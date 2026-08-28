import { labelForId } from "../utils";

function formatEvent(e) {
  if (e.event_type === "SEQUENCE_COMPLETED") {
    return e.status === "COMPLETED" ? "completed the full sequence" : "finished with a missed step";
  }
  return `entered ${prettyZone(e.zone)}`;
}

function prettyZone(zone) {
  if (!zone) return "no zone";
  return zone.replace(/_/g, " ").toLowerCase();
}

export default function EventLog({ events = [] }) {
  return (
    <div className="panel log-panel">
      <div className="panel-header">
        <h3>Live event log</h3>
        <span className="panel-hint">{events.length} entries</span>
      </div>

      <div className="log-list">
        {events.length === 0 ? (
          <p className="log-empty">Events will appear here once tracking starts.</p>
        ) : (
          events
            .slice()
            .reverse()
            .map((e, i) => (
              <div key={i} className={`log-row ${e.status === "MISSED_STEP" ? "log-row-alert" : ""}`}>
                <span className="log-frame">
                  {e.timestamp !== undefined && e.timestamp !== null
                    ? `t=${e.timestamp}s`
                    : e.frame_number !== null && e.frame_number !== undefined
                    ? `f.${e.frame_number}`
                    : "—"}
                </span>
                <span className="log-text">
                  <strong>{labelForId(e.person_id)}</strong> {formatEvent(e)}
                </span>
              </div>
            ))
        )}
      </div>
    </div>
  );
}
