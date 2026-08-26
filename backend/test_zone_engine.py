"""
test_zone_engine.py

Quick standalone sanity check for ZoneEngine, with no FastAPI, no tracker,
no database involved. Run this first to confirm your zone math works.

Usage:
    python test_zone_engine.py
"""

from app.services.zone_engine import ZoneEngine

# Option A: hardcoded zones for a quick smoke test
zones = {
    "ENTRY_ZONE": [
        [100, 100],
        [400, 100],
        [400, 400],
        [100, 400],
    ]
}

engine = ZoneEngine(zones)

bbox = [150, 150, 300, 390]
zone = engine.get_zone(bbox)
print(f"bbox {bbox} -> {zone}")
assert zone == "ENTRY_ZONE", "Expected ENTRY_ZONE"

bbox_outside = [900, 900, 950, 950]
zone_outside = engine.get_zone(bbox_outside)
print(f"bbox {bbox_outside} -> {zone_outside}")
assert zone_outside is None, "Expected None for a point outside all zones"

print("\n[OK] ZoneEngine basic tests passed.")

# Option B: load your real zones.json and try a few of your own bboxes
try:
    real_engine = ZoneEngine.from_json("app/config/zones.json")
    sample_bbox = [500, 300, 650, 700]  # replace with a bbox from your video
    print(f"\nUsing real zones.json -> {sample_bbox} maps to: {real_engine.get_zone(sample_bbox)}")
except FileNotFoundError:
    print("\n[!] app/config/zones.json not found yet — skipping real-zone test.")
