import { useState } from "react";

const MOCK_CAMERAS = [
  { id: "cam-1", name: "Sanitation Chamber — Entry", status: "online" },
  { id: "cam-2", name: "Sanitation Chamber — Wash station", status: "online" },
  { id: "cam-3", name: "Production Corridor", status: "offline" },
];

export default function CameraConnectModal({ open, onClose, onConnect }) {
  const [rtspUrl, setRtspUrl] = useState("");
  const [selectedCam, setSelectedCam] = useState(null);

  if (!open) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Connect a CCTV camera</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <p className="modal-sub">Pick a camera already on the network, or connect one by stream URL.</p>

        <div className="cam-list">
          {MOCK_CAMERAS.map((cam) => (
            <button
              key={cam.id}
              className={`cam-card ${selectedCam === cam.id ? "cam-card-selected" : ""} ${
                cam.status === "offline" ? "cam-card-disabled" : ""
              }`}
              disabled={cam.status === "offline"}
              onClick={() => setSelectedCam(cam.id)}
            >
              <span className={`cam-status cam-status-${cam.status}`} />
              <span className="cam-name">{cam.name}</span>
              <span className="cam-state">{cam.status}</span>
            </button>
          ))}
        </div>

        <div className="modal-divider">
          <span>or</span>
        </div>

        <label className="field-label" htmlFor="rtsp">
          RTSP / stream URL
        </label>
        <input
          id="rtsp"
          className="text-input"
          placeholder="rtsp://192.168.1.20:554/stream1"
          value={rtspUrl}
          onChange={(e) => setRtspUrl(e.target.value)}
        />
        <p className="field-hint">
          Streaming ingest isn't wired into the backend yet — this hands the URL off once{" "}
          <code>tracker_service.py</code> supports a live source.
        </p>

        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            disabled={!selectedCam && !rtspUrl}
            onClick={() => {
              onConnect?.({ cameraId: selectedCam, rtspUrl: rtspUrl || null });
              onClose();
            }}
          >
            Connect
          </button>
        </div>
      </div>
    </div>
  );
}
