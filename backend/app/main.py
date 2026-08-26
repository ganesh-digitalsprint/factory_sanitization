"""
main.py

FastAPI application entrypoint.

Run with:
    uvicorn app.main:app --reload
from inside the backend/ directory.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.database import init_db
from app.api import video_routes, event_routes

app = FastAPI(title="Sanitation Monitoring API")

# Allow the React dev server to call this API during development.
# Tighten this list once you deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(video_routes.router)
app.include_router(event_routes.router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/")
async def root():
    return {"status": "ok", "service": "sanitation-monitoring-api"}
