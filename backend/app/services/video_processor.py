"""
video_processor.py

Ties the pipeline together for one uploaded video:

    Tracker  ->  ZoneEngine  ->  EventEngine  ->  Event Store (DB)

This is what FastAPI's BackgroundTasks calls after a video is uploaded,
so the /upload request returns immediately instead of blocking for the
whole video's processing time.
"""

from pathlib import Path

from app.services.zone_engine import ZoneEngine
from app.services.event_engine import EventEngine
from app.services.tracker_service import RealTrackerService, MockTrackerService
from app.database.database import SessionLocal
from app.models.event import Event

ZONES_PATH = Path(__file__).resolve().parent.parent / "config" / "zones.json"

# In-memory job status store for the MVP. Swap for a DB table or Redis
# once you need this to survive a server restart or scale to workers.
JOB_STATUS = {}


def process_video(job_id: str, video_path: str, use_mock_tracker: bool = True):
    """
    Runs the full pipeline against one video and writes events to the DB.
    Call this via FastAPI's BackgroundTasks, not inline in the request.
    """
    JOB_STATUS[job_id] = {"status": "PROCESSING", "persons_detected": 0, "events_detected": 0}

    zone_engine = ZoneEngine.from_json(ZONES_PATH)
    event_engine = EventEngine()

    db = SessionLocal()
    seen_person_ids = set()
    events_written = 0

    try:
        if use_mock_tracker:
            tracker = MockTrackerService()
            # For the mock, just iterate over whichever frame numbers have tracks
            frame_numbers = sorted(tracker.mock_tracks_per_frame.keys())
            frame_iter = (
                (frame_number, tracker.get_tracks_for_frame(frame_number))
                for frame_number in frame_numbers
            )
        else:
            tracker = RealTrackerService(video_path)
            frame_iter = tracker.run()

        for frame_number, tracks in frame_iter:
            for track in tracks:
                person_id = track["track_id"]
                bbox = track["bbox"]
                seen_person_ids.add(person_id)

                zone = zone_engine.get_zone(bbox)
                events = event_engine.process_zone(
                    person_id=person_id,
                    zone=zone,
                    frame_number=frame_number,
                )

                for event in events:
                    db_event = Event(
                        job_id=job_id,
                        person_id=str(event["person_id"]),
                        event_type=event["event"],
                        zone=event.get("to_zone") or event.get("zone"),
                        frame_number=event.get("frame_number"),
                        status=event.get("status", "OK"),
                    )
                    db.add(db_event)
                    events_written += 1

        db.commit()

        JOB_STATUS[job_id] = {
            "status": "COMPLETED",
            "persons_detected": len(seen_person_ids),
            "events_detected": events_written,
        }

    except Exception as exc:  # noqa: BLE001 - MVP-level catch-all, tighten later
        db.rollback()
        JOB_STATUS[job_id] = {"status": "FAILED", "error": str(exc)}
        raise

    finally:
        db.close()
