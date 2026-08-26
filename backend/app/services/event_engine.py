"""
event_engine.py

Turns raw zone occupancy into meaningful business events:
- ZONE_CHANGED whenever a tracked person moves into a new zone
- a running list of visited zones per person
- MISSED_STEP detection once a person reaches the final zone, by
  comparing their visited zones against the expected sanitation sequence

This module has no FastAPI or database dependency — it's pure logic,
so you can unit test it the same way as ZoneEngine.
"""

from typing import Optional


# Edit this to match your actual required sanitation sequence
EXPECTED_SEQUENCE = [
    "ENTRY_ZONE",
    "CUPBOARD_INTERACTION_ZONE",
    "SLIPPER_ZONE",
    "VACUUM_ZONE",
    "HAND_WASH_ZONE",
    "HAND_DRYER_ZONE",
    "ACCESS_BUTTON_ZONE",
    "PRODUCTION_ENTRY_ZONE",
]

# Which zone marks "the person is done" and it's safe to check for missed steps
FINAL_ZONE = "PRODUCTION_ENTRY_ZONE"


class EventEngine:
    def __init__(self, expected_sequence: Optional[list] = None, final_zone: Optional[str] = None):
        self.expected_sequence = expected_sequence or EXPECTED_SEQUENCE
        self.final_zone = final_zone or FINAL_ZONE
        self.person_states = {}

    def _get_or_create_state(self, person_id):
        if person_id not in self.person_states:
            self.person_states[person_id] = {
                "current_zone": None,
                "visited_zones": [],
                "completed": False,
            }
        return self.person_states[person_id]

    def process_zone(self, person_id, zone, frame_number=None, timestamp=None):
        """
        Call this once per frame (or per detection) for each tracked person.
        Returns a list of event dicts (can be empty, one, or two events —
        e.g. a ZONE_CHANGED plus a MISSED_STEPS event if they just finished).
        """
        state = self._get_or_create_state(person_id)
        events = []

        previous_zone = state["current_zone"]

        # No change in zone -> nothing to emit
        if zone == previous_zone:
            return events

        state["current_zone"] = zone

        if zone and zone not in state["visited_zones"]:
            state["visited_zones"].append(zone)

        events.append({
            "person_id": person_id,
            "event": "ZONE_CHANGED",
            "from_zone": previous_zone,
            "to_zone": zone,
            "frame_number": frame_number,
            "timestamp": timestamp,
        })

        # Once they hit the final zone, check what they skipped
        if zone == self.final_zone and not state["completed"]:
            state["completed"] = True
            missed = self.get_missed_steps(person_id)
            events.append({
                "person_id": person_id,
                "event": "SEQUENCE_COMPLETED",
                "visited_zones": list(state["visited_zones"]),
                "missed_steps": missed,
                "status": "COMPLETED" if not missed else "MISSED_STEP",
                "frame_number": frame_number,
                "timestamp": timestamp,
            })

        return events

    def get_missed_steps(self, person_id):
        """Returns the list of expected zones this person never visited."""
        state = self.person_states.get(person_id)
        if not state:
            return list(self.expected_sequence)

        visited = set(state["visited_zones"])
        return [zone for zone in self.expected_sequence if zone not in visited]

    def get_state(self, person_id):
        return self.person_states.get(person_id)
