"use client";

import { FormEvent, useState } from "react";

export type MemoryHudState = "idle" | "querying" | "result" | "unknown" | "error";

export type ProactiveCue = {
  id: string;
  type: "schedule_upcoming" | "recognized_person" | "important_object";
  title: string;
  message: string;
  priority: number;
  source_ids: string[];
  expires_at: string | null;
};

type MemoryHudOverlayProps = {
  state: MemoryHudState;
  answer: string | null;
  error: string | null;
  proactiveCue: ProactiveCue | null;
  onDismiss: () => void;
};

type MemoryHudControlsProps = {
  isCameraActive: boolean;
  state: MemoryHudState;
  onQuery: (question: string) => void;
  proactiveCuesEnabled: boolean;
  onProactiveCuesChange: (enabled: boolean) => void;
};

const QUICK_ACTIONS = [
  "What was I doing?",
  "Where are my keys?",
  "What am I doing today?",
];

export function MemoryHudOverlay({ state, answer, error, proactiveCue, onDismiss }: MemoryHudOverlayProps) {
  if (state === "idle" && !proactiveCue) {
    return null;
  }

  const isProactive = state === "idle" && proactiveCue !== null;
  const isError = state === "error" && !isProactive;
  const isUnknown = state === "unknown" && !isProactive;
  const heading = state === "querying"
    ? "Checking memory"
    : isProactive
      ? "MemoryCue · Optional cue"
      : isError
        ? "MemoryCue unavailable"
        : "MemoryCue";
  const message = state === "querying" ? "Looking that up..." : isProactive ? proactiveCue.message : isError ? error : answer;

  return (
    <aside className={`hud-overlay hud-overlay-${state}`} aria-live="polite" aria-label="MemoryCue camera cue">
      <div className="hud-overlay-heading">
        <span className="hud-overlay-label">{heading}</span>
        <button className="hud-dismiss-button" type="button" onClick={onDismiss}>
          Dismiss
        </button>
      </div>
      {isProactive && <strong className="hud-overlay-cue-title">{proactiveCue.title}</strong>}
      <p className={`hud-overlay-message ${isUnknown ? "is-unknown" : ""}`}>
        {message ?? "I couldn't find matching saved information."}
      </p>
    </aside>
  );
}

export function MemoryHudControls({
  isCameraActive,
  state,
  onQuery,
  proactiveCuesEnabled,
  onProactiveCuesChange,
}: MemoryHudControlsProps) {
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
    <div className="hud-controls" aria-label="MemoryCue camera cue controls">
      <div className="hud-controls-heading">
        <div>
          <p className="section-kicker">Camera cues</p>
          <h3>Ask for a cue</h3>
        </div>
        <div className="hud-control-mode-row">
          <span className="hud-mode-label">Questions</span>
          <label className="hud-proactive-toggle">
            <span>Optional cues</span>
            <input
              type="checkbox"
              checked={proactiveCuesEnabled}
              onChange={(event) => onProactiveCuesChange(event.target.checked)}
            />
            <span aria-hidden="true">{proactiveCuesEnabled ? "On" : "Off"}</span>
          </label>
        </div>
      </div>
      <form className="hud-query-form" onSubmit={submitQuestion}>
        <label htmlFor="hud-question">Ask MemoryCue</label>
        <div className="hud-query-input-row">
          <input
            id="hud-question"
            type="text"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Where are my keys?"
            disabled={isDisabled}
          />
          <button className="primary-button" type="submit" disabled={isDisabled || !question.trim()}>
            {isQuerying ? "Checking..." : "Ask"}
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
        {isCameraActive
          ? "Questions run only when you choose Ask. Optional cues use saved context and can be turned off."
          : "Start the camera to use cues in the preview."}
      </p>
    </div>
  );
}
