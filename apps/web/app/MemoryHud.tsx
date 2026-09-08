"use client";

import { FormEvent, useState } from "react";

export type MemoryHudState = "idle" | "querying" | "result" | "unknown" | "error";

type MemoryHudOverlayProps = {
  state: MemoryHudState;
  answer: string | null;
  error: string | null;
  onDismiss: () => void;
};

type MemoryHudControlsProps = {
  isCameraActive: boolean;
  state: MemoryHudState;
  onQuery: (question: string) => void;
};

const QUICK_ACTIONS = [
  "What was I doing?",
  "Where are my keys?",
  "What am I doing today?",
];

export function MemoryHudOverlay({ state, answer, error, onDismiss }: MemoryHudOverlayProps) {
  if (state === "idle") {
    return null;
  }

  const isError = state === "error";
  const isUnknown = state === "unknown";
  const heading = state === "querying" ? "Checking memory" : isError ? "MemoryCue unavailable" : "MemoryCue cue";
  const message = state === "querying" ? "Looking that up..." : isError ? error : answer;

  return (
    <aside className={`hud-overlay hud-overlay-${state}`} aria-live="polite" aria-label="MemoryCue HUD cue">
      <div className="hud-overlay-heading">
        <span className="hud-overlay-label">{heading}</span>
        <button className="hud-dismiss-button" type="button" onClick={onDismiss}>
          Dismiss
        </button>
      </div>
      <p className={`hud-overlay-message ${isUnknown ? "is-unknown" : ""}`}>
        {message ?? "MemoryCue does not have an answer for that yet."}
      </p>
    </aside>
  );
}

export function MemoryHudControls({ isCameraActive, state, onQuery }: MemoryHudControlsProps) {
  const [question, setQuestion] = useState("");
  const isQuerying = state === "querying";
  const isDisabled = !isCameraActive || isQuerying;

  function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || isDisabled) {
      return;
    }
    onQuery(trimmedQuestion);
  }

  return (
    <div className="hud-controls" aria-label="MemoryCue glasses HUD controls">
      <div className="hud-controls-heading">
        <div>
          <p className="section-kicker">Wearer view</p>
          <h3>Memory HUD</h3>
        </div>
        <span className="hud-mode-label">Manual cue</span>
      </div>
      <form className="hud-query-form" onSubmit={submitQuestion}>
        <label htmlFor="hud-question">Ask MemoryCue</label>
        <div className="hud-query-input-row">
          <input
            id="hud-question"
            type="text"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask about something you remember"
            disabled={isDisabled}
          />
          <button className="primary-button" type="submit" disabled={isDisabled || !question.trim()}>
            {isQuerying ? "Checking..." : "Show cue"}
          </button>
        </div>
      </form>
      <div className="hud-quick-actions">
        <span>Quick cues</span>
        <div>
          {QUICK_ACTIONS.map((action) => (
            <button
              className="hud-quick-button"
              key={action}
              type="button"
              onClick={() => onQuery(action)}
              disabled={isDisabled}
            >
              {action}
            </button>
          ))}
        </div>
      </div>
      <p className="hud-controls-helper">
        {isCameraActive ? "Ask when you need a short contextual reminder." : "Start the camera to enable HUD cues."}
      </p>
    </div>
  );
}
