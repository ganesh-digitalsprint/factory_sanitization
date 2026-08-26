"""
video_processor.py

Ties the pipeline together for one uploaded video:

    Tracker  ->  ZoneEngine  ->  EventEngine  ->  Event Store (DB)
                                        |
                                        +--> WebSocket (live to React)

This is what FastAPI's BackgroundTasks calls after a video is uploaded,
so the /upload request returns immediately instead of blocking for the
whole video's processing time. As each frame is processed, results are
pushed live over the session's WebSocket AND written to the DB, so the
DB stays the source of truth even if nobody's connected to the socket.

A small artificial delay is added between frames for the mock tracker
so the live feed is actually visible in the UI rather than finishing
instantly - remove FRAME_DELAY_SECONDS once you're driving this from a
real video's actual frame rate.
"""

import time
from pathlib import Path

from app.services.zone_engine import ZoneEngine
from app.services.event_engine import EventEngine
from app.services.tracker_service import RealTrackerService, MockTrackerService
from app.services.connection_manager import manager
from app.database.database import SessionLocal
from app.models.event import Event

ZONES_PATH = Path(__file__).resolve().parent.parent / "config" / "zones.json"

# In-memory job status store for the MVP. Swap for a DB table or Redis
# once you need this to survive a server restart or scale to workers.
JOB_STATUS = {}

FRAME_DELAY_SECONDS = 0.6  # only affects the mock tracker demo pace


def process_video(job_id: str, video_path: str, use_mock_tracker: bool = True):
    """
    Runs the full pipeline against one video, streaming results live over
    the session's WebSocket while also writing events to the DB.
    Call this via FastAPI's BackgroundTasks, not inline in the request.
    """
    JOB_STATUS[job_id] = {"status": "PROCESSING", "persons_detected": 0, "events_detected": 0}
    manager.send(job_id, {"type": "status", "status": "PROCESSING"})

    zone_engine = ZoneEngine.from_json(ZONES_PATH)
    event_engine = EventEngine()

    db = SessionLocal()
    seen_person_ids = set()
    events_written = 0

    try:
        if use_mock_tracker:
            tracker = MockTrackerService()
            frame_numbers = sorted(tracker.mock_tracks_per_frame.keys())
            frame_iter = (
                (frame_number, tracker.get_tracks_for_frame(frame_number))
                for frame_number in frame_numbers
            )
        else:
            tracker = RealTrackerService(video_path)
            frame_iter = tracker.run()

        for frame_number, tracks in frame_iter:
            persons_payload = []

            for track in tracks:
                person_id = track["track_id"]
                bbox = track["bbox"]
                seen_person_ids.add(person_id)

                zone = zone_engine.get_zone(bbox)
                persons_payload.append({"track_id": person_id, "bbox": bbox, "zone": zone})

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
                    db.flush()  # get the row committed-ish before we broadcast it
                    events_written += 1

                    # Live push: React appends this straight to the event log /
                    # sequence stepper without waiting for the job to finish.
                    manager.send(job_id, {
                        "type": "event",
                        "person_id": event["person_id"],
                        "event_type": event["event"],
                        "zone": event.get("to_zone") or event.get("zone"),
                        "frame_number": event.get("frame_number"),
                        "status": event.get("status", "OK"),
                        "missed_steps": event.get("missed_steps"),
                    })

            # Live push: current bounding boxes + zones for this frame,
            # independent of whether any event fired.
            manager.send(job_id, {
                "type": "frame_result",
                "frame_number": frame_number,
                "persons": persons_payload,
            })

            JOB_STATUS[job_id] = {
                "status": "PROCESSING",
                "persons_detected": len(seen_person_ids),
                "events_detected": events_written,
            }

            if use_mock_tracker:
                time.sleep(FRAME_DELAY_SECONDS)

        db.commit()

        JOB_STATUS[job_id] = {
            "status": "COMPLETED",
            "persons_detected": len(seen_person_ids),
            "events_detected": events_written,
        }
        manager.send(job_id, {
            "type": "status",
            "status": "COMPLETED",
            "persons_detected": len(seen_person_ids),
            "events_detected": events_written,
        })

    except Exception as exc:  # noqa: BLE001 - MVP-level catch-all, tighten later
        db.rollback()
        JOB_STATUS[job_id] = {"status": "FAILED", "error": str(exc)}
        manager.send(job_id, {"type": "status", "status": "FAILED", "error": str(exc)})
        raise

    finally:
        db.close()
