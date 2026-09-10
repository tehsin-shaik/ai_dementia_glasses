"use client";

import { useEffect, useRef, useState } from "react";

import { captureVideoFrame } from "./camera";
import { MemoryHudControls, MemoryHudOverlay, MemoryHudState, ProactiveCue } from "./MemoryHud";

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
  onRecognize: (file: File) => void;
  isRecognizing: boolean;
  hudState: MemoryHudState;
  hudAnswer: string | null;
  hudError: string | null;
  proactiveCue: ProactiveCue | null;
  proactiveCuesEnabled: boolean;
  onProactiveCuesChange: (enabled: boolean) => void;
  onHudQuery: (question: string) => void;
  onDismissHud: () => void;
  onImagePreviewError: () => void;
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
    captured: "Image captured",
    "analysis-running": "Analyzing captured image...",
    "analysis-complete": "Analysis ready for review",
    saving: "Saving memory...",
    saved: "Memory saved",
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
  onRecognize,
  isRecognizing,
  hudState,
  hudAnswer,
  hudError,
  proactiveCue,
  proactiveCuesEnabled,
  onProactiveCuesChange,
  onHudQuery,
  onDismissHud,
  onImagePreviewError,
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
      setCameraError(error instanceof Error ? error.message : "The camera image could not be captured.");
    }
  }

  async function recognizeCurrentFrame() {
    if (!videoRef.current || !canvasRef.current) {
      setCameraError("The camera preview is unavailable.");
      return;
    }

    try {
      const frame = await captureVideoFrame(videoRef.current, canvasRef.current);
      onRecognize(frame);
      setCameraError(null);
    } catch (error) {
      setCameraError(error instanceof Error ? error.message : "The camera image could not be captured.");
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
  const visibleProactiveCue = isStreamActive && proactiveCue &&
    (!proactiveCue.expires_at || new Date(proactiveCue.expires_at).getTime() > Date.now())
    ? proactiveCue
    : null;

  return (
    <section className="camera-panel" aria-labelledby="camera-heading">
      <div className="camera-panel-heading">
        <div>
          <p className="section-kicker">Live camera</p>
          <h2 id="camera-heading">Live view</h2>
        </div>
        <span className={`camera-status camera-status-${status}`} role="status">
          <span className="status-dot" aria-hidden="true" />
          {statusLabel(status)}
        </span>
      </div>
      <p className="camera-helper">
        Capture an image. AI analysis is optional; review or edit the details before saving. <strong>Who is this?</strong>
        checks one image against reference faces enrolled for this demo profile.
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
          proactiveCue={visibleProactiveCue}
          onDismiss={onDismissHud}
        />
      </div>
      <canvas ref={canvasRef} className="camera-canvas" aria-hidden="true" />

      <MemoryHudControls
        isCameraActive={isStreamActive}
        state={hudState}
        onQuery={onHudQuery}
        proactiveCuesEnabled={proactiveCuesEnabled}
        onProactiveCuesChange={onProactiveCuesChange}
      />

      <div className="camera-controls">
        {!streamRef.current && !hasFrame && (
          <button className="secondary-button" type="button" onClick={() => void startCamera()} disabled={isStarting}>
            {isStarting ? "Starting camera..." : "Start camera"}
          </button>
        )}
        {isActive && (
          <button className="primary-button" type="button" onClick={() => void captureFrame()} disabled={isRecognizing}>
            Capture image
          </button>
        )}
        {isActive && (
          <button
            className="secondary-button"
            type="button"
            onClick={() => void recognizeCurrentFrame()}
            disabled={isRecognizing}
          >
            {isRecognizing ? "Checking..." : "Who is this?"}
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
          <button className="text-button" type="button" onClick={stopCamera} disabled={isAnalyzing || isSaving || isRecognizing}>
            Stop camera
          </button>
        )}
      </div>

      {hasFrame && (
        <div className="captured-frame">
          <div>
            <p className="captured-frame-label">Captured image</p>
            <p className="captured-frame-name">{capturedFrame?.name}</p>
          </div>
          <img
            src={capturedPreviewUrl ?? undefined}
            alt="Captured camera image"
            onError={(event) => {
              event.currentTarget.hidden = true;
              onImagePreviewError();
            }}
          />
        </div>
      )}

      {cameraError && <p className="camera-error" role="alert">{cameraError}</p>}
    </section>
  );
}
