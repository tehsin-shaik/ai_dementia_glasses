"use client";

import { useEffect, useRef, useState } from "react";

import { captureVideoFrame } from "./camera";
import { MemoryHudControls, MemoryHudOverlay, MemoryHudState } from "./MemoryHud";

export type CameraStatus =
  | "inactive"
  | "starting"
  | "active"
  | "captured"
  | "analysis-running"
  | "analysis-complete"
  | "saving"
  | "saved"
  | "error";

type GlassesSimulatorProps = {
  capturedFrame: File | null;
  capturedPreviewUrl: string | null;
  isAnalyzing: boolean;
  isSaving: boolean;
  analysisComplete: boolean;
  saved: boolean;
  onCapture: (file: File) => void;
  onRetake: () => void;
  onAnalyze: () => void;
  hudState: MemoryHudState;
  hudAnswer: string | null;
  hudError: string | null;
  onHudQuery: (question: string) => void;
  onDismissHud: () => void;
};

type BaseCameraStatus = "inactive" | "starting" | "active" | "captured" | "error";

const preferredConstraints: MediaStreamConstraints = {
  video: {
    facingMode: "environment",
    width: { ideal: 1280 },
    height: { ideal: 720 },
  },
  audio: false,
};

const fallbackConstraints: MediaStreamConstraints = {
  video: {
    width: { ideal: 1280 },
    height: { ideal: 720 },
  },
  audio: false,
};

export function cameraErrorMessage(error: unknown): string {
  const name =
    error && typeof error === "object" && "name" in error
      ? String(error.name)
      : "";

  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Camera permission was denied. Allow camera access and try again.";
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return "No camera was found. Connect a camera and try again.";
  }
  if (name === "NotReadableError" || name === "AbortError") {
    return "The camera could not be started. It may already be in use.";
  }
  if (name === "TypeError") {
    return "Camera access requires localhost or HTTPS.";
  }
  return "The camera could not be started. Check the browser permission and try again.";
}

function isPermissionError(error: unknown): boolean {
  if (!error || typeof error !== "object" || !("name" in error)) {
    return false;
  }
  return ["NotAllowedError", "SecurityError"].includes(String(error.name));
}

function statusLabel(status: CameraStatus): string {
  const labels: Record<CameraStatus, string> = {
    inactive: "Camera inactive",
    starting: "Starting camera...",
    active: "Camera active",
    captured: "Frame captured",
    "analysis-running": "Analyzing captured frame...",
    "analysis-complete": "Analysis ready for review",
    saving: "Saving camera memory...",
    saved: "Camera memory saved",
    error: "Camera error",
  };
  return labels[status];
}

export default function GlassesSimulator({
  capturedFrame,
  capturedPreviewUrl,
  isAnalyzing,
  isSaving,
  analysisComplete,
  saved,
  onCapture,
  onRetake,
  onAnalyze,
  hudState,
  hudAnswer,
  hudError,
  onHudQuery,
  onDismissHud,
}: GlassesSimulatorProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [baseStatus, setBaseStatus] = useState<BaseCameraStatus>("inactive");
  const [cameraError, setCameraError] = useState<string | null>(null);

  useEffect(() => {
    if (!capturedFrame && baseStatus === "captured") {
      setBaseStatus(streamRef.current ? "active" : "inactive");
    }
  }, [baseStatus, capturedFrame]);

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      if (videoRef.current) {
        videoRef.current.srcObject = null;
      }
    };
  }, []);

  function stopActiveStream() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  }

  function effectiveStatus(): CameraStatus {
    if (cameraError) {
      return "error";
    }
    if (isSaving) {
      return "saving";
    }
    if (saved) {
      return "saved";
    }
    if (isAnalyzing) {
      return "analysis-running";
    }
    if (analysisComplete) {
      return "analysis-complete";
    }
    return baseStatus;
  }

  async function startCamera() {
    if (streamRef.current) {
      return;
    }

    setBaseStatus("starting");
    setCameraError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setBaseStatus("error");
      setCameraError("Camera access requires localhost or HTTPS.");
      return;
    }

    try {
      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia(preferredConstraints);
      } catch (error) {
        if (isPermissionError(error)) {
          throw error;
        }
        stream = await navigator.mediaDevices.getUserMedia(fallbackConstraints);
      }

      streamRef.current = stream;
      if (!videoRef.current) {
        throw new Error("The camera preview is unavailable.");
      }
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      setBaseStatus("active");
    } catch (error) {
      stopActiveStream();
      setBaseStatus("error");
      setCameraError(cameraErrorMessage(error));
    }
  }

  function stopCamera() {
    stopActiveStream();
    setBaseStatus(capturedFrame ? "captured" : "inactive");
    setCameraError(null);
  }

  async function captureFrame() {
    if (!videoRef.current || !canvasRef.current) {
      setBaseStatus("error");
      setCameraError("The camera preview is unavailable.");
      return;
    }

    try {
      const frame = await captureVideoFrame(videoRef.current, canvasRef.current);
      onCapture(frame);
      setBaseStatus("captured");
      setCameraError(null);
    } catch (error) {
      setBaseStatus("error");
      setCameraError(error instanceof Error ? error.message : "The camera frame could not be captured.");
    }
  }

  function retakeFrame() {
    onRetake();
    setBaseStatus(streamRef.current ? "active" : "inactive");
    setCameraError(null);
  }

  const status = effectiveStatus();
  const isStarting = baseStatus === "starting";
  const isActive = baseStatus === "active";
  const isStreamActive = Boolean(streamRef.current);
  const showLivePreview = isActive || isStarting || isStreamActive;
  const hasFrame = Boolean(capturedFrame && capturedPreviewUrl);

  return (
    <section className="camera-panel" aria-labelledby="camera-heading">
      <div className="camera-panel-heading">
        <div>
          <p className="section-kicker">Browser hardware simulator</p>
          <h2 id="camera-heading">Glasses Simulator</h2>
        </div>
        <span className={`camera-status camera-status-${status}`} role="status">
          <span className="status-dot" aria-hidden="true" />
          {statusLabel(status)}
        </span>
      </div>
      <p className="camera-helper">
        Point the laptop camera at a useful moment, capture one frame, then review the AI suggestions before saving.
        Camera access works on localhost or HTTPS. No microphone is requested.
      </p>

      <div className="camera-view" data-camera-active={showLivePreview}>
        {showLivePreview ? (
          <video ref={videoRef} autoPlay muted playsInline aria-label="Live camera preview" />
        ) : (
          <div className="camera-placeholder">
            <span aria-hidden="true">◉</span>
            <p>Camera preview will appear here.</p>
          </div>
        )}
        <MemoryHudOverlay
          state={hudState}
          answer={hudAnswer}
          error={hudError}
          onDismiss={onDismissHud}
        />
      </div>
      <canvas ref={canvasRef} className="camera-canvas" aria-hidden="true" />

      <MemoryHudControls isCameraActive={isStreamActive} state={hudState} onQuery={onHudQuery} />

      <div className="camera-controls">
        {!streamRef.current && !hasFrame && (
          <button className="secondary-button" type="button" onClick={() => void startCamera()} disabled={isStarting}>
            {isStarting ? "Starting camera..." : "Start camera"}
          </button>
        )}
        {isActive && (
          <button className="primary-button" type="button" onClick={() => void captureFrame()}>
            Capture what I see
          </button>
        )}
        {hasFrame && (
          <>
            <button className="secondary-button" type="button" onClick={retakeFrame} disabled={isAnalyzing || isSaving}>
              Retake
            </button>
            <button className="primary-button" type="button" onClick={onAnalyze} disabled={isAnalyzing || isSaving}>
              {isAnalyzing ? "Analyzing..." : "Analyze with AI"}
            </button>
          </>
        )}
        {streamRef.current && (
          <button className="text-button" type="button" onClick={stopCamera} disabled={isAnalyzing || isSaving}>
            Stop camera
          </button>
        )}
      </div>

      {hasFrame && (
        <div className="captured-frame">
          <div>
            <p className="captured-frame-label">Captured frame</p>
            <p className="captured-frame-name">{capturedFrame?.name}</p>
          </div>
          <img src={capturedPreviewUrl ?? undefined} alt="Captured camera frame" />
        </div>
      )}

      {cameraError && <p className="camera-error" role="alert">{cameraError}</p>}
    </section>
  );
}
