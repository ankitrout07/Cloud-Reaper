import os
import sys
from sqlalchemy import create_engine, Column, String, Float, DateTime, JSON
from sqlalchemy.orm import declarative_base, sessionmaker
import datetime

Base = declarative_base()

class CloudResource(Base):
    __tablename__ = "resources"
    
    id = Column(String, primary_key=True)
    provider = Column(String, nullable=False, index=True) # azure, aws, gcp
    resource_type = Column(String, nullable=False)        # virtual_machines, disks
    region = Column(String, nullable=False)
    cost_attributes = Column(JSON, nullable=False)        # Engine-agnostic storage replacement for JSONB
    last_scanned = Column(DateTime, default=datetime.datetime.utcnow)

def get_desktop_engine():
    """Resolves zero-configuration database mapping inside native system APPDATA"""
    if os.name == 'nt' or "PRODUCTION_DESKTOP_MODE" in os.environ:
        base_dir = os.environ.get("APPDATA", os.path.expanduser("~"))
        db_dir = os.path.join(base_dir, "CloudReaper")
    else:
        db_dir = os.path.abspath(os.path.dirname(__file__))
        
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "metadata.db")
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
