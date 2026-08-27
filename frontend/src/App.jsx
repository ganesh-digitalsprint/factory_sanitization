import { useState, useCallback, useRef, useEffect } from "react";
import TopBar from "./components/TopBar";
import VideoStage from "./components/VideoStage";
import SequenceStepper, { DEFAULT_SEQUENCE } from "./components/SequenceStepper";
import StatStrip from "./components/StatStrip";
import EventLog from "./components/EventLog";
import CameraConnectModal from "./components/CameraConnectModal";
import { uploadVideo, connectProcessingStream } from "./api";

export default function App() {
  const [file, setFile] = useState(null);
  const [videoUrl, setVideoUrl] = useState(null);
  const [status, setStatus] = useState("empty"); // empty | ready | processing | completed | failed
  const [errorMsg, setErrorMsg] = useState(null);
  const [wsConnected, setWsConnected] = useState(false);

  const [personsDetected, setPersonsDetected] = useState(0);
  const [eventsDetected, setEventsDetected] = useState(0);
  const [visitedZones, setVisitedZones] = useState([]);
  const [missedZones, setMissedZones] = useState([]);
  const [activeZone, setActiveZone] = useState(null);
  const [events, setEvents] = useState([]);
  const [liveTracks, setLiveTracks] = useState([]);
  const [aiFrameInfo, setAiFrameInfo] = useState(null);
  const [cameraModalOpen, setCameraModalOpen] = useState(false);

  const closeStreamRef = useRef(null);

  const resetLiveState = () => {
    setEvents([]);
    setVisitedZones([]);
    setMissedZones([]);
    setActiveZone(null);
    setLiveTracks([]);
    setAiFrameInfo(null);
    setPersonsDetected(0);
    setEventsDetected(0);
  };

  const handleFileSelected = useCallback((f) => {
    closeStreamRef.current?.();
    setFile(f);
    setVideoUrl(URL.createObjectURL(f));
    setStatus("ready");
    setErrorMsg(null);
    setWsConnected(false);
    resetLiveState();
  }, []);

  const handleProcess = useCallback(async () => {
    if (!file) return;
    setStatus("processing");
    setErrorMsg(null);
    resetLiveState();

    try {
      const response = await uploadVideo(file);
      const jobId = response.session_id || response.job_id;

      // Open the live results channel BEFORE (or right after) processing
      // starts on the backend - the server buffers nothing, so if we
      // connect late we simply miss earlier frames, same as a real live feed.
      closeStreamRef.current = connectProcessingStream(jobId, {
        onOpen: () => setWsConnected(true),

        onStatus: (msg) => {
          if (msg.persons_detected !== undefined) setPersonsDetected(msg.persons_detected);
          if (msg.events_detected !== undefined) setEventsDetected(msg.events_detected);

          if (msg.status === "COMPLETED") {
            setStatus("completed");
            closeStreamRef.current?.();
          } else if (msg.status === "FAILED") {
            setStatus("failed");
            setErrorMsg(msg.error ?? "Processing failed.");
            closeStreamRef.current?.();
          }
        },

        onFrameResult: (msg) => {
          setLiveTracks(msg.persons ?? []);
          setAiFrameInfo({ frameNumber: msg.frame_number });
          const current = msg.persons?.[0]?.zone ?? null;
          if (current) setActiveZone(current);
        },

        onEvent: (msg) => {
          setEvents((prev) => [...prev, msg]);

          if (msg.zone) {
            setVisitedZones((prev) => (prev.includes(msg.zone) ? prev : [...prev, msg.zone]));
          }

          if (msg.event_type === "SEQUENCE_COMPLETED" && msg.missed_steps?.length) {
            setMissedZones(msg.missed_steps);
          }
        },

        onError: () => {
          setStatus("failed");
          setErrorMsg("Live connection to the backend was interrupted.");
        },

        onClose: () => setWsConnected(false),
      });
    } catch (err) {
      setStatus("failed");
      setErrorMsg(err.message ?? "Could not reach the backend.");
    }
  }, [file]);

  useEffect(() => () => closeStreamRef.current?.(), []);

  const compliancePct =
    status === "completed" && DEFAULT_SEQUENCE.length > 0
      ? Math.round(((DEFAULT_SEQUENCE.length - missedZones.length) / DEFAULT_SEQUENCE.length) * 100)
      : null;

  return (
    <div className="app-shell">
      <TopBar jobStatus={status} wsConnected={wsConnected} onOpenCameraModal={() => setCameraModalOpen(true)} />

      {errorMsg && (
        <div className="banner banner-error">
          Couldn't process this video: {errorMsg}. Confirm the backend is running at{" "}
          <code>localhost:8000</code>.
        </div>
      )}

      <main className="layout">
        <section className="layout-center">
          <VideoStage
            videoUrl={videoUrl}
            fileName={file?.name}
            status={status}
            onFileSelected={handleFileSelected}
            onProcess={handleProcess}
            liveTracks={liveTracks}
            aiFrameInfo={aiFrameInfo}
          />
          <StatStrip personsDetected={personsDetected} eventsDetected={eventsDetected} compliancePct={compliancePct} />
        </section>

        <aside className="layout-side">
          <SequenceStepper
            visitedZones={visitedZones}
            missedZones={missedZones}
            activeZone={status === "processing" ? activeZone : null}
          />
          <EventLog events={events} />
        </aside>
      </main>

      <CameraConnectModal
        open={cameraModalOpen}
        onClose={() => setCameraModalOpen(false)}
        onConnect={(cfg) => {
          // Placeholder hook: wire this to a future /cameras/connect
          // endpoint once the backend supports a live RTSP/tracker source
          // feeding the same WebSocket stream used here.
          console.log("Camera connect requested:", cfg);
        }}
      />
    </div>
  );
}
