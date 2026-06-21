import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps

from dotenv import load_dotenv
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    create_engine,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

load_dotenv()

# We need engine-agnostic JSON (not JSONB) for SQLite compatibility
# in desktop mode
# Default to SQLite in a data directory; use PostgreSQL if DATABASE_URL is set
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Use SQLite by default
    data_dir = os.path.join(os.path.dirname(__file__), "../../../data")
    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, "reaper.db")
    DATABASE_URL = f"sqlite:///{db_path}"

# Configure engine with connection pooling for better performance
engine_config = (
    {
        "connect_args": {"check_same_thread": False},
        "pool_pre_ping": True,  # Verify connections before using
        "echo": False,  # Disable SQL logging for performance
    }
    if "sqlite" in DATABASE_URL
    else {
        "pool_size": 20,  # Increased pool size for better concurrency
        "max_overflow": 30,  # Increased max overflow for peak loads
        "pool_pre_ping": True,  # Verify connections before using
        "pool_recycle": 1800,  # Recycle connections after 30 minutes
        "pool_timeout": 30,  # Timeout for getting connection from pool
        "echo": False,  # Disable SQL logging for performance
    }
)

engine = create_engine(DATABASE_URL, **engine_config)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Resource(Base):
    __tablename__ = "legacy_resources"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, index=True)
    type = Column(String, index=True)
    region = Column(String)
    tags = Column(JSON, default={})
    active = Column(Boolean, default=True)
    is_protected = Column(Boolean, default=False)
    is_unallocated = Column(Boolean, default=False)
    last_seen = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    cost_history = relationship("CostHistory", back_populates="resource")
    reap_actions = relationship("ReapAction", back_populates="resource")
    recommendations = relationship("Recommendation", back_populates="resource")
    action_logs = relationship("ActionLog", back_populates="resource")


class CostHistory(Base):
    __tablename__ = "cost_history"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    resource_id = Column(String, ForeignKey("legacy_resources.id"))
    date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    cost = Column(Numeric(15, 4))
    cost_type = Column(String, default="ACTUAL")  # ACTUAL or AMORTIZED
    currency = Column(String, default="USD")

    resource = relationship("Resource", back_populates="cost_history")


class ReapAction(Base):
    __tablename__ = "reap_actions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    resource_id = Column(String, ForeignKey("legacy_resources.id"))
    action = Column(String)  # e.g. DEALLOCATE, DELETE
    authorized_by = Column(String)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    resource = relationship("Resource", back_populates="reap_actions")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    resource_id = Column(String, ForeignKey("legacy_resources.id"))
    recommendation_type = Column(String)  # e.g. RIGHTSIZE, GREENOPS
    savings = Column(Numeric(15, 4))
    description = Column(String)

    resource = relationship("Resource", back_populates="recommendations")


class ActionLog(Base):
    __tablename__ = "action_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    resource_id = Column(String, ForeignKey("legacy_resources.id"))
    action_type = Column(String)  # REAP, KILL, PROTECTION_ADD
    status = Column(String)  # SUCCESS, FAILED
    details = Column(String)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    resource = relationship("Resource", back_populates="action_logs")


class BusinessMetric(Base):
    __tablename__ = "business_metrics"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    metric_name = Column(String, index=True)  # e.g. ACTIVE_USERS, API_REQUESTS
    value = Column(Float)
    unit = Column(String)
    date = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class RegionPriceCache(Base):
    __tablename__ = "region_price_cache"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    sku_id = Column(String, index=True)
    region_name = Column(String, index=True)
    price = Column(Numeric(15, 6))
    currency = Column(String, default="USD")
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class VaultSettings(Base):
    """Single-row vault configuration (passcode verifier + encryption salt)."""

    __tablename__ = "vault_settings"

    id = Column(Integer, primary_key=True, default=1)
    salt = Column(String(64), nullable=False)
    passcode_verifier = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class VaultEntry(Base):
    """Encrypted secret entry (payload decrypted only while vault is unlocked)."""

    __tablename__ = "vault_entries"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    label = Column(String(200), nullable=False)
    entry_type = Column(
        String(40), nullable=False, default="credential"
    )  # credential, passcode, note
    encrypted_payload = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class CloudConnection(Base):
    """
    Multi-cloud credential vault. Only one connection should be active at a time.

    credentials JSON shape by provider_type:
      - aws: access_key_id, secret_access_key, region
      - azure: tenant_id, client_id, client_secret, subscription_id
      - gcp: project_id, service_account_json (inline JSON or file path)
      - k8s: kubeconfig (path), context (optional)
    """

    __tablename__ = "cloud_connections"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    provider_type = Column(String(20), nullable=False, index=True)  # azure, aws, gcp, k8s
    connection_name = Column(String(100), nullable=False)
    credentials = Column(JSON, nullable=False, default=dict)
    is_active = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class CloudResource(Base):
    __tablename__ = "resources"

    id = Column(String, primary_key=True)
    provider = Column(String, nullable=False, index=True)  # azure, aws, gcp
    resource_type = Column(String, nullable=False)  # virtual_machines, disks
    region = Column(String, nullable=False)
    cost_attributes = Column(JSON, nullable=False)  # Engine-agnostic storage replacement for JSONB
    last_scanned = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False, index=True)
    scope_type = Column(String, nullable=False)  # TAG, SUBSCRIPTION, etc.
    scope_value = Column(String, nullable=False)
    monthly_limit = Column(Numeric(15, 2), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    alerts = relationship("BudgetAlert", back_populates="budget", cascade="all, delete-orphan")


class BudgetAlert(Base):
    __tablename__ = "budget_alerts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    budget_id = Column(Integer, ForeignKey("budgets.id"), nullable=False)
    threshold_percentage = Column(Numeric(5, 2), nullable=False)  # e.g., 85.00
    notification_channel = Column(String, nullable=False)  # DISCORD, SLACK, etc.
    is_triggered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    budget = relationship("Budget", back_populates="alerts")


class CloudCommitment(Base):
    __tablename__ = "cloud_commitments"

    id = Column(String, primary_key=True)
    provider_type = Column(String, nullable=False, index=True)  # aws, azure, gcp
    commitment_type = Column(String, nullable=False)  # SAVINGS_PLAN, RESERVED_INSTANCE
    hourly_commitment = Column(Numeric(15, 4), nullable=False)
    status = Column(String, nullable=False)  # ACTIVE, EXPIRED, etc.
    expiration_date = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def get_desktop_engine():
    """Resolves zero-configuration database mapping inside native system APPDATA"""
    if os.name == "nt" or "PRODUCTION_DESKTOP_MODE" in os.environ:
        base_dir = os.environ.get("APPDATA", os.path.expanduser("~"))
        db_dir = os.path.join(base_dir, "CloudReaper")
    else:
        db_dir = os.path.abspath(os.path.dirname(__file__))

    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "metadata.db")
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


def init_db():
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_db_session():
    """Context manager for database sessions to ensure proper cleanup."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def retry_on_db_error(max_retries=3, delay=1.0):
    """Decorator to retry database operations on transient errors."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        time.sleep(delay * (attempt + 1))
                    else:
                        raise
                except Exception:
                    # Don't retry non-database errors
                    raise
            raise last_exception

        return wrapper

    return decorator
