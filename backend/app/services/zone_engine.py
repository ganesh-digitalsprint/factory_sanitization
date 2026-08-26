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
    def __init__(self, zones: dict):
        """
        zones: dict mapping zone_name -> list of [x, y] polygon points.
               Empty polygons (not yet drawn) are simply skipped.
        """
        self.zones = zones

    @classmethod
    def from_json(cls, path: str | Path) -> "ZoneEngine":
        """Convenience constructor: load zones straight from a zones.json file."""
        with open(path, "r") as f:
            zones = json.load(f)
        return cls(zones)

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
            if not polygon:
                continue

            polygon_np = np.array(polygon, dtype=np.int32)
            result = cv2.pointPolygonTest(polygon_np, point, False)

            if result >= 0:
                return zone_name

        return None
