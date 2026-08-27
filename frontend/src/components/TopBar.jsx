export default function TopBar({ jobStatus, wsConnected, onOpenCameraModal }) {
  const statusLabel = {
    empty: "Idle",
    ready: "Ready",
    processing: "Processing",
    completed: "Completed",
    failed: "Failed",
  }[jobStatus] ?? "Idle";

  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M12 3 4 6v6c0 4.5 3.2 7.7 8 9 4.8-1.3 8-4.5 8-9V6l-8-3Z" />
            <path d="m8.5 12 2.4 2.4L16 9.6" />
          </svg>
        </span>
        <div>
          <span className="brand-name">Sanitation Tracker</span>
          <span className="brand-sub">Sanitation compliance monitoring</span>
        </div>
      </div>

      <div className="topbar-actions">
        {jobStatus === "processing" && (
          <span className={`ws-pill ${wsConnected ? "ws-pill-live" : ""}`}>
            <span className="ws-dot" />
            {wsConnected ? "Live feed connected" : "Connecting…"}
          </span>
        )}
        <span className={`status-pill status-${jobStatus}`}>
          <span className="status-dot" />
          {statusLabel}
        </span>
        <button className="btn btn-outline" onClick={onOpenCameraModal}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" style={{ marginRight: 6 }}>
            <rect x="2" y="6" width="14" height="12" rx="2" />
            <path d="M16 10.5 21 8v8l-5-2.5" />
          </svg>
          Connect camera
        </button>
      </div>
    </header>
  );
}
