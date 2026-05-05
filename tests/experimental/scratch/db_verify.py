import sys
from pathlib import Path

from sqlalchemy import inspect

# Set PYTHONPATH to include src directory
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

try:
    from reaper.engine.models import BusinessMetric, SessionLocal, engine, init_db
except ImportError:
    print("Error: Could not import reaper modules. Check PYTHONPATH.")
    sys.exit(1)


def verify():
    print("Initializing Database...")
    try:
        init_db()
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Error initializing DB: {e}")
        return

    inspector = inspect(engine)

    print("\nVerifying Tables:")
    tables = inspector.get_table_names()
    print(f"Tables found: {tables}")

    expected_tables = ["resources", "cost_history", "business_metrics"]
    for table in expected_tables:
        if table in tables:
            print(f"✅ Table '{table}' exists.")
        else:
            print(f"❌ Table '{table}' is MISSING.")

    print("\nVerifying Columns in 'resources':")
    columns = [c["name"] for c in inspector.get_columns("resources")]
    if "is_unallocated" in columns:
        print("✅ Column 'is_unallocated' exists in 'resources'.")
    else:
        print("❌ Column 'is_unallocated' is MISSING in 'resources'.")

    print("\nVerifying Columns in 'cost_history':")
    columns = [c["name"] for c in inspector.get_columns("cost_history")]
    if "cost_type" in columns:
        print("✅ Column 'cost_type' exists in 'cost_history'.")
    else:
        print("❌ Column 'cost_type' is MISSING in 'cost_history'.")

    print("\nSeed Sample Data...")
    session = SessionLocal()
    try:
        # Check if business metrics can be added
        metric = BusinessMetric(metric_name="ACTIVE_USERS", value=15000, unit="per 1K users")
        session.add(metric)
        session.commit()
        print("✅ Successfully added sample BusinessMetric.")
    except Exception as e:
        print(f"❌ Error adding sample data: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    verify()
