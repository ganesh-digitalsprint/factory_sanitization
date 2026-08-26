"""
event_routes.py

GET /events/{job_id}            - all events for a job
GET /events/{job_id}/summary    - per-person completed/missed-step summary
"""

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.event import Event

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/{job_id}")
async def get_events(job_id: str, db: Session = Depends(get_db)):
    events = db.query(Event).filter(Event.job_id == job_id).order_by(Event.frame_number).all()
    return [
        {
            "person_id": e.person_id,
            "event_type": e.event_type,
            "zone": e.zone,
            "frame_number": e.frame_number,
            "status": e.status,
            "created_at": e.created_at,
        }
        for e in events
    ]


@router.get("/{job_id}/summary")
async def get_summary(job_id: str, db: Session = Depends(get_db)):
    events = db.query(Event).filter(Event.job_id == job_id).all()

    per_person = defaultdict(lambda: {"events": 0, "status": "IN_PROGRESS"})
    for e in events:
        per_person[e.person_id]["events"] += 1
        if e.event_type == "SEQUENCE_COMPLETED":
            per_person[e.person_id]["status"] = e.status  # COMPLETED or MISSED_STEP

    return [
        {"person_id": pid, **data}
        for pid, data in per_person.items()
    ]
