"""
video_routes.py

POST /videos/upload          - upload a video, kick off background processing
GET  /videos/{job_id}        - check the status of a processing job
GET  /videos/{job_id}/tracks - raw per-frame tracker output for that job,
                                 in the exact shape RealTrackerService
                                 produces:
                                 {"frame_number": 1250, "timestamp": 41.67,
                                  "tracks": [{"track_id": 101,
                                              "class_name": "person",
                                              "bbox": [320, 210, 470, 700],
                                              "confidence": 0.91}]}
"""

import json
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException

from app.services.video_processor import process_video, JOB_STATUS, get_tracks_path

router = APIRouter(prefix="/videos", tags=["videos"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


@router.post("/upload")
async def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())
    video_path = UPLOAD_DIR / f"{job_id}_{file.filename}"

    with open(video_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    JOB_STATUS[job_id] = {"status": "QUEUED"}

    # use_mock_tracker=True until you're ready to run the real YOLO+ByteTrack
    # pipeline — flip to False to use RealTrackerService.
    background_tasks.add_task(process_video, job_id, str(video_path), True)

    return {"job_id": job_id, "status": "QUEUED"}


@router.get("/{job_id}")
async def get_job_status(job_id: str):
    status = JOB_STATUS.get(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="job_id not found")
    return {"job_id": job_id, **status}


@router.get("/{job_id}/tracks")
async def get_job_tracks(
    job_id: str,
    frame_number: Optional[int] = None,
    limit: int = 500,
    offset: int = 0,
):
    """
    Returns the raw per-frame tracker output saved during processing.

    - No query params: returns up to `limit` frame records starting at `offset`.
    - `frame_number=<n>`: returns just that one frame's record.

    Each record looks like:
        {"frame_number": 1250, "timestamp": 41.67,
         "tracks": [{"track_id": 101, "class_name": "person",
                     "bbox": [320, 210, 470, 700], "confidence": 0.91}]}
    """
    status = JOB_STATUS.get(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="job_id not found")

    tracks_path = get_tracks_path(job_id)
    if not tracks_path.exists():
        raise HTTPException(
            status_code=404,
            detail="No per-frame track data saved for this job (was save_tracks=False, "
                   "or is the job still processing?)",
        )

    if frame_number is not None:
        with open(tracks_path) as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                if record["frame_number"] == frame_number:
                    return record
        raise HTTPException(status_code=404, detail=f"frame_number {frame_number} not found")

    records = []
    with open(tracks_path) as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    return records[offset: offset + limit]