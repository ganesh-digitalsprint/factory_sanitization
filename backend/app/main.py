"""
main.py

FastAPI application entrypoint.

Run with:
    uvicorn app.main:app --reload
from inside the backend/ directory.
"""

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.database import init_db
from app.api import video_routes, event_routes
from app.services.connection_manager import manager
from app.services.db_writer import start_db_writer, stop_db_writer

app = FastAPI(title="Sanitation Monitoring API")

# Allow the React dev server to call this API during development.
# Tighten this list once you deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local MVP development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Primary API v1 routes
app.include_router(video_routes.router, prefix="/api/v1")
app.include_router(event_routes.router, prefix="/api/v1")


@app.on_event("startup")
async def on_startup():
    init_db()
    start_db_writer()
    # process_video() runs in a worker thread (BackgroundTasks), so the
    # connection manager needs a reference to the main event loop to be
    # able to schedule WebSocket sends from that thread.
    manager.set_loop(asyncio.get_event_loop())


@app.on_event("shutdown")
async def on_shutdown():
    stop_db_writer()


@app.get("/")
async def root():
    return {"status": "ok", "service": "sanitation-monitoring-api"}

