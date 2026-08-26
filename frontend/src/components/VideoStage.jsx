import { useRef, useState, useCallback, useEffect } from "react";

const ZONE_COLORS = ["#3e7c8c", "#6f8f45", "#d9a441", "#c4544a", "#8b6fb0"];

export default function VideoStage({
  videoUrl,
  fileName,
  status, // "empty" | "ready" | "processing" | "completed" | "failed"
  onFileSelected,
  onProcess,
  liveTracks = [], // [{track_id, bbox:[x1,y1,x2,y2], zone}] - raw pixel coords from the source video
  aiFrameInfo = null, // {frameNumber} - how far the AI pipeline has actually gotten
}) {
  const inputRef = useRef(null);
  const videoRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);
  const [videoTime, setVideoTime] = useState(0);
  // Scale factor between the video's native pixel size and how large it's
  // actually rendered, so bbox overlays line up regardless of screen size.
  const [scale, setScale] = useState({ x: 1, y: 1, offsetX: 0, offsetY: 0 });

  const recomputeScale = useCallback(() => {
    const el = videoRef.current;
    if (!el || !el.videoWidth) return;

    const renderedW = el.clientWidth;
    const renderedH = el.clientHeight;
    const nativeAspect = el.videoWidth / el.videoHeight;
    const renderedAspect = renderedW / renderedH;

    // object-fit: contain letterboxes the video - account for the bars
    let contentW = renderedW;
    let contentH = renderedH;
    let offsetX = 0;
    let offsetY = 0;

    if (nativeAspect > renderedAspect) {
      contentH = renderedW / nativeAspect;
      offsetY = (renderedH - contentH) / 2;
    } else {
      contentW = renderedH * nativeAspect;
      offsetX = (renderedW - contentW) / 2;
    }

    setScale({
      x: contentW / el.videoWidth,
      y: contentH / el.videoHeight,
      offsetX,
      offsetY,
    });
  }, []);

  useEffect(() => {
    const onResize = () => recomputeScale();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [recomputeScale]);

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) onFileSelected(file);
    },
    [onFileSelected]
  );

  const isProcessing = status === "processing";
  const isEmpty = status === "empty";

  return (
    <div className="stage">
      <div
        className={`stage-frame ${isProcessing ? "is-processing" : ""} ${
          status === "completed" ? "is-completed" : ""
        }`}
      >
        {/* Viewfinder corner brackets — the signature element */}
        <span className="bracket bracket-tl" />
        <span className="bracket bracket-tr" />
        <span className="bracket bracket-bl" />
        <span className="bracket bracket-br" />
        {isProcessing && <span className="scan-line" />}

        <div className="stage-inner">
          {isEmpty ? (
            <div
              className={`dropzone ${isDragging ? "is-dragging" : ""}`}
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              onClick={() => inputRef.current?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
            >
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                <rect x="2" y="5" width="15" height="14" rx="2" />
                <path d="M17 9.5 22 7v10l-5-2.5" />
              </svg>
              <p className="dropzone-title">Drop a CCTV clip, or click to browse</p>
              <p className="dropzone-sub">MP4 or MOV &middot; the feed will appear centered here</p>
              <input
                ref={inputRef}
                type="file"
                accept="video/*"
                hidden
                onChange={(e) => e.target.files?.[0] && onFileSelected(e.target.files[0])}
              />
            </div>
          ) : (
            <div className="video-wrap">
              <video
                ref={videoRef}
                src={videoUrl}
                controls={!isProcessing}
                className="video-el"
                onLoadedMetadata={recomputeScale}
                onTimeUpdate={(e) => setVideoTime(e.target.currentTime)}
              />

              {liveTracks.map((t) => (
                <div
                  key={t.track_id}
                  className="track-box"
                  style={{
                    left: `${scale.offsetX + t.bbox[0] * scale.x}px`,
                    top: `${scale.offsetY + t.bbox[1] * scale.y}px`,
                    width: `${(t.bbox[2] - t.bbox[0]) * scale.x}px`,
                    height: `${(t.bbox[3] - t.bbox[1]) * scale.y}px`,
                    borderColor: ZONE_COLORS[t.track_id % ZONE_COLORS.length],
                  }}
                >
                  <span
                    className="track-label"
                    style={{ background: ZONE_COLORS[t.track_id % ZONE_COLORS.length] }}
                  >
                    P{t.track_id} &middot; {t.zone ?? "—"}
                  </span>
                </div>
              ))}

              {isProcessing && (
                <div className="processing-badge">
                  <span className="pulse-dot" />
                  Tracking in progress
                  {aiFrameInfo?.frameNumber !== undefined && (
                    <span className="processing-badge-frame">
                      &middot; AI at frame {aiFrameInfo.frameNumber}
                      {" "}
                      (video at {videoTime.toFixed(1)}s)
                    </span>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="stage-footer">
        <div className="stage-file">
          {fileName ? (
            <>
              <span className="file-dot" />
              <span className="file-name">{fileName}</span>
            </>
          ) : (
            <span className="file-name muted">No video loaded</span>
          )}
        </div>

        <div className="stage-actions">
          {!isEmpty && status !== "processing" && status !== "completed" && (
            <button className="btn btn-ghost" onClick={() => inputRef.current?.click()}>
              Replace video
            </button>
          )}
          <input
            ref={inputRef}
            type="file"
            accept="video/*"
            hidden
            onChange={(e) => e.target.files?.[0] && onFileSelected(e.target.files[0])}
          />
          <button
            className="btn btn-primary"
            disabled={isEmpty || isProcessing}
            onClick={onProcess}
          >
            {isProcessing ? "Processing…" : status === "completed" ? "Re-run" : "Start tracking"}
          </button>
        </div>
      </div>
    </div>
  );
}
