"""
Database Migration Script for AI/ML Features

This script creates the new database tables required for the AI/ML enhancements.
"""

import os
import sys

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# Set up minimal environment
os.environ.setdefault("DATABASE_URL", "sqlite:///./data/reaper.db")

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Text, JSON, inspect
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class CapacityPrediction(Base):
    """Predictive capacity planning forecasts."""
    __tablename__ = "capacity_predictions"

    id = Column(Integer, primary_key=True, index=True)
    resource_id = Column(String, index=True)
    prediction_date = Column(DateTime, default=datetime)
    forecast_horizon_days = Column(Integer)
    predicted_cpu = Column(Float, nullable=True)
    predicted_memory = Column(Float, nullable=True)
    predicted_cost = Column(Float)
    confidence_interval_lower = Column(Float, nullable=True)
    confidence_interval_upper = Column(Float, nullable=True)
    model_version = Column(String)
    forecast_data = Column(JSON)


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
    analysis_timestamp = Column(DateTime, default=datetime)


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
    created_at = Column(DateTime, default=datetime)


class AlertFeedback(Base):
    """User feedback on alerts for intelligent tuning."""
    __tablename__ = "alert_feedback"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(String, index=True)
    user_id = Column(String, index=True)
    feedback_type = Column(String)
    feedback_value = Column(Integer, nullable=True)
    feedback_text = Column(Text, nullable=True)
    response_time_seconds = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=datetime)


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
    created_at = Column(DateTime, default=datetime)


def migrate_ai_ml_tables():
    """Create AI/ML enhancement tables in the database."""
    print("Creating AI/ML enhancement tables...")

    try:
        # Create data directory if it doesn't exist
        data_dir = os.path.join(os.path.dirname(__file__), "../../../data")
        os.makedirs(data_dir, exist_ok=True)

        # Create database engine
        db_path = os.path.join(data_dir, "reaper.db")
        engine = create_engine(f"sqlite:///{db_path}")

        # Create all tables including the new ones
        Base.metadata.create_all(bind=engine)
        print("✅ AI/ML tables created successfully!")

        # Verify tables were created
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        ai_ml_tables = [
            "capacity_predictions",
            "anomaly_explanations",
            "chat_conversations",
            "alert_feedback",
            "alert_optimizations",
        ]

        for table in ai_ml_tables:
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
    migrate_ai_ml_tables()