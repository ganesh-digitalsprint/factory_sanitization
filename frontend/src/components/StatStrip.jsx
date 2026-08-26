export default function StatStrip({ personsDetected = 0, eventsDetected = 0, compliancePct = null }) {
  const stats = [
    { label: "Persons detected", value: personsDetected },
    { label: "Events logged", value: eventsDetected },
    {
      label: "Compliance",
      value: compliancePct === null ? "—" : `${compliancePct}%`,
      accent:
        compliancePct === null ? "neutral" : compliancePct >= 90 ? "success" : compliancePct >= 60 ? "warning" : "danger",
    },
  ];

  return (
    <div className="stat-strip">
      {stats.map((s) => (
        <div key={s.label} className="stat-card">
          <span className={`stat-value ${s.accent ? `stat-${s.accent}` : ""}`}>{s.value}</span>
          <span className="stat-label">{s.label}</span>
        </div>
      ))}
    </div>
  );
}
