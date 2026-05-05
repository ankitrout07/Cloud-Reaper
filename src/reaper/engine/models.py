import os
from datetime import datetime, UTC

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

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Resource(Base):
    __tablename__ = "resources"

    id = Column(String, primary_key=True, index=True)  # Azure Resource ID
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
    timestamp = Column(DateTime, default=lambda: datetime.now(UTC))

    resource = relationship("Resource", back_populates="action_logs")


class BusinessMetric(Base):
    __tablename__ = "business_metrics"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    metric_name = Column(String, index=True)  # e.g. ACTIVE_USERS, API_REQUESTS
    value = Column(Float)
    unit = Column(String)
    date = Column(DateTime, default=lambda: datetime.now(UTC))


def init_db():
    Base.metadata.create_all(bind=engine)
