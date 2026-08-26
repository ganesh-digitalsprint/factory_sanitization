"""
event.py

SQLAlchemy model for the events table.
"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, DateTime

from app.database.database import Base


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, index=True)
    person_id = Column(String, index=True)
    event_type = Column(String)       # e.g. ZONE_CHANGED, SEQUENCE_COMPLETED
    zone = Column(String, nullable=True)
    frame_number = Column(Integer, nullable=True)
    status = Column(String, default="OK")   # OK, COMPLETED, MISSED_STEP
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
