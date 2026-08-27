"""
video_routes.py

POST /videos/upload   - upload a video, kick off background processing
GET  /videos/{job_id} - check the status of a processing job
"""

import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException

from app.services.video_processor import process_video, JOB_STATUS
from app.services.connection_manager import manager

router = APIRouter(prefix="/videos", tags=["videos"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


@router.post("/upload")
async def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    1. Validate uploaded video.
    2. Generate unique session_id.
    3. Save uploaded video file.
    4. Create processing session directly with status "PROCESSING" (No QUEUED state).
    5. Immediately start video processing in background.
    6. Return session_id immediately.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename missing in uploaded video file")

    session_id = str(uuid.uuid4())
    video_path = UPLOAD_DIR / f"{session_id}_{file.filename}"

    with open(video_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    JOB_STATUS[job_id] = {"status": "QUEUED"}

    # use_mock_tracker=True until your teammate's real tracker is ready —
    # flip to False once RealTrackerService is wired up to their model
    background_tasks.add_task(process_video, job_id, str(video_path), True)

    return {
        "session_id": session_id,
        "job_id": session_id,
        "status": "PROCESSING",
        "message": "Video uploaded and processing started",
    }


@router.get("/{session_id}")
async def get_session_status(session_id: str):
    session = SESSION_STORE.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session_id not found")
    return session


@router.get("/{job_id}/tracks")
async def get_job_tracks(
    job_id: str,
    frame_number: Optional[int] = None,
    limit: int = 500,
    offset: int = 0,
):
    """
    Live channel for one processing session. The video itself is NOT sent
    over this socket - React plays the uploaded file directly via <video>.
    This only carries AI results: track_id + bbox + zone per frame, plus
    zone-change / missed-step events, as process_video() produces them.
    """
    await manager.connect(session_id, websocket)
    await websocket.send_json({"type": "test", "message": "WebSocket connected"})

    try:
        # We don't expect the client to send anything meaningful back, but
        # we still need to await something to detect disconnects promptly.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)
