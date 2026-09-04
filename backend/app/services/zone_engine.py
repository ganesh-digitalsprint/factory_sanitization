"""
zone_engine.py

Given a person's bounding box, figure out which zone (if any) they're
currently in based on bounding-box overlap with configured zone polygons.
"""

import json
import logging
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class ZoneEngine:
    def __init__(self, zones: dict | list, overlap_threshold: float = 0.20):
        """
        zones: can be either:
          1. Dict mapping zone_name -> list of [x, y] polygon points
          2. Dict with {"zones": [{"name": "...", "points": [[x,y],...]}, ...]}
          3. List of zone dicts [{"name": "...", "points": ...}]
        overlap_threshold: float between 0.0 and 1.0 (default 0.20 = 20%).
          Determines minimum fraction of bounding-box area that must overlap
          with a zone polygon for the person to be considered inside.
        """
        self.zones = self._normalize_zones(zones)
        self.overlap_threshold = float(overlap_threshold)

    @staticmethod
    def _normalize_zones(raw_zones) -> dict:
        normalized = {}
        if isinstance(raw_zones, dict):
            if "zones" in raw_zones and isinstance(raw_zones["zones"], list):
                for z in raw_zones["zones"]:
                    if isinstance(z, dict) and "name" in z and "points" in z:
                        normalized[z["name"]] = z["points"]
            else:
                for name, points in raw_zones.items():
                    if isinstance(points, list):
                        normalized[name] = points
        elif isinstance(raw_zones, list):
            for z in raw_zones:
                if isinstance(z, dict) and "name" in z and "points" in z:
                    normalized[z["name"]] = z["points"]
        return normalized

    @classmethod
    def from_json(cls, path: str | Path, overlap_threshold: float = 0.20) -> "ZoneEngine":
        """Convenience constructor: load zones straight from a zones.json file."""
        with open(path, "r") as f:
            data = json.load(f)
        return cls(data, overlap_threshold=overlap_threshold)

    @staticmethod
    def compute_overlap(polygon: list, bbox: list | tuple) -> tuple[float, float, float]:
        """
        Calculates geometric overlap between an arbitrary polygon and a bounding box.

        bbox: [x1, y1, x2, y2]
        polygon: list of [x, y] points

        Returns: (intersection_area, bbox_area, overlap_ratio)
        """
        x1, y1, x2, y2 = bbox
        x1_f, y1_f, x2_f, y2_f = float(x1), float(y1), float(x2), float(y2)

        bbox_w = max(0.0, x2_f - x1_f)
        bbox_h = max(0.0, y2_f - y1_f)
        bbox_area = bbox_w * bbox_h

        if bbox_area <= 0.0 or not polygon or len(polygon) < 3:
            return 0.0, bbox_area, 0.0

        offset_x = np.floor(x1_f)
        offset_y = np.floor(y1_f)
        w_int = max(1, int(np.ceil(x2_f) - offset_x))
        h_int = max(1, int(np.ceil(y2_f) - offset_y))

        poly_np = np.array(polygon, dtype=np.float32)
        poly_rel = poly_np - np.array([offset_x, offset_y], dtype=np.float32)
        poly_rel_int = np.int32(np.round(poly_rel))

        mask = np.zeros((h_int, w_int), dtype=np.uint8)
        cv2.fillPoly(mask, [poly_rel_int], 255)

        intersection_area = float(np.count_nonzero(mask))
        overlap_ratio = intersection_area / bbox_area if bbox_area > 0 else 0.0

        return intersection_area, bbox_area, overlap_ratio

    def get_zone(self, bbox: list | tuple) -> str | None:
        """
        Given a person's bounding box [x1, y1, x2, y2], determine which zone (if any)
        they are currently in based on bounding-box ↔ zone polygon overlap.

        Returns the zone name with the highest overlap ratio that meets or exceeds
        self.overlap_threshold, or None if no zone satisfies the threshold.
        """
        debug_lines = [f"\nBBox: {bbox}"]

        best_zone = None
        max_overlap_ratio = -1.0

        for zone_name, polygon in self.zones.items():
            if not polygon or not isinstance(polygon, list) or len(polygon) < 3:
                continue

            try:
                intersection_area, bbox_area, overlap_ratio = self.compute_overlap(polygon, bbox)

                debug_lines.append(
                    f"\nZone={zone_name}\n"
                    f"intersection_area={intersection_area:.2f}\n"
                    f"bbox_area={bbox_area:.2f}\n"
                    f"overlap_ratio={overlap_ratio:.2f}"
                )

                if overlap_ratio >= self.overlap_threshold:
                    if overlap_ratio > max_overlap_ratio:
                        max_overlap_ratio = overlap_ratio
                        best_zone = zone_name
            except Exception as e:
                logger.error(f"Zone error for {zone_name}: {e}")
                continue

        if best_zone is not None:
            debug_lines.append(f"\n\nSelected zone={best_zone}")
        else:
            debug_lines.append("\n\n>>> NO ZONE")

        log_str = "".join(debug_lines)
        logger.debug(log_str)
        print(log_str)

        return best_zone

