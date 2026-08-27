"""
video_routes.py

POST /api/v1/videos/upload          - upload a video, start background processing immediately
GET  /api/v1/videos/{session_id}     - check the session status
WS   /api/v1/videos/{session_id}/stream - live AI results stream
"""

import shutil
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    BackgroundTasks,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)

from app.services.video_processor import process_video, SESSION_STORE
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

    # Initialize session directly in PROCESSING state (no waiting/queued state)
    SESSION_STORE[session_id] = {
        "session_id": session_id,
        "job_id": session_id,
        "video_path": str(video_path),
        "status": "PROCESSING",
        "progress": 0.0,
        "current_frame": 0,
        "current_timestamp": 0.0,
        "total_frames": 0,
        "fps": 30.0,
        "processing_fps": 0.0,
        "persons_detected": 0,
        "events_detected": 0,
    }

    # Start processing task immediately in the background
    background_tasks.add_task(process_video, session_id, str(video_path), True)

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


@router.websocket("/{session_id}/stream")
async def video_stream(websocket: WebSocket, session_id: str):
    """
    Live channel for one processing session.
    Carries live AI processing results: frame_result (track_id + bbox + zone),
    plus zone-change and sequence completed events.
    """
    await manager.connect(session_id, websocket)

    # Send initial processing_started message upon connection
    session = SESSION_STORE.get(session_id)
    initial_status = session.get("status", "PROCESSING") if session else "PROCESSING"
    await websocket.send_json({
        "type": "processing_started",
        "session_id": session_id,
        "status": initial_status,
    })

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)

