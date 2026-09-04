"""
db_writer.py

Single-threaded background worker for persisting events to SQLite.
Every processing thread enqueues events here instead of writing directly to SQLite,
preventing database locking issues while serving fast in-memory reads for live views.
"""

import logging
import queue
import threading
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any, Optional

from app.database.database import SessionLocal
from app.models.event import Event

logger = logging.getLogger(__name__)

# In-memory store: job_id -> list of event dicts
_IN_MEMORY_EVENTS: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
_memory_lock = threading.Lock()

# Queue & thread control
_db_queue: queue.Queue = queue.Queue()
_writer_thread: Optional[threading.Thread] = None
_running: bool = False


def enqueue_event(event_data: Dict[str, Any]) -> None:
    """
    Called by video_processor to drop an event into memory instantly
    and queue it for background SQLite persistence.
    """
    job_id = event_data.get("job_id")
    if not job_id:
        logger.error("Attempted to enqueue event without job_id: %s", event_data)
        return

    # Add default timestamp if missing
    if "created_at" not in event_data or event_data["created_at"] is None:
        event_data["created_at"] = datetime.utcnow()

    # Instant in-memory write
    with _memory_lock:
        _IN_MEMORY_EVENTS[job_id].append(event_data)

    # Queue for background DB writer thread
    _db_queue.put(event_data)


def get_in_memory_events(job_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Returns in-memory events for job_id if present, else None.
    """
    with _memory_lock:
        if job_id in _IN_MEMORY_EVENTS:
            return list(_IN_MEMORY_EVENTS[job_id])
    return None


def _db_writer_worker() -> None:
    """
    Dedicated worker loop owning all SQLite write operations.
    """
    global _running
    logger.info("DB Writer thread started.")

    while _running or not _db_queue.empty():
        batch = []
        try:
            # Block briefly waiting for an item
            item = _db_queue.get(timeout=0.5)
            batch.append(item)
            _db_queue.task_done()

            # Drain any additional pending items up to batch size 50
            while len(batch) < 50:
                try:
                    next_item = _db_queue.get_nowait()
                    batch.append(next_item)
                    _db_queue.task_done()
                except queue.Empty:
                    break

        except queue.Empty:
            continue

        if not batch:
            continue

        db = SessionLocal()
        try:
            for data in batch:
                event_obj = Event(
                    job_id=data.get("job_id"),
                    person_id=str(data.get("person_id")),
                    event_type=data.get("event_type"),
                    zone=data.get("zone"),
                    frame_number=data.get("frame_number"),
                    status=data.get("status", "OK"),
                    confidence=data.get("confidence"),
                    created_at=data.get("created_at"),
                )
                db.add(event_obj)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.exception("Error writing event batch to SQLite: %s", exc)
        finally:
            db.close()

    logger.info("DB Writer thread stopped.")


def start_db_writer() -> None:
    """
    Starts the single-threaded DB writer daemon thread.
    """
    global _writer_thread, _running
    if _running and _writer_thread and _writer_thread.is_alive():
        return

    _running = True
    _writer_thread = threading.Thread(target=_db_writer_worker, daemon=True, name="DBWriterThread")
    _writer_thread.start()


def stop_db_writer() -> None:
    """
    Stops the DB writer thread cleanly after draining the queue.
    """
    global _running, _writer_thread
    _running = False
    if _writer_thread and _writer_thread.is_alive():
        _writer_thread.join(timeout=5.0)
