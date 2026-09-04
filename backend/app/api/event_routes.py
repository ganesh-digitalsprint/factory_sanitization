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
from app.services.db_writer import get_in_memory_events

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/{job_id}")
async def get_events(job_id: str, db: Session = Depends(get_db)):
    mem_events = get_in_memory_events(job_id)
    if mem_events is not None:
        sorted_events = sorted(mem_events, key=lambda x: x.get("frame_number") or 0)
        return [
            {
                "person_id": str(e.get("person_id")),
                "event_type": e.get("event_type"),
                "zone": e.get("zone"),
                "frame_number": e.get("frame_number"),
                "status": e.get("status", "OK"),
                "created_at": e.get("created_at"),
            }
            for e in sorted_events
        ]

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
    mem_events = get_in_memory_events(job_id)
    if mem_events is not None:
        raw_events = mem_events
    else:
        events = db.query(Event).filter(Event.job_id == job_id).all()
        raw_events = [
            {
                "person_id": e.person_id,
                "event_type": e.event_type,
                "status": e.status,
            }
            for e in events
        ]

    per_person = defaultdict(lambda: {"events": 0, "status": "IN_PROGRESS"})
    for e in raw_events:
        pid = str(e.get("person_id"))
        per_person[pid]["events"] += 1
        if e.get("event_type") == "SEQUENCE_COMPLETED":
            per_person[pid]["status"] = e.get("status", "OK")

    return [
        {"person_id": pid, **data}
        for pid, data in per_person.items()
    ]

