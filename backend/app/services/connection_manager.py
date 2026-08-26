"""
connection_manager.py

Manages WebSocket connections per session_id (one video upload = one
session). process_video() runs in a background thread (FastAPI's
BackgroundTasks runs sync functions in a threadpool), so pushing a
message to a websocket - which is async - needs to hop back onto the
main event loop. `manager.send(...)` does that hop for you; call it
from anywhere, sync or async.
"""

import asyncio
from typing import Dict, List, Optional

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """Call once at FastAPI startup so background threads can schedule sends."""
        self.loop = loop

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.setdefault(session_id, []).append(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket):
        conns = self.active_connections.get(session_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self.active_connections.pop(session_id, None)

    async def _send_async(self, session_id: str, message: dict):
        dead = []
        for ws in self.active_connections.get(session_id, []):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(session_id, ws)

    def send(self, session_id: str, message: dict):
        """
        Thread-safe fire-and-forget send. Safe to call from the sync
        background-task thread that runs process_video().
        """
        if session_id not in self.active_connections or self.loop is None:
            return  # no one listening yet, or loop not ready - drop silently
        asyncio.run_coroutine_threadsafe(self._send_async(session_id, message), self.loop)


manager = ConnectionManager()
