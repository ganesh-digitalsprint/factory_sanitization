"""
video_routes.py

POST /api/v1/videos/upload
    Upload full video and immediately start background processing.

GET /api/v1/videos/{session_id}
    Get current processing status.

WS /api/v1/videos/{session_id}/stream
    Receive live AI processing results.
"""

from filelock import asyncio
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

UPLOAD_DIR = (
    Path(__file__).resolve().parent.parent.parent / "uploads"
)

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload")
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """
    Upload the complete video file.

    The video is saved first, then a processing session is
    created and processing starts immediately in the background.

    The API does NOT wait for the entire video processing to finish.
    """

    # -----------------------------
    # 1. Validate file
    # -----------------------------
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename missing in uploaded video file",
        )

    # Optional basic validation
    allowed_extensions = {
        ".mp4",
        ".avi",
        ".mov",
        ".mkv",
        ".webm",
    }

    extension = Path(file.filename).suffix.lower()

    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported video format: {extension}",
        )

    # -----------------------------
    # 2. Generate session ID
    # -----------------------------
    session_id = str(uuid.uuid4())

    video_path = (
        UPLOAD_DIR /
        f"{session_id}{extension}"
    )

    # -----------------------------
    # 3. Save complete uploaded video
    # -----------------------------
    try:
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save video: {str(exc)}",
        )

    # -----------------------------
    # 4. Create processing session
    # -----------------------------
    SESSION_STORE[session_id] = {
        "session_id": session_id,
        "video_path": str(video_path),

        "status": "PROCESSING",

        "progress": 0.0,

        "current_frame": 0,
        "current_timestamp": 0.0,

        "total_frames": 0,
        "fps": 0.0,

        "processing_fps": 0.0,

        "persons_detected": 0,
        "events_detected": 0,
    }

    # -----------------------------
    # 5. Start processing immediately
    # -----------------------------
    background_tasks.add_task(
        process_video,
        session_id,
        str(video_path),
        True,
    )

    # -----------------------------
    # 6. Return immediately
    # -----------------------------
    return {
        "session_id": session_id,
        "status": "PROCESSING",
        "message": "Video uploaded and processing started",
    }


@router.get("/{session_id}")
async def get_session_status(session_id: str):

    session = SESSION_STORE.get(session_id)

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="session_id not found",
        )

    return session


@router.websocket("/{session_id}/stream")
async def video_stream(
    websocket: WebSocket,
    session_id: str,
):
    session = SESSION_STORE.get(session_id)

    if session is None:
        await websocket.close(code=1008)
        return

    await manager.connect(session_id, websocket)

    try:
        await websocket.send_json({
            "type": "processing_started",
            "session_id": session_id,
            "status": session.get("status", "PROCESSING"),
        })

        # Keep connection open while processing
        while True:
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)

    except Exception:
        manager.disconnect(session_id, websocket)