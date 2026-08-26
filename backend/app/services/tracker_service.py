"""
tracker_service.py

Defines the CONTRACT between your teammate's tracking code and your
zone/event pipeline. Whether tracks come from YOLO+ByteTrack,
YOLO+BoT-SORT, or a hand-written mock, they must come out looking like:

    {
        "track_id": int,
        "bbox": [x1, y1, x2, y2],
    }

Use MockTrackerService while your teammate's real tracker isn't ready
yet, then swap in RealTrackerService (or whatever they hand you) without
touching ZoneEngine or EventEngine at all.
"""

from typing import Iterator, List, Dict
import cv2


class MockTrackerService:
    """
    Fake tracker for development. Replace `mock_tracks_per_frame` with
    whatever bounding boxes make sense for testing your own video, or
    generate them programmatically.
    """

    def __init__(self, mock_tracks_per_frame: Dict[int, List[Dict]] = None):
        # frame_number -> list of {"track_id": int, "bbox": [x1,y1,x2,y2]}
        self.mock_tracks_per_frame = mock_tracks_per_frame or {
            0: [{"track_id": 1, "bbox": [120, 220, 260, 480]}],
            50: [{"track_id": 1, "bbox": [300, 380, 500, 580]}],
            100: [{"track_id": 1, "bbox": [550, 420, 750, 640]}],
        }

    def get_tracks_for_frame(self, frame_number: int) -> List[Dict]:
        return self.mock_tracks_per_frame.get(frame_number, [])


class RealTrackerService:
    """
    Skeleton for wiring in your teammate's actual YOLO + tracker.
    Fill in `run` once their code is ready — the important part is that
    it yields (frame_number, tracks) in the same shape MockTrackerService
    produces, so nothing downstream needs to change.
    """

    def __init__(self, video_path: str, model=None):
        self.video_path = video_path
        self.model = model  # e.g. a loaded YOLO model + ByteTrack instance

    def run(self) -> Iterator[tuple]:
        cap = cv2.VideoCapture(self.video_path)
        frame_number = 0

        while True:
            ok, frame = cap.read()
            if not ok:
                break

            # TODO: replace with your teammate's real detection + tracking call
            # tracks = self.model.track(frame)
            tracks = []  # placeholder until the real tracker is plugged in

            yield frame_number, tracks
            frame_number += 1

        cap.release()
