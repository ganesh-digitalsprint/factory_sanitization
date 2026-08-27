"""
video_processor.py

Ties the pipeline together for one uploaded video:

    Tracker  ->  ZoneEngine  ->  EventEngine  ->  Event Store (DB)
                     |
                     +--> raw per-frame tracks also saved to disk as
                          JSONL, one JSON object per line, in the exact
                          shape RealTrackerService.run_frames() produces:

                          {"frame_number": 1250, "timestamp": 41.67,
                           "tracks": [{"track_id": 101, "class_name": "person",
                                       "bbox": [320, 210, 470, 700],
                                       "confidence": 0.91}]}

This is what FastAPI's BackgroundTasks calls after a video is uploaded,
so the /upload request returns immediately instead of blocking for the
whole video's processing time.
"""

import json
from pathlib import Path

from app.services.zone_engine import ZoneEngine
from app.services.event_engine import EventEngine
from app.services.tracker_service import RealTrackerService, MockTrackerService
from app.database.database import SessionLocal
from app.models.event import Event

ZONES_PATH = Path(__file__).resolve().parent.parent / "config" / "zones.json"

# Where raw per-frame track JSONL files get written, one file per job:
# uploads/tracks/{job_id}.jsonl
TRACKS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "tracks"
TRACKS_DIR.mkdir(parents=True, exist_ok=True)

# In-memory job status store for the MVP. Swap for a DB table or Redis
# once you need this to survive a server restart or scale to workers.
JOB_STATUS = {}


def get_tracks_path(job_id: str) -> Path:
    """Path to the raw per-frame tracks JSONL file for a given job."""
    return TRACKS_DIR / f"{job_id}.jsonl"


def _mock_frame_iter(tracker: MockTrackerService, frame_rate: int = 25):
    """Wraps MockTrackerService in the same per-frame dict shape RealTrackerService.run_frames() uses."""
    for frame_number in sorted(tracker.mock_tracks_per_frame.keys()):
        yield {
            "frame_number": frame_number,
            "timestamp": round(frame_number / frame_rate, 2),
            "tracks": tracker.get_tracks_for_frame(frame_number),
        }


def process_video(
    job_id: str,
    video_path: str,
    use_mock_tracker: bool = True,
    save_tracks: bool = True,
):
    """
    Runs the full pipeline against one video, writes derived events to the
    DB, and (if save_tracks=True) writes every raw per-frame tracker
    output to uploads/tracks/{job_id}.jsonl so it can be fetched later via
    GET /videos/{job_id}/tracks.

    Call this via FastAPI's BackgroundTasks, not inline in the request.
    """
    JOB_STATUS[job_id] = {"status": "PROCESSING", "persons_detected": 0, "events_detected": 0}

    zone_engine = ZoneEngine.from_json(ZONES_PATH)
    event_engine = EventEngine()

    db = SessionLocal()
    seen_person_ids = set()
    events_written = 0
    frames_written = 0

    tracks_file = open(get_tracks_path(job_id), "w") if save_tracks else None

    try:
        if use_mock_tracker:
            tracker = MockTrackerService()
            frame_result_iter = _mock_frame_iter(tracker)
        else:
            tracker = RealTrackerService(video_path)
            frame_result_iter = tracker.run_frames()

        for frame_result in frame_result_iter:
            frame_number = frame_result["frame_number"]
            tracks = frame_result["tracks"]

            if tracks_file is not None:
                tracks_file.write(json.dumps(frame_result) + "\n")
                frames_written += 1

            for track in tracks:
                person_id = track["track_id"]
                bbox = track["bbox"]
                seen_person_ids.add(person_id)

                zone = zone_engine.get_zone(bbox)
                events = event_engine.process_zone(
                    person_id=person_id,
                    zone=zone,
                    frame_number=frame_number,
                    timestamp=frame_result.get("timestamp"),
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
            "frames_processed": frames_written,
            "tracks_available": tracks_file is not None,
        }

    except Exception as exc:  # noqa: BLE001 - MVP-level catch-all, tighten later
        db.rollback()
        JOB_STATUS[job_id] = {"status": "FAILED", "error": str(exc)}
        raise

    finally:
        db.close()
        if tracks_file is not None:
            tracks_file.close()