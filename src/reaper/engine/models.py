import os
from datetime import datetime

try:
    from datetime import UTC
except ImportError:
    UTC = UTC

from dotenv import load_dotenv
from sqlalchemy import (
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Resource(Base):
    __tablename__ = "resources"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, index=True)
    type = Column(String, index=True)
    region = Column(String)
    tags = Column(JSONB, default={})
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
    resource_id = Column(String, ForeignKey("resources.id"))
    date = Column(DateTime, default=lambda: datetime.now(UTC))
    cost = Column(Numeric(15, 4))
    cost_type = Column(String, default="ACTUAL")  # ACTUAL or AMORTIZED
    currency = Column(String, default="USD")

    resource = relationship("Resource", back_populates="cost_history")


class ReapAction(Base):
    __tablename__ = "reap_actions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    resource_id = Column(String, ForeignKey("resources.id"))
    action = Column(String)  # e.g. DEALLOCATE, DELETE
    authorized_by = Column(String)
    timestamp = Column(DateTime, default=lambda: datetime.now(UTC))

    resource = relationship("Resource", back_populates="reap_actions")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    resource_id = Column(String, ForeignKey("resources.id"))
    recommendation_type = Column(String)  # e.g. RIGHTSIZE, GREENOPS
    savings = Column(Numeric(15, 4))
    description = Column(String)

    resource = relationship("Resource", back_populates="recommendations")


class ActionLog(Base):
    __tablename__ = "action_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    resource_id = Column(String, ForeignKey("resources.id"))
    action_type = Column(String)  # REAP, KILL, PROTECTION_ADD
    status = Column(String)  # SUCCESS, FAILED
    details = Column(String)
    previous_hash = Column(String)
    signature = Column(String)
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
    credentials = Column(JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    scope_type = Column(String, nullable=False)  # e.g., "TAG", "PROVIDER", "ACCOUNT"
    scope_value = Column(String, nullable=False)  # e.g., "Owner=ankit" or "azure"
    monthly_limit = Column(Numeric(15, 4), nullable=False)


class BudgetAlert(Base):
    __tablename__ = "budget_alerts"

    id = Column(Integer, primary_key=True)
    budget_id = Column(Integer, ForeignKey("budgets.id"), nullable=False)
    threshold_percentage = Column(Numeric(5, 2), nullable=False)  # e.g., 85.00 for 85%
    notification_channel = Column(String, default="DISCORD")
    is_triggered = Column(Boolean, default=False)


class CloudCommitment(Base):
    __tablename__ = "cloud_commitments"

    id = Column(String, primary_key=True)  # e.g., AWS SP ARN or Azure Reservation ID
    provider_type = Column(String, nullable=False)  # aws, azure
    commitment_type = Column(String, nullable=False)  # "SAVINGS_PLAN", "RESERVED_INSTANCE"
    hourly_commitment = Column(
        Numeric(10, 4), nullable=False
    )  # The agreed dollar-per-hour spend contract
    status = Column(String, nullable=False)  # ACTIVE, EXPIRED, RETIRED
    expiration_date = Column(DateTime, nullable=False)


def init_db():
    Base.metadata.create_all(bind=engine)
