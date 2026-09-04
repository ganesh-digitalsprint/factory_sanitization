"""
test_api_flow.py

End-to-end test for FastAPI video upload and background processing flow.
"""

import asyncio
import time
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.services.video_processor import SESSION_STORE

client = TestClient(app)

def test_video_upload_and_processing():
    
    # Create a small dummy video file for testing
    test_video_path = Path("test_sample.mp4")
    test_video_path.write_bytes(b"dummy video content for unit testing")
    
    try:
        with open(test_video_path, "rb") as f:
            response = client.post(
                "/api/v1/videos/upload",
                files={"file": ("test_sample.mp4", f, "video/mp4")},
                data={"use_mock_tracker": "true"}
            )
        
        assert response.status_code == 200, f"Upload failed: {response.text}"

        data = response.json()
        print("Upload Response:", data)
        
        assert "job_id" in data
        assert data["status"] == "PROCESSING"
        
        session_id = data["job_id"]
        
        print(f"\n2. Testing GET /api/v1/videos/{session_id} immediately after upload...")
        status_res = client.get(f"/api/v1/videos/{session_id}")
        assert status_res.status_code == 200
        session_data = status_res.json()
        print("Session State:", session_data)
        assert session_data["status"] in ["PROCESSING", "COMPLETED"]
        
        print("\n3. Waiting for background processing to progress...")
        time.sleep(2.0)
        
        final_res = client.get(f"/api/v1/videos/{session_id}")
        final_data = final_res.json()
        print("Updated Session State:", final_data)
        assert final_data["status"] in ["PROCESSING", "COMPLETED"]

        print("\n4. Testing GET /api/v1/events/{session_id}...")
        events_res = client.get(f"/api/v1/events/{session_id}")
        assert events_res.status_code == 200
        events_data = events_res.json()
        print("Events fetched:", len(events_data))
        
        print("\n5. Testing WebSocket connection...")
        with client.websocket_connect(f"/api/v1/videos/{session_id}/stream") as websocket:
            ws_data = websocket.receive_json()
            print("Received initial WS message:", ws_data)
            assert ws_data["type"] == "test"


            
        print("\n[SUCCESS] End-to-End API & Background Processing tests passed successfully!")
        
    finally:
        if test_video_path.exists():
            test_video_path.unlink()

if __name__ == "__main__":
    test_video_upload_and_processing()
