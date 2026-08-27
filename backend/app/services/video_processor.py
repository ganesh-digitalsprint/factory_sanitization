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

<<<<<<< HEAD
This is what FastAPI's BackgroundTasks calls after a video is uploaded,
so the /upload request returns immediately instead of blocking for the
whole video's processing time.
"""

import json
=======
This is invoked immediately after a video is uploaded in a background worker thread
(via FastAPI BackgroundTasks), so the HTTP /upload request returns immediately instead of
blocking for the whole video processing time.

As each frame is processed, live frame results (throttled to avoid flooding) and immediate
zone/sanitation events are pushed live over the session's WebSocket AND written to the DB.
"""

import logging
import time
>>>>>>> 136eb9bf99f29001df2f525a4d6f52e51bfee4c5
from pathlib import Path
import cv2

from app.services.zone_engine import ZoneEngine
from app.services.event_engine import EventEngine
from app.services.tracker_service import RealTrackerService, MockTrackerService
from app.database.database import SessionLocal
from app.models.event import Event

logger = logging.getLogger(__name__)

ZONES_PATH = Path(__file__).resolve().parent.parent / "config" / "zones.json"

<<<<<<< HEAD
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
=======
# In-memory session store for tracking processing sessions.
SESSION_STORE = {}
JOB_STATUS = SESSION_STORE  # backward compatibility alias

FRAME_DELAY_SECONDS = 0.2  # pacing delay for mock tracker demo


def process_video(session_id: str, video_path: str, use_mock_tracker: bool = True):
    """
    Runs the full pipeline against one video, streaming results live over
    the session's WebSocket while writing events to the DB.
    Started immediately upon upload in a background thread.
    """
    start_time = time.time()
    logger.info(f"[Session {session_id}] Processing started for video: {video_path}")

    # Inspect video for FPS and frame count if accessible via OpenCV
    fps = 30.0
    total_frames = 100
    try:
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            detected_fps = cap.get(cv2.CAP_PROP_FPS)
            detected_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if detected_fps and detected_fps > 0:
                fps = float(detected_fps)
            if detected_frames and detected_frames > 0:
                total_frames = detected_frames
            cap.release()
    except Exception as e:
        logger.warning(f"[Session {session_id}] Could not inspect video properties: {e}")

    SESSION_STORE[session_id] = {
        "session_id": session_id,
        "video_path": video_path,
        "status": "PROCESSING",
        "progress": 0.0,
        "current_frame": 0,
        "total_frames": total_frames,
        "fps": fps,
        "persons_detected": 0,
        "events_detected": 0,
    }

    # Signal live listeners that processing has started
    manager.send(session_id, {
        "type": "processing_started",
        "session_id": session_id,
    })
>>>>>>> 136eb9bf99f29001df2f525a4d6f52e51bfee4c5

    zone_engine = ZoneEngine.from_json(ZONES_PATH)
    event_engine = EventEngine()

    db = SessionLocal()
    seen_person_ids = set()
    events_written = 0
<<<<<<< HEAD
    frames_written = 0

    tracks_file = open(get_tracks_path(job_id), "w") if save_tracks else None
=======
    processed_frames_count = 0
    last_ws_send_time = 0.0
>>>>>>> 136eb9bf99f29001df2f525a4d6f52e51bfee4c5

    try:
        if use_mock_tracker:
            tracker = MockTrackerService()
<<<<<<< HEAD
            frame_result_iter = _mock_frame_iter(tracker)
=======
            frame_numbers = sorted(tracker.mock_tracks_per_frame.keys())
            if frame_numbers and total_frames <= 100:
                total_frames = max(frame_numbers[-1] + 1, 100)
                SESSION_STORE[session_id]["total_frames"] = total_frames
            frame_iter = (
                (frame_number, tracker.get_tracks_for_frame(frame_number))
                for frame_number in frame_numbers
            )
>>>>>>> 136eb9bf99f29001df2f525a4d6f52e51bfee4c5
        else:
            tracker = RealTrackerService(video_path)
            frame_result_iter = tracker.run_frames()

<<<<<<< HEAD
        for frame_result in frame_result_iter:
            frame_number = frame_result["frame_number"]
            tracks = frame_result["tracks"]

            if tracks_file is not None:
                tracks_file.write(json.dumps(frame_result) + "\n")
                frames_written += 1
=======
        for frame_number, tracks in frame_iter:
            processed_frames_count += 1
            timestamp = round(frame_number / fps, 2)
            progress = round((frame_number / max(total_frames, 1)) * 100, 1)

            persons_payload = []
>>>>>>> 136eb9bf99f29001df2f525a4d6f52e51bfee4c5

            for track in tracks:
                person_id = track["track_id"]
                bbox = track["bbox"]
                seen_person_ids.add(person_id)

                zone = zone_engine.get_zone(bbox)
<<<<<<< HEAD
=======
                persons_payload.append({
                    "track_id": person_id,
                    "bbox": bbox,
                    "zone": zone,
                    "confidence": track.get("confidence", 0.90),
                    "class_name": track.get("class_name", "person"),
                })

>>>>>>> 136eb9bf99f29001df2f525a4d6f52e51bfee4c5
                events = event_engine.process_zone(
                    person_id=person_id,
                    zone=zone,
                    frame_number=frame_number,
<<<<<<< HEAD
                    timestamp=frame_result.get("timestamp"),
=======
                    timestamp=timestamp,
>>>>>>> 136eb9bf99f29001df2f525a4d6f52e51bfee4c5
                )

                for event in events:
                    db_event = Event(
                        job_id=session_id,
                        person_id=str(event["person_id"]),
                        event_type=event["event"],
                        zone=event.get("to_zone") or event.get("zone"),
                        frame_number=event.get("frame_number"),
                        status=event.get("status", "OK"),
                    )
                    db.add(db_event)
<<<<<<< HEAD
                    events_written += 1

        db.commit()

        JOB_STATUS[job_id] = {
            "status": "COMPLETED",
            "persons_detected": len(seen_person_ids),
            "events_detected": events_written,
            "frames_processed": frames_written,
            "tracks_available": tracks_file is not None,
        }
=======
                    db.flush()
                    events_written += 1

                    # IMPORTANT EVENTS: Always send immediately over WebSocket
                    manager.send(session_id, {
                        "type": "event",
                        "session_id": session_id,
                        "person_id": event["person_id"],
                        "event_type": event["event"],
                        "zone": event.get("to_zone") or event.get("zone"),
                        "timestamp": timestamp,
                        "frame_number": frame_number,
                        "status": event.get("status", "OK"),
                        "missed_steps": event.get("missed_steps"),
                    })

            # THROTTLED FRAME RESULTS: Send at most 10 WebSocket updates per second
            now = time.time()
            if now - last_ws_send_time >= 0.1:
                manager.send(session_id, {
                    "type": "frame_result",
                    "session_id": session_id,
                    "frame_number": frame_number,
                    "timestamp": timestamp,
                    "progress": min(progress, 100.0),
                    "persons": persons_payload,
                })
                last_ws_send_time = now

            elapsed_so_far = time.time() - start_time
            live_processing_fps = round(processed_frames_count / elapsed_so_far, 2) if elapsed_so_far > 0 else 0.0

            SESSION_STORE[session_id].update({
                "status": "PROCESSING",
                "progress": min(progress, 99.9),
                "current_frame": frame_number,
                "current_timestamp": timestamp,
                "processing_fps": live_processing_fps,
                "persons_detected": len(seen_person_ids),
                "events_detected": events_written,
            })

            if use_mock_tracker:
                time.sleep(FRAME_DELAY_SECONDS)

        db.commit()

        total_elapsed = time.time() - start_time
        processing_fps = round(processed_frames_count / total_elapsed, 2) if total_elapsed > 0 else 0
        logger.info(
            f"[Session {session_id}] Finished processing. "
            f"Source FPS: {fps}, Processing FPS: {processing_fps}, Total Frames: {processed_frames_count}"
        )

        SESSION_STORE[session_id].update({
            "status": "COMPLETED",
            "progress": 100.0,
            "persons_detected": len(seen_person_ids),
            "events_detected": events_written,
            "processing_fps": processing_fps,
        })
>>>>>>> 136eb9bf99f29001df2f525a4d6f52e51bfee4c5

        manager.send(session_id, {
            "type": "processing_completed",
            "session_id": session_id,
            "progress": 100.0,
        })

    except Exception as exc:
        db.rollback()
<<<<<<< HEAD
        JOB_STATUS[job_id] = {"status": "FAILED", "error": str(exc)}
=======
        logger.exception(f"[Session {session_id}] Processing failed: {exc}")
        SESSION_STORE[session_id].update({
            "status": "FAILED",
            "error": str(exc),
        })
        manager.send(session_id, {
            "type": "processing_error",
            "session_id": session_id,
            "message": str(exc),
        })
>>>>>>> 136eb9bf99f29001df2f525a4d6f52e51bfee4c5
        raise

    finally:
        db.close()
<<<<<<< HEAD
        if tracks_file is not None:
            tracks_file.close()
=======

>>>>>>> 136eb9bf99f29001df2f525a4d6f52e51bfee4c5
