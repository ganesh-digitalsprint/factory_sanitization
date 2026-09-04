"""
test_concurrent_writes.py

Stress tests concurrent video processing threads pushing events to db_writer,
ensuring SQLite WAL mode and the single-threaded queue prevent database locking.
"""

import threading
import time

from app.database.database import init_db, SessionLocal
from app.services.db_writer import start_db_writer, stop_db_writer, enqueue_event
from app.models.event import Event


def simulate_processing_worker(worker_id: int, num_events: int = 50):
    job_id = f"concurrent_job_{worker_id}"
    for i in range(num_events):
        enqueue_event({
            "job_id": job_id,
            "person_id": str(worker_id),
            "event_type": "ZONE_CHANGED",
            "zone": "CUPBOARD_INTERACTION_ZONE",
            "frame_number": i,
            "status": "OK",
            "confidence": 0.95,
        })
        time.sleep(0.01)


def main():
    print("1. Initializing DB and starting DB Writer thread...")
    init_db()
    start_db_writer()

    num_workers = 10
    events_per_worker = 50
    threads = []

    print(f"2. Launching {num_workers} concurrent processing threads ({num_workers * events_per_worker} total events)...")
    start_time = time.time()

    for w in range(num_workers):
        t = threading.Thread(target=simulate_processing_worker, args=(w, events_per_worker))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print("3. Processing threads complete. Stopping DB Writer and waiting for queue flush...")
    stop_db_writer()
    elapsed = round(time.time() - start_time, 2)

    db = SessionLocal()
    try:
        total_in_db = db.query(Event).filter(Event.job_id.like("concurrent_job_%")).count()
        expected = num_workers * events_per_worker
        print(f"4. DB Check: Persisted {total_in_db}/{expected} events in {elapsed}s.")
        assert total_in_db == expected, f"Expected {expected} events in DB, found {total_in_db}"
        print("[SUCCESS] Concurrent multi-threaded write test passed with 0 database lock errors!")
    finally:
        db.close()


if __name__ == "__main__":
    main()
