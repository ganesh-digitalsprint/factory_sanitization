const DEFAULT_SEQUENCE = [
  "ENTRY_ZONE",
  "CUPBOARD_INTERACTION_ZONE",
  "SLIPPER_ZONE",
  "VACUUM_ZONE",
  "HAND_WASH_ZONE",
  "HAND_DRYER_ZONE",
  "ACCESS_BUTTON_ZONE",
  "PRODUCTION_ENTRY_ZONE",
];

const LABELS = {
  ENTRY_ZONE: "Entry",
  CUPBOARD_INTERACTION_ZONE: "Cupboard interaction",
  SLIPPER_ZONE: "Slipper change",
  VACUUM_ZONE: "Vacuum",
  HAND_WASH_ZONE: "Hand wash",
  HAND_DRYER_ZONE: "Hand dryer",
  ACCESS_BUTTON_ZONE: "Access button",
  PRODUCTION_ENTRY_ZONE: "Production entry",
};

/**
 * visitedZones: string[] of zone names the current/selected person has hit
 * missedZones: string[] of zone names flagged as skipped (only meaningful once completed)
 */
export default function SequenceStepper({
  sequence = DEFAULT_SEQUENCE,
  visitedZones = [],
  missedZones = [],
  activeZone = null,
}) {
  return (
    <div className="panel stepper-panel">
      <div className="panel-header">
        <h3>Sanitation sequence</h3>
        <span className="panel-hint">Required order</span>
      </div>

      <ol className="stepper">
        {sequence.map((zone, i) => {
          const isVisited = visitedZones.includes(zone);
          const isMissed = missedZones.includes(zone);
          const isActive = zone === activeZone;

          let state = "pending";
          if (isMissed) state = "missed";
          else if (isVisited) state = "done";
          if (isActive) state = "active";

          return (
            <li key={zone} className={`step step-${state}`}>
              <span className="step-index">
                {state === "done" ? (
                  <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                    <path d="M3 8.5 6.2 12 13 4" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                ) : state === "missed" ? (
                  <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                    <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
                  </svg>
                ) : (
                  i + 1
                )}
              </span>
              <span className="step-label">{LABELS[zone] ?? zone}</span>
              {isActive && <span className="step-now">now</span>}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export { DEFAULT_SEQUENCE };
