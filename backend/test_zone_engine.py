"""
test_zone_engine.py

Unit tests for ZoneEngine (bounding-box ↔ zone polygon overlap ratio).

Usage:
    python test_zone_engine.py
"""

from pathlib import Path
from app.services.zone_engine import ZoneEngine

# Configure test zones
# Zone A: Square from (100, 100) to (300, 300) -> area 40,000
# Zone B: Square from (250, 100) to (450, 300) -> area 40,000
test_zones = {
    "CUPBOARD_INTERACTION_ZONE": [
        [100, 100],
        [300, 100],
        [300, 300],
        [100, 300],
    ],
    "VACUUM_ZONE": [
        [250, 100],
        [450, 100],
        [450, 300],
        [250, 300],
    ],
}

engine = ZoneEngine(test_zones, overlap_threshold=0.20)

# -------------------------------------------------------------
# Test 1 — Completely outside
# -------------------------------------------------------------
bbox_outside = [900, 900, 950, 950]
zone_outside = engine.get_zone(bbox_outside)
print(f"\n[Test 1] bbox {bbox_outside} -> {zone_outside}")
assert zone_outside is None, "Expected None for bbox completely outside all zones"

# -------------------------------------------------------------
# Test 2 — Significant overlap
# -------------------------------------------------------------
# BBox: [150, 150, 250, 250] -> area 10,000. 100% inside CUPBOARD_INTERACTION_ZONE
bbox_inside = [150, 150, 250, 250]
zone_inside = engine.get_zone(bbox_inside)
print(f"\n[Test 2] bbox {bbox_inside} -> {zone_inside}")
assert zone_inside == "CUPBOARD_INTERACTION_ZONE", "Expected CUPBOARD_INTERACTION_ZONE"

# -------------------------------------------------------------
# Test 3 — Small overlap (below threshold)
# -------------------------------------------------------------
# BBox: [80, 80, 180, 180] -> bbox area 100 x 100 = 10,000.
# Overlap with Zone A is (100..180, 100..180) = 80 x 80 = 6,400 (ratio 0.64).
# Now construct a box with < 20% overlap:
# BBox: [50, 50, 150, 250] -> bbox size 100 x 200 = 20,000 area.
# Overlap with Zone A: (100..150, 100..250) = 50 x 150 = 7,500 (ratio 0.375).
# BBox: [20, 20, 120, 500] -> bbox size 100 x 480 = 48,000 area.
# Overlap with Zone A: (100..120, 100..300) = 20 x 200 = 4,000 (ratio 4,000 / 48,000 = 0.083 < 0.20 threshold).
bbox_small_overlap = [20, 20, 120, 500]
zone_small = engine.get_zone(bbox_small_overlap)
print(f"\n[Test 3] bbox {bbox_small_overlap} -> {zone_small}")
assert zone_small is None, "Expected None for overlap below threshold (0.20)"

# -------------------------------------------------------------
# Test 4 — Multiple zones (picks highest overlap ratio)
# -------------------------------------------------------------
# BBox: [240, 100, 340, 300] -> area 100 x 200 = 20,000
# Overlap with CUPBOARD_INTERACTION_ZONE (100..300, 100..300):
#   Intersection: [240..300, 100..300] = 60 x 200 = 12,000 -> ratio 0.60
# Overlap with VACUUM_ZONE (250..450, 100..300):
#   Intersection: [250..340, 100..300] = 90 x 200 = 18,000 -> ratio 0.90
bbox_multi = [240, 100, 340, 300]
zone_multi = engine.get_zone(bbox_multi)
print(f"\n[Test 4] bbox {bbox_multi} -> {zone_multi}")
assert zone_multi == "VACUUM_ZONE", f"Expected VACUUM_ZONE (highest overlap ratio), got {zone_multi}"

# -------------------------------------------------------------
# Test 5 — Boundary condition
# -------------------------------------------------------------
# BBox touching boundary of Zone A: [50, 100, 100, 300] -> touches x=100 line.
# Overlap area is 0 pixels, ratio 0.0 -> returns None deterministically.
bbox_boundary = [50, 100, 100, 300]
zone_boundary = engine.get_zone(bbox_boundary)
print(f"\n[Test 5] bbox {bbox_boundary} -> {zone_boundary}")
assert zone_boundary is None, "Expected None for touching boundary with zero interior overlap"

print("\n[OK] All ZoneEngine unit tests passed.")

# -------------------------------------------------------------
# Real zones.json backward compatibility test
# -------------------------------------------------------------
zones_file = Path(__file__).resolve().parent / "app" / "config" / "zones.json"
if zones_file.exists():
    real_engine = ZoneEngine.from_json(zones_file)
    sample_bbox = [1491, 339, 1737, 748]
    detected_zone = real_engine.get_zone(sample_bbox)
    print(f"\n[Compatibility Test] Real zones.json sample {sample_bbox} -> {detected_zone}")
    assert detected_zone is None or isinstance(detected_zone, str)

