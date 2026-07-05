"""
Database Migration Script for Governance Features

This script creates the new database tables required for the governance features.
"""

import os
import sys

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# Set up minimal environment
os.environ.setdefault("DATABASE_URL", "sqlite:///./data/reaper.db")

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class PolicyTemplate(Base):
    """Cross-cloud policy templates."""

    __tablename__ = "policy_templates"

    id = Column(Integer, primary_key=True, index=True)
    policy_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)  # cost_optimization, security_governance, etc.
    severity = Column(String, nullable=False)  # critical, high, medium, low
    description = Column(Text)
    universal_rules = Column(JSON)
    provider_translations = Column(JSON)
    version = Column(Integer, default=1)
    status = Column(String, default="draft")  # active, draft, disabled, archived
    created_at = Column(DateTime, default=datetime)
    updated_at = Column(DateTime, default=datetime, onupdate=datetime)


class PolicyEvaluation(Base):
    """Policy compliance evaluation results."""

    __tablename__ = "policy_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    policy_id = Column(String, index=True, nullable=False)
    resource_id = Column(String, index=True, nullable=False)
    resource_type = Column(String)
    provider = Column(String, nullable=False)
    compliant = Column(Boolean, default=False)
    violations = Column(JSON)
    evaluated_at = Column(DateTime, default=datetime, index=True)

    # Relationship to policy template
    policy_template_id = Column(Integer, ForeignKey("policy_templates.id"))
    policy_template = relationship("PolicyTemplate", backref="evaluations")


class MigrationAssessment(Base):
    """Cloud provider migration assessments."""

    __tablename__ = "migration_assessments"

    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(String, unique=True, index=True, nullable=False)
    source_provider = Column(String, nullable=False)
    target_provider = Column(String, nullable=False)
    resource_inventory = Column(JSON)
    cost_analysis = Column(JSON)
    risk_assessment = Column(JSON)
    roi_analysis = Column(JSON)
    migration_plan = Column(JSON)
    created_at = Column(DateTime, default=datetime, index=True)
    status = Column(String, default="pending")  # pending, in_progress, completed, cancelled


class UnifiedCostRecord(Base):
    """Multi-cloud cost aggregation records."""

    __tablename__ = "unified_cost_records"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, index=True, nullable=False)
    resource_id = Column(String, index=True, nullable=False)
    resource_type = Column(String)
    region = Column(String, index=True)
    service_category = Column(String, index=True)
    original_currency = Column(String)
    original_amount = Column(Float)
    base_currency = Column(String, default="USD")
    converted_amount = Column(Float)
    billing_period_start = Column(DateTime, index=True)
    billing_period_end = Column(DateTime, index=True)
    cost_type = Column(String)  # capex, opex, reservation
    tags = Column(JSON)
    created_at = Column(DateTime, default=datetime)


class BestPractice(Base):
    """Provider-specific best practices."""

    __tablename__ = "best_practices"

    id = Column(Integer, primary_key=True, index=True)
    practice_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)  # cost_optimization, security, reliability, etc.
    severity = Column(String, nullable=False)  # critical, high, medium, low, info
    provider = Column(String, nullable=False)
    description = Column(Text)
    rationale = Column(Text)
    implementation_guide = Column(Text)
    resource_types = Column(JSON)
    check_logic = Column(JSON)
    remediation_steps = Column(JSON)
    references = Column(JSON)
    created_at = Column(DateTime, default=datetime)
    updated_at = Column(DateTime, default=datetime, onupdate=datetime)


class PracticeEvaluation(Base):
    """Best practice evaluation results."""

    __tablename__ = "practice_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    practice_id = Column(String, index=True, nullable=False)
    resource_id = Column(String, index=True, nullable=False)
    resource_type = Column(String)
    status = Column(String, nullable=False)  # compliant, non_compliant, not_applicable, unknown
    severity = Column(String)
    findings = Column(Text)
    recommendations = Column(JSON)
    estimated_effort = Column(String)
    estimated_cost_impact = Column(String)
    evaluated_at = Column(DateTime, default=datetime, index=True)

    # Relationship to best practice
    best_practice_id = Column(Integer, ForeignKey("best_practices.id"))
    best_practice = relationship("BestPractice", backref="evaluations")


class GovernanceReport(Base):
    """Generated governance reports."""

    __tablename__ = "governance_reports"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(String, unique=True, index=True, nullable=False)
    report_type = Column(
        String, nullable=False
    )  # policy_compliance, cost_analysis, migration_assessment, best_practices
    provider = Column(String, index=True)
    period_start = Column(DateTime, index=True)
    period_end = Column(DateTime, index=True)
    report_data = Column(JSON)
    summary = Column(JSON)
    generated_at = Column(DateTime, default=datetime, index=True)
    generated_by = Column(String)  # user_id or system


class GovernanceMetric(Base):
    """Governance metrics for tracking and alerting."""

    __tablename__ = "governance_metrics"

    id = Column(Integer, primary_key=True, index=True)
    metric_name = Column(String, index=True, nullable=False)
    provider = Column(String, index=True)
    resource_id = Column(String, index=True)
    metric_value = Column(Float)
    metric_unit = Column(String)
    recorded_at = Column(DateTime, default=datetime, index=True)
    meta_data = Column(JSON)  # Renamed from 'metadata' (reserved in SQLAlchemy)


def migrate_governance_tables():
    """Create governance feature tables in the database."""
    print("Creating governance feature tables...")

    try:
        # Create data directory if it doesn't exist
        data_dir = os.path.join(os.path.dirname(__file__), "../../../data")
        os.makedirs(data_dir, exist_ok=True)

        # Create database engine
        db_path = os.path.join(data_dir, "reaper.db")
        engine = create_engine(f"sqlite:///{db_path}")

        # Create all tables including the new ones
        Base.metadata.create_all(bind=engine)
        print("✅ Governance tables created successfully!")

        # Verify tables were created
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        governance_tables = [
            "policy_templates",
            "policy_evaluations",
            "migration_assessments",
            "unified_cost_records",
            "best_practices",
            "practice_evaluations",
            "governance_reports",
            "governance_metrics",
        ]

        for table in governance_tables:
            if table in existing_tables:
                print(f"✅ Table '{table}' verified")
            else:
                print(f"⚠️  Table '{table}' not found")

        print("\nMigration completed successfully!")
        return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    migrate_governance_tables()
