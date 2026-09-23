import os
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

load_dotenv()

# ---------------------------------------------------------------------------
# Database URL resolution
# ---------------------------------------------------------------------------
# Unified rule (Python and Go share the same file):
#   1. Honour DATABASE_URL env-var when explicitly set.
#   2. Otherwise resolve <repo-root>/data/reaper.db so both runtimes hit the
#      same file regardless of which Python package directory __file__ resolves
#      to at import time.
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Walk up from this file until we find the repo root (contains pyproject.toml
    # or .git), then use <repo_root>/data/reaper.db.
    _this_file = Path(__file__).resolve()
    _repo_root = _this_file.parent
    for _parent in _this_file.parents:
        if (_parent / "pyproject.toml").exists() or (_parent / ".git").exists():
            _repo_root = _parent
            break
    _data_dir = _repo_root / "data"
    _data_dir.mkdir(parents=True, exist_ok=True)
    DATABASE_URL = f"sqlite:///{_data_dir / 'reaper.db'}"

# Convert to async URL
ASYNC_DATABASE_URL: str | None = None
if "postgresql" in DATABASE_URL:
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
elif "sqlite" in DATABASE_URL:
    ASYNC_DATABASE_URL = DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite://")


def _apply_sqlite_pragmas(dbapi_conn, _connection_record) -> None:  # noqa: ANN001
    """Enable WAL journal mode, busy timeout, and NORMAL fsync on every new
    SQLite connection.  WAL allows concurrent readers alongside the single
    writer and eliminates the "database is locked" errors that the old
    journal=DELETE mode produced under pool_size=20 / MaxOpenConns=25."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")  # ms — callers wait up to 5 s
    cursor.execute("PRAGMA synchronous=NORMAL")  # safe with WAL; faster than FULL
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# ---------------------------------------------------------------------------
# Engine configuration
# ---------------------------------------------------------------------------
# SQLite is single-writer by design.  pool_size=20 / max_overflow=10 means 30
# threads can *hold* a connection simultaneously — but only 1 can write.  The
# other 29 block, timeout, and raise OperationalError.  Cap to 5 connections
# (reads can share; the single writer slot is effectively serialised anyway).
# ---------------------------------------------------------------------------
engine_config: dict = (
    {
        "connect_args": {"check_same_thread": False},
        "pool_pre_ping": True,
        "echo": False,
        "pool_size": 5,      # was 20 — SQLite is single-writer; >5 just queues
        "max_overflow": 0,   # no extra connections beyond pool_size
    }
    if "sqlite" in DATABASE_URL
    else {
        "pool_size": 40,
        "max_overflow": 60,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
        "pool_timeout": 15,
        "echo": False,
        "connect_args": (
            {
                "connect_timeout": 10,
                "options": "-c statement_timeout=30000",
            }
            if "postgresql" in DATABASE_URL
            else {}
        ),
    }
)

# Sync engine (for backward compatibility)
engine = create_engine(DATABASE_URL, **engine_config)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Wire WAL + busy_timeout for every new SQLite connection in the sync pool
if "sqlite" in DATABASE_URL:
    event.listen(engine, "connect", _apply_sqlite_pragmas)

# Async engine
async_engine_config = engine_config.copy()
if "sqlite" in DATABASE_URL:
    async_engine_config["connect_args"] = {"check_same_thread": False}
    # aiosqlite uses StaticPool internally; pool_size/max_overflow not supported
    async_engine_config.pop("pool_size", None)
    async_engine_config.pop("max_overflow", None)

if ASYNC_DATABASE_URL:
    async_engine = create_async_engine(ASYNC_DATABASE_URL, **async_engine_config)
    AsyncSessionLocal = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False, autocommit=False, autoflush=False
    )
    # Wire WAL pragmas for async connections too
    if "sqlite" in ASYNC_DATABASE_URL:
        event.listen(async_engine.sync_engine, "connect", _apply_sqlite_pragmas)
else:
    async_engine = None
    AsyncSessionLocal = None


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
    last_seen = Column(DateTime, default=lambda: datetime.now(UTC))

    cost_history = relationship("CostHistory", back_populates="resource")
    reap_actions = relationship("ReapAction", back_populates="resource")
    recommendations = relationship("Recommendation", back_populates="resource")
    action_logs = relationship("ActionLog", back_populates="resource")


class CostHistory(Base):
    __tablename__ = "cost_history"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    resource_id = Column(String, ForeignKey("legacy_resources.id"))
    date = Column(DateTime, default=lambda: datetime.now(UTC))
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
    timestamp = Column(DateTime, default=lambda: datetime.now(UTC))

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
    timestamp = Column(DateTime, default=lambda: datetime.now(UTC))

    resource = relationship("Resource", back_populates="action_logs")


class BusinessMetric(Base):
    __tablename__ = "business_metrics"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    metric_name = Column(String, index=True)  # e.g. ACTIVE_USERS, API_REQUESTS
    value = Column(Float)
    unit = Column(String)
    date = Column(DateTime, default=lambda: datetime.now(UTC))


class RegionPriceCache(Base):
    __tablename__ = "region_price_cache"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    sku_id = Column(String, index=True)
    region_name = Column(String, index=True)
    price = Column(Numeric(15, 6))
    currency = Column(String, default="USD")
    last_updated = Column(DateTime, default=lambda: datetime.now(UTC))


class VaultSettings(Base):
    """Single-row vault configuration (passcode verifier + encryption salt)."""

    __tablename__ = "vault_settings"

    id = Column(Integer, primary_key=True, default=1)
    salt = Column(String(64), nullable=False)
    passcode_verifier = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
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
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
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
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class CloudResource(Base):
    __tablename__ = "resources"

    id = Column(String, primary_key=True)
    provider = Column(String, nullable=False, index=True)  # azure, aws, gcp
    resource_type = Column(String, nullable=False, index=True)  # virtual_machines, disks
    region = Column(String, nullable=False)
    # cost_attributes stores all resource metadata as JSON for engine-agnostic portability
    cost_attributes = Column(JSON, nullable=False)
    last_scanned = Column(DateTime, default=lambda: datetime.now(UTC), index=True)

    # Composite index for snapshot queries: provider+type+region filtered by watermark
    __table_args__ = (
        Index(
            "ix_resources_lookup",
            "provider",
            "resource_type",
            "region",
            "last_scanned",
        ),
    )


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False, index=True)
    scope_type = Column(String, nullable=False)  # TAG, SUBSCRIPTION, etc.
    scope_value = Column(String, nullable=False)
    monthly_limit = Column(Numeric(15, 2), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    alerts = relationship("BudgetAlert", back_populates="budget", cascade="all, delete-orphan")


class BudgetAlert(Base):
    __tablename__ = "budget_alerts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    budget_id = Column(Integer, ForeignKey("budgets.id"), nullable=False)
    threshold_percentage = Column(Numeric(5, 2), nullable=False)  # e.g., 85.00
    notification_channel = Column(String, nullable=False)  # DISCORD, SLACK, etc.
    is_triggered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    budget = relationship("Budget", back_populates="alerts")


class CloudCommitment(Base):
    __tablename__ = "cloud_commitments"

    id = Column(String, primary_key=True)
    provider_type = Column(String, nullable=False, index=True)  # aws, azure, gcp
    commitment_type = Column(String, nullable=False)  # SAVINGS_PLAN, RESERVED_INSTANCE
    hourly_commitment = Column(Numeric(15, 4), nullable=False)
    status = Column(String, nullable=False)  # ACTIVE, EXPIRED, etc.
    expiration_date = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))


class OptimizationBaseline(Base):
    """
    Stores the optimized resource baseline after rightsizing analysis.
    This baseline is used for commitment management calculations to prevent
    capital waste by evaluating reservations AFTER rightsizing.
    """

    __tablename__ = "optimization_baselines"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    resource_id = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False, index=True)  # azure, aws, gcp
    current_sku = Column(String, nullable=False)
    recommended_action = Column(String, nullable=False)  # STAY, RIGHTSIZE, SHUTDOWN
    environment_type = Column(String, nullable=False)  # production, dev-test
    current_avg_cpu = Column(Numeric(10, 2), nullable=False)
    current_avg_memory = Column(Numeric(10, 2), nullable=False)
    confidence_score = Column(Numeric(5, 4), nullable=False)
    estimated_savings = Column(Numeric(15, 4), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


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


@asynccontextmanager
async def get_async_db_session():
    """Async context manager for database sessions to ensure proper cleanup."""
    if AsyncSessionLocal is None:
        raise RuntimeError(
            "Async database not configured. Set DATABASE_URL with PostgreSQL or SQLite."
        )

    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


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


# AI/ML Enhancement Tables


class CapacityPrediction(Base):
    """Predictive capacity planning forecasts."""

    __tablename__ = "capacity_predictions"

    id = Column(Integer, primary_key=True, index=True)
    resource_id = Column(String, index=True)
    prediction_date = Column(DateTime, default=datetime.now)
    forecast_horizon_days = Column(Integer)
    predicted_cpu = Column(Float, nullable=True)
    predicted_memory = Column(Float, nullable=True)
    predicted_cost = Column(Float)
    confidence_interval_lower = Column(Float, nullable=True)
    confidence_interval_upper = Column(Float, nullable=True)
    model_version = Column(String)
    forecast_data = Column(JSON)  # Stores full forecast details
    created_at = Column(DateTime, default=datetime.now)


class AnomalyExplanation(Base):
    """Root cause analysis for cost anomalies."""

    __tablename__ = "anomaly_explanations"

    id = Column(Integer, primary_key=True, index=True)
    anomaly_id = Column(String, index=True)
    resource_id = Column(String, index=True)
    root_cause = Column(String)
    causal_factors = Column(JSON)
    explanation_text = Column(Text)
    confidence_score = Column(Float)
    recommendations = Column(JSON)
    analysis_timestamp = Column(DateTime, default=datetime.now)


class ChatConversation(Base):
    """Natural language query conversation history."""

    __tablename__ = "chat_conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    session_id = Column(String, index=True)
    query_text = Column(Text)
    intent_classification = Column(String)
    sql_query = Column(Text, nullable=True)
    response_text = Column(Text)
    response_data = Column(JSON, nullable=True)
    processing_time_seconds = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.now)


class AlertFeedback(Base):
    """User feedback on alerts for intelligent tuning."""

    __tablename__ = "alert_feedback"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(String, index=True)
    user_id = Column(String, index=True)
    feedback_type = Column(String)  # 'acknowledge', 'dismiss', 'snooze', 'action_taken'
    feedback_value = Column(Integer, nullable=True)  # 1-5 rating
    feedback_text = Column(Text, nullable=True)
    response_time_seconds = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=datetime.now)


class AlertOptimization(Base):
    """Optimized alert thresholds and settings."""

    __tablename__ = "alert_optimizations"

    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(String, index=True)
    user_id = Column(String, index=True, nullable=True)
    original_threshold = Column(Float)
    optimized_threshold = Column(Float)
    adjustment_percentage = Column(Float)
    user_sensitivity = Column(Float)
    historical_quality = Column(Float)
    rationale = Column(Text)
    confidence = Column(String)
    created_at = Column(DateTime, default=datetime.now)
