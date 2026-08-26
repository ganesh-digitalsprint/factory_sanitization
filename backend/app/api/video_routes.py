"""
video_routes.py

POST /videos/upload   - upload a video, kick off background processing
GET  /videos/{job_id} - check the status of a processing job
"""

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException

from app.services.video_processor import process_video, JOB_STATUS

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

    # use_mock_tracker=True until your teammate's real tracker is ready —
    # flip to False once RealTrackerService is wired up to their model
    background_tasks.add_task(process_video, job_id, str(video_path), True)

    return {"job_id": job_id, "status": "QUEUED"}


@router.get("/{job_id}")
async def get_job_status(job_id: str):
    status = JOB_STATUS.get(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="job_id not found")
    return {"job_id": job_id, **status}
