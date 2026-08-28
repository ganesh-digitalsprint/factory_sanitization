"""
zone_engine.py

Given a person's bounding box, figure out which zone (if any) they're
currently standing in, based on zones.json.
"""

import json
from pathlib import Path

import cv2
import numpy as np


class ZoneEngine:
    def __init__(self, zones: dict | list):
        """
        zones: can be either:
          1. Dict mapping zone_name -> list of [x, y] polygon points
          2. Dict with {"zones": [{"name": "...", "points": [[x,y],...]}, ...]}
          3. List of zone dicts [{"name": "...", "points": ...}]
        """
        self.zones = self._normalize_zones(zones)

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
    def from_json(cls, path: str | Path) -> "ZoneEngine":
        """Convenience constructor: load zones straight from a zones.json file."""
        with open(path, "r") as f:
            data = json.load(f)
        return cls(data)

    @staticmethod
    def get_person_point(bbox):
        """
        bbox: [x1, y1, x2, y2]
        Returns the bottom-center point of the box, which approximates
        where the person's feet are — the standard choice for zone checks.
        """
        x1, y1, x2, y2 = bbox
        x = int((x1 + x2) / 2)
        y = int(y2)
        return x, y

    def get_zone(self, bbox):
        """
        Returns the name of the first zone that contains the person's
        foot point, or None if they're not in any defined zone.
        """
        point = self.get_person_point(bbox)

        for zone_name, polygon in self.zones.items():
            if not polygon or not isinstance(polygon, list) or len(polygon) < 3:
                continue

            try:
                polygon_np = np.array(polygon, dtype=np.int32)
                if polygon_np.ndim != 2 or polygon_np.shape[1] != 2:
                    continue

                result = cv2.pointPolygonTest(polygon_np, point, False)
                if result >= 0:
                    return zone_name
            except Exception:
                continue

        return None
