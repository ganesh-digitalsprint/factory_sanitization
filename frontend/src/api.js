// api.js
// Thin wrapper around the FastAPI backend. During dev, Vite proxies
// /api/* to http://localhost:8000 (see vite.config.js, ws: true), so
// this file never needs to know the backend's real host.

const BASE = "http://localhost:8000/api/v1";

export async function uploadVideo(file) {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${BASE}/videos/upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    throw new Error(`Upload failed (${res.status})`);
  }
  return res.json(); // { job_id, status }
}

export async function getEvents(jobId) {
  const res = await fetch(`${BASE}/events/${jobId}`);
  if (!res.ok) throw new Error(`Could not fetch events (${res.status})`);
  return res.json();
}

/**
 * Opens the live processing stream for one session (job_id) and wires up
 * handlers for each message type the backend sends:
 *   { type: "test", message }                                  - handshake
 *   { type: "status", status, persons_detected?, events_detected? }
 *   { type: "frame_result", frame_number, persons: [...] }      - live bboxes/zones
 *   { type: "event", person_id, event_type, zone, ... }         - zone changes / completions
 *
 * Returns a cleanup function - call it to close the socket (e.g. on unmount
 * or when a new video is loaded).
 */
export function connectProcessingStream(jobId, { onOpen, onStatus, onFrameResult, onEvent, onError, onClose } = {}) {
  const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  // Use backend host and /api/v1/videos prefix for WebSocket connection
  const wsUrl = `${wsProtocol}//localhost:8000/api/v1/videos/${jobId}/stream`;
  const ws = new WebSocket(wsUrl);

  ws.onopen = () => onOpen?.();

  ws.onmessage = (event) => {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }

    switch (data.type) {
      case "test":
      case "processing_started":
        onOpen?.(data);
        if (data.status) onStatus?.(data);
        break;
      case "processing_completed":
        onStatus?.({ ...data, status: "COMPLETED" });
        break;
      case "processing_error":
        onStatus?.({ ...data, status: "FAILED", error: data.message });
        break;
      case "status":
        onStatus?.(data);
        break;
      case "frame_result":
        onFrameResult?.(data);
        break;
      case "event":
        onEvent?.(data);
        break;
      default:
        break;
    }
  };

  ws.onerror = (err) => onError?.(err);
  ws.onclose = () => onClose?.();

  return () => ws.close();
}
