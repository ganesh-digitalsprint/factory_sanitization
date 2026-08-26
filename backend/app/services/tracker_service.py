"""
tracker_service.py

Defines the CONTRACT between the tracking code and the zone/event
pipeline (see ``video_processor.py``). Regardless of the tracker
implementation, tracks come out looking like:

    {
        "track_id": int | str,
        "class_name": str,
        "bbox": [x1, y1, x2, y2],
        "confidence": float,
    }

``RealTrackerService.run()`` still yields ``(frame_number, tracks)`` tuples —
exactly what ``video_processor.py`` already expects, so nothing else in
this project needs to change.

``RealTrackerService`` now wraps the full pipeline that used to live in the
Colab notebook (``Food_sanitization_yolo10_bt.ipynb``):

    YOLOv10 (Ultralytics) person detection
        -> ROI / reflective-surface filtering        (optional, off by default)
        -> ByteTrack (supervision) short-term tracking
        -> OSNet (torchreid) Re-ID embeddings         (optional, on by default)
        -> GlobalIdentityManager (appearance-based, long-term identity)

The GlobalIdentityManager is what gives you the "fixed id" behaviour from
the Colab notebook: ByteTrack alone will hand out a new tracker_id any time
a person is briefly occluded or leaves/re-enters frame. GlobalIdentityManager
re-attaches a stable "Person_XX" id by comparing OSNet appearance embeddings
against a rolling gallery, the same way the notebook did.

If the optional Re-ID dependencies (torch / torchreid) aren't installed,
RealTrackerService degrades gracefully to plain ByteTrack ids instead of
crashing (see ``use_reid``) — useful for environments where you only need
short-term tracking and want to skip the heavy Re-ID install.

For the exact per-frame JSON payload you want
(``{"frame_number":..., "timestamp":..., "tracks": [...]}``), iterate
``RealTrackerService.run_frames()`` instead of ``run()``.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional / heavy dependencies.
#
# Imported lazily and defensively so that:
#   - MockTrackerService keeps working with zero extra dependencies
#   - RealTrackerService degrades gracefully (raw ByteTrack ids, no Re-ID)
#     if torch/torchreid aren't installed, instead of blowing up on import
# ---------------------------------------------------------------------------

try:
    from ultralytics import YOLO
except ImportError:  # pragma: no cover
    YOLO = None
    logger.warning("ultralytics not installed — RealTrackerService will not be able to detect people.")

try:
    import supervision as sv
except ImportError:  # pragma: no cover
    sv = None
    logger.warning("supervision not installed — RealTrackerService cannot run ByteTrack.")

try:
    import torch
except ImportError:  # pragma: no cover
    torch = None

try:
    from torchreid.reid.utils import FeatureExtractor
except ImportError:  # pragma: no cover
    FeatureExtractor = None
    logger.info(
        "torchreid not installed — RealTrackerService will fall back to raw ByteTrack "
        "ids only (no long-term Re-ID identity)."
    )


class MockTrackerService:
    """
    Fake tracker for development/testing without a GPU or model weights.
    Replace `mock_tracks_per_frame` with whatever bounding boxes make sense
    for testing your own video, or generate them programmatically.
    """

    def __init__(self, mock_tracks_per_frame: Dict[int, List[Dict]] = None):
        # frame_number -> list of track dicts (same shape RealTrackerService produces)
        self.mock_tracks_per_frame = mock_tracks_per_frame or {
            0: [{"track_id": 1, "class_name": "person", "bbox": [120, 220, 260, 480], "confidence": 0.95}],
            50: [{"track_id": 1, "class_name": "person", "bbox": [300, 380, 500, 580], "confidence": 0.93}],
            100: [{"track_id": 1, "class_name": "person", "bbox": [550, 420, 750, 640], "confidence": 0.90}],
        }

    def get_tracks_for_frame(self, frame_number: int) -> List[Dict]:
        return self.mock_tracks_per_frame.get(frame_number, [])


# ---------------------------------------------------------------------------
# Detection filtering
# (ported from the Colab notebook's "ROI and reflection configuration" +
#  "Geometry functions" cells).
# ---------------------------------------------------------------------------

@dataclass
class DetectionFilterConfig:
    """Tunable knobs for filtering raw YOLO boxes before they reach ByteTrack."""

    conf_threshold: float = 0.30
    min_person_height: int = 40
    min_person_area: int = 1500

    # Valid-person ROI polygon (e.g. exclude ceiling/background). Off by
    # default because it's scene-specific — pass roi_polygon + use_roi_filter=True
    # once you know your camera's frame coordinates (see zones.json for the
    # analogous per-zone polygons).
    use_roi_filter: bool = False
    roi_polygon: Optional[np.ndarray] = None  # Nx2 int array

    # Reflective-surface rejection (e.g. stainless steel panels producing
    # a mirrored "ghost" detection). Also scene-specific and off by default.
    use_reflection_filter: bool = False
    reflection_polygons: List[np.ndarray] = field(default_factory=list)


def _point_inside_polygon(point: Tuple[float, float], polygon: np.ndarray) -> bool:
    return cv2.pointPolygonTest(polygon, (float(point[0]), float(point[1])), False) >= 0


def _bbox_bottom_center(bbox) -> Tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return (x1 + x2) / 2.0, y2


def is_valid_detection(bbox, confidence: float, config: DetectionFilterConfig) -> bool:
    """Mirrors `valid_detection()` from the Colab notebook."""
    x1, y1, x2, y2 = bbox
    width, height = x2 - x1, y2 - y1
    area = width * height

    if confidence < config.conf_threshold:
        return False
    if height < config.min_person_height:
        return False
    if area < config.min_person_area:
        return False

    bottom_center = _bbox_bottom_center(bbox)

    if config.use_roi_filter and config.roi_polygon is not None:
        if not _point_inside_polygon(bottom_center, config.roi_polygon):
            return False

    if config.use_reflection_filter:
        for polygon in config.reflection_polygons:
            if _point_inside_polygon(bottom_center, polygon):
                return False

    return True


# ---------------------------------------------------------------------------
# Re-ID helpers (ported from the Colab notebook's "Re-ID utility functions").
# ---------------------------------------------------------------------------

def _l2_normalize(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32)
    norm = np.linalg.norm(vector)
    return vector if norm < 1e-12 else vector / norm


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(_l2_normalize(a), _l2_normalize(b)))


def _crop_person(frame: np.ndarray, bbox) -> Optional[np.ndarray]:
    x1, y1, x2, y2 = bbox
    h, w = frame.shape[:2]
    x1, y1 = max(0, int(x1)), max(0, int(y1))
    x2, y2 = min(w, int(x2)), min(h, int(y2))
    if x2 <= x1 or y2 <= y1:
        return None
    crop = frame[y1:y2, x1:x2]
    return crop if crop.size else None


def _extract_reid_embedding(extractor, crop: Optional[np.ndarray]) -> Optional[np.ndarray]:
    if extractor is None or crop is None:
        return None
    if crop.shape[0] < 50 or crop.shape[1] < 30:
        return None
    try:
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        features = extractor([rgb])
        return _l2_normalize(features[0].cpu().numpy())
    except Exception as exc:  # noqa: BLE001 - keep tracking alive even if Re-ID hiccups
        logger.warning("Re-ID embedding extraction failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# GlobalIdentityManager
# Ported near-verbatim from the Colab notebook's "Global Identity Manager"
# cell. Gives ByteTrack's short-lived track ids a stable, appearance-based
# identity that survives brief occlusion / re-entry into frame.
# ---------------------------------------------------------------------------

class GlobalIdentityManager:
    def __init__(
        self,
        expected_persons: Optional[int] = None,
        match_threshold: float = 0.70,
        max_memory_frames: int = 1500,
        max_embeddings: int = 30,
        min_track_frames_for_id: int = 10,
    ):
        # None => uncapped: keep minting new global identities as new people
        # appear. Set a number (like the notebook's EXPECTED_PERSONS=8) if
        # you know the exact headcount for a given camera/shift.
        self.expected_persons = expected_persons if expected_persons is not None else math.inf
        self.match_threshold = match_threshold
        self.max_memory_frames = max_memory_frames
        self.max_embeddings = max_embeddings
        self.min_track_frames_for_id = min_track_frames_for_id

        self.persons: Dict[str, dict] = {}
        self.track_states: Dict[int, str] = {}
        self.next_person_number = 1

    def create_person(self, track_id, embedding, frame_number, bbox) -> Optional[str]:
        if len(self.persons) >= self.expected_persons:
            return None

        person_id = f"Person_{self.next_person_number:02d}"
        self.next_person_number += 1

        self.persons[person_id] = {
            "embeddings": deque(maxlen=self.max_embeddings),
            "last_seen": frame_number,
            "last_bbox": bbox,
            "active_track": track_id,
            "status": "ACTIVE",
            "track_ids": set(),
        }
        if embedding is not None:
            self.persons[person_id]["embeddings"].append(embedding)
        self.persons[person_id]["track_ids"].add(track_id)
        return person_id

    def person_similarity(self, person_id, embedding) -> float:
        if embedding is None:
            return 0.0
        gallery = self.persons[person_id]["embeddings"]
        if not gallery:
            return 0.0
        return float(max(_cosine_similarity(embedding, g) for g in gallery))

    def find_best_person(self, embedding, frame_number, used_person_ids=None):
        used_person_ids = used_person_ids or set()
        candidates = []

        for person_id, data in self.persons.items():
            if person_id in used_person_ids:
                continue
            if frame_number - data["last_seen"] > self.max_memory_frames:
                continue
            candidates.append((self.person_similarity(person_id, embedding), person_id))

        if not candidates:
            return None, 0.0

        candidates.sort(reverse=True)
        best_similarity, best_person = candidates[0]
        if best_similarity >= self.match_threshold:
            return best_person, best_similarity
        return None, best_similarity

    def assign(self, track_id, embedding, frame_number, bbox, track_age, used_person_ids=None):
        used_person_ids = used_person_ids if used_person_ids is not None else set()

        # Track already bound to a global identity.
        if track_id in self.track_states:
            person_id = self.track_states[track_id]
            if person_id in self.persons:
                data = self.persons[person_id]
                data["last_seen"] = frame_number
                data["last_bbox"] = bbox
                data["active_track"] = track_id
                data["status"] = "ACTIVE"
                data["track_ids"].add(track_id)
                return person_id, 1.0

        # Try appearance-based re-identification.
        if embedding is not None and track_age >= self.min_track_frames_for_id:
            person_id, similarity = self.find_best_person(embedding, frame_number, used_person_ids)
            if person_id is not None:
                self.track_states[track_id] = person_id
                data = self.persons[person_id]
                data["last_seen"] = frame_number
                data["last_bbox"] = bbox
                data["active_track"] = track_id
                data["status"] = "ACTIVE"
                data["track_ids"].add(track_id)
                data["embeddings"].append(embedding)
                return person_id, similarity

        # New global identity.
        if (
            embedding is not None
            and track_age >= self.min_track_frames_for_id
            and len(self.persons) < self.expected_persons
        ):
            person_id = self.create_person(track_id, embedding, frame_number, bbox)
            if person_id is not None:
                self.track_states[track_id] = person_id
                return person_id, 1.0

        return "UNKNOWN", 0.0

    def update_lost_states(self, active_person_ids, frame_number):
        for person_id, data in self.persons.items():
            if person_id in active_person_ids:
                data["status"] = "ACTIVE"
            elif frame_number - data["last_seen"] <= self.max_memory_frames:
                data["status"] = "LOST"
            else:
                data["status"] = "EXPIRED"


# ---------------------------------------------------------------------------
# RealTrackerService
# ---------------------------------------------------------------------------

class RealTrackerService:
    """
    YOLOv10 + ByteTrack (+ optional OSNet Re-ID) tracker.

    Contract used by video_processor.py (unchanged):

        tracker = RealTrackerService(video_path)
        for frame_number, tracks in tracker.run():
            ...  # track["track_id"], track["bbox"], plus now
                 # track["class_name"], track["confidence"] too

    New: exact per-frame JSON payload you asked for:

        tracker = RealTrackerService(video_path)
        for frame_result in tracker.run_frames():
            # {"frame_number": 1250, "timestamp": 41.67,
            #  "tracks": [{"track_id": 101, "class_name": "person",
            #              "bbox": [320, 210, 470, 700], "confidence": 0.91}]}
            ...
    """

    PERSON_CLASS_ID = 0  # COCO "person"

    def __init__(
        self,
        video_path: str,
        model=None,
        *,
        model_name: str = "yolov10m.pt",
        device: Optional[str] = None,
        person_class_id: int = PERSON_CLASS_ID,
        # --- Detection filtering ------------------------------------
        conf_threshold: float = 0.30,
        min_person_height: int = 40,
        min_person_area: int = 1500,
        use_roi_filter: bool = False,
        roi_polygon: Optional[List[List[int]]] = None,
        use_reflection_filter: bool = False,
        reflection_polygons: Optional[List[List[List[int]]]] = None,
        # --- ByteTrack -------------------------------------------------
        track_activation_threshold: float = 0.25,
        lost_track_buffer: int = 150,
        minimum_matching_threshold: float = 0.80,
        frame_rate: int = 25,
        # --- Re-ID / global identity ------------------------------------
        use_reid: bool = True,
        expected_persons: Optional[int] = None,
        reid_match_threshold: float = 0.70,
        max_embeddings_per_person: int = 30,
        embedding_update_interval: int = 10,
        min_track_frames_for_id: int = 10,
        global_memory_frames: Optional[int] = None,
    ):
        self.video_path = video_path
        self.device = device or ("cuda" if (torch is not None and torch.cuda.is_available()) else "cpu")
        self.person_class_id = person_class_id
        self.conf_threshold = conf_threshold
        self.frame_rate = frame_rate
        self.embedding_update_interval = embedding_update_interval

        self.filter_config = DetectionFilterConfig(
            conf_threshold=conf_threshold,
            min_person_height=min_person_height,
            min_person_area=min_person_area,
            use_roi_filter=use_roi_filter,
            roi_polygon=np.array(roi_polygon, dtype=np.int32) if roi_polygon else None,
            use_reflection_filter=use_reflection_filter,
            reflection_polygons=[np.array(p, dtype=np.int32) for p in (reflection_polygons or [])],
        )

        # --- Detector ---------------------------------------------------
        if model is not None:
            self.model = model
        elif YOLO is not None:
            self.model = YOLO(model_name)
        else:
            self.model = None
            logger.error("ultralytics is not installed — RealTrackerService cannot detect people.")

        # --- Short-term tracker ------------------------------------------
        self.tracker = None
        if sv is not None:
            self.tracker = sv.ByteTrack(
                track_activation_threshold=track_activation_threshold,
                lost_track_buffer=lost_track_buffer,
                minimum_matching_threshold=minimum_matching_threshold,
                frame_rate=frame_rate,
            )
        else:
            logger.error("supervision is not installed — RealTrackerService cannot track people.")

        # --- Optional Re-ID / global identity -----------------------------
        self.reid_extractor = None
        self.identity_manager = None
        if use_reid:
            if FeatureExtractor is not None:
                try:
                    self.reid_extractor = FeatureExtractor(model_name="osnet_x1_0", device=self.device)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Could not load OSNet Re-ID model (%s) — continuing without Re-ID.", exc)
            else:
                logger.info("torchreid not installed — continuing without Re-ID (raw ByteTrack ids only).")

            if self.reid_extractor is not None:
                self.identity_manager = GlobalIdentityManager(
                    expected_persons=expected_persons,
                    match_threshold=reid_match_threshold,
                    max_memory_frames=global_memory_frames or (frame_rate * 60),
                    max_embeddings=max_embeddings_per_person,
                    min_track_frames_for_id=min_track_frames_for_id,
                )

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def _detect(self, frame: np.ndarray):
        """Runs YOLO + filtering. Returns a supervision.Detections (possibly empty) or None."""
        if self.model is None or sv is None:
            return None

        results = self.model.predict(
            frame,
            conf=self.conf_threshold,
            classes=[self.person_class_id],
            device=self.device,
            verbose=False,
        )[0]

        xyxy, confidences, class_ids = [], [], []
        for box in results.boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            confidence = float(box.conf[0].cpu().numpy())
            class_id = int(box.cls[0].cpu().numpy())

            if class_id != self.person_class_id:
                continue
            if not is_valid_detection((x1, y1, x2, y2), confidence, self.filter_config):
                continue

            xyxy.append([x1, y1, x2, y2])
            confidences.append(confidence)
            class_ids.append(class_id)

        if not xyxy:
            return sv.Detections.empty()

        return sv.Detections(
            xyxy=np.array(xyxy, dtype=np.float32),
            confidence=np.array(confidences, dtype=np.float32),
            class_id=np.array(class_ids, dtype=int),
        )

    # ------------------------------------------------------------------
    # Main loop — internal generator shared by run() and run_frames()
    # ------------------------------------------------------------------

    def _iter_frames(self) -> Iterator[Dict]:
        if self.model is None or self.tracker is None:
            raise RuntimeError(
                "RealTrackerService requires 'ultralytics' and 'supervision' to be installed. "
                "See requirements.txt / pyproject.toml."
            )

        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            raise FileNotFoundError(f"Could not open video: {self.video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or self.frame_rate

        track_frame_counts: Dict[int, int] = defaultdict(int)
        track_last_embedding_frame: Dict[int, int] = {}
        frame_number = 0

        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break

                detections = self._detect(frame)
                tracked = self.tracker.update_with_detections(detections) if detections is not None else None

                tracks_out: List[Dict] = []
                used_person_ids = set()

                if tracked is not None and len(tracked) > 0:
                    for i in range(len(tracked)):
                        x1, y1, x2, y2 = tracked.xyxy[i]
                        bbox_f = (float(x1), float(y1), float(x2), float(y2))
                        bbox = [int(round(v)) for v in bbox_f]
                        confidence = float(tracked.confidence[i]) if tracked.confidence is not None else 0.0
                        raw_track_id = int(tracked.tracker_id[i]) if tracked.tracker_id is not None else -1

                        track_frame_counts[raw_track_id] += 1
                        final_track_id: object = raw_track_id

                        if self.identity_manager is not None:
                            embedding = None
                            last_emb_frame = track_last_embedding_frame.get(raw_track_id, -math.inf)
                            if frame_number - last_emb_frame >= self.embedding_update_interval:
                                crop = _crop_person(frame, bbox_f)
                                embedding = _extract_reid_embedding(self.reid_extractor, crop)
                                if embedding is not None:
                                    track_last_embedding_frame[raw_track_id] = frame_number

                            person_id, _similarity = self.identity_manager.assign(
                                track_id=raw_track_id,
                                embedding=embedding,
                                frame_number=frame_number,
                                bbox=bbox_f,
                                track_age=track_frame_counts[raw_track_id],
                                used_person_ids=used_person_ids,
                            )
                            used_person_ids.add(person_id)
                            if person_id != "UNKNOWN":
                                final_track_id = person_id

                        tracks_out.append({
                            "track_id": final_track_id,
                            "class_name": "person",
                            "bbox": bbox,
                            "confidence": round(confidence, 2),
                        })

                    if self.identity_manager is not None:
                        self.identity_manager.update_lost_states(used_person_ids, frame_number)

                yield {
                    "frame_number": frame_number,
                    "timestamp": round(frame_number / fps, 2),
                    "tracks": tracks_out,
                }
                frame_number += 1

        finally:
            cap.release()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> Iterator[Tuple[int, List[Dict]]]:
        """
        Back-compat contract for video_processor.py:
        yields (frame_number, tracks) where each track has "track_id",
        "bbox" (as before), plus "class_name"/"confidence" now too.
        """
        for frame_result in self._iter_frames():
            yield frame_result["frame_number"], frame_result["tracks"]

    def run_frames(self) -> Iterator[Dict]:
        """
        Yields the full per-frame payload:
            {"frame_number": int, "timestamp": float, "tracks": [...]}
        """
        yield from self._iter_frames()