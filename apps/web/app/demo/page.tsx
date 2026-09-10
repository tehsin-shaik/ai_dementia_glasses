"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";

import SiteNav from "../SiteNav";
import { memoryCueFetch } from "../api";
import type { ProactiveCue } from "../MemoryHud";

type QueryResult = {
  answer: string;
  intent: string;
  source_ids: string[];
};

type MemoryListItem = {
  id: number;
  timestamp: string;
  location: string;
  description: string;
  image_url: string | null;
};

type ApiError = { detail?: string };

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEMO_PROFILES = [
  { id: 1, name: "Alex" },
  { id: 2, name: "Jordan" },
] as const;
const QUICK_QUESTIONS = ["What was I doing?", "Where are my keys?", "Who is Sarah?", "What am I doing today?"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object";
}

async function errorMessage(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as ApiError | null;
  return typeof payload?.detail === "string" ? payload.detail : fallback;
}

function parseQueryResult(payload: unknown): QueryResult {
  if (
    !isRecord(payload) ||
    typeof payload.answer !== "string" ||
    typeof payload.intent !== "string" ||
    !Array.isArray(payload.source_ids) ||
    !payload.source_ids.every((sourceId) => typeof sourceId === "string")
  ) {
    throw new Error("The question returned an invalid response.");
  }
  return payload as QueryResult;
}

function parseMemoryList(payload: unknown): MemoryListItem[] {
  if (
    !Array.isArray(payload) ||
    !payload.every(
      (memory) =>
        isRecord(memory) &&
        typeof memory.id === "number" &&
        typeof memory.timestamp === "string" &&
        typeof memory.location === "string" &&
        typeof memory.description === "string" &&
        (memory.image_url === null || typeof memory.image_url === "string"),
    )
  ) {
    throw new Error("The memory list returned an invalid response.");
  }
  return payload as MemoryListItem[];
}

function parseProactiveCues(payload: unknown): ProactiveCue[] {
  if (!isRecord(payload) || !Array.isArray(payload.cues)) {
    throw new Error("The proactive cue response was invalid.");
  }
  if (
    !payload.cues.every(
      (cue) =>
        isRecord(cue) &&
        typeof cue.id === "string" &&
        ["schedule_upcoming", "recognized_person", "important_object"].includes(String(cue.type)) &&
        typeof cue.title === "string" &&
        typeof cue.message === "string" &&
        typeof cue.priority === "number" &&
        Array.isArray(cue.source_ids) &&
        cue.source_ids.every((sourceId) => typeof sourceId === "string") &&
        (cue.expires_at === null || typeof cue.expires_at === "string"),
    )
  ) {
    throw new Error("The proactive cue response was invalid.");
  }
  return payload.cues as ProactiveCue[];
}

function imageUrl(path: string): string {
  return path.startsWith("http") ? path : `${API_URL}${path}`;
}

function displayTime(timestamp: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(timestamp));
}

export default function DemoPage() {
  const [activeUserId, setActiveUserId] = useState<number>(DEMO_PROFILES[0].id);
  const [demoLoaded, setDemoLoaded] = useState(false);
  const [isSeeding, setIsSeeding] = useState(false);
  const [memories, setMemories] = useState<MemoryListItem[]>([]);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proactiveCue, setProactiveCue] = useState<ProactiveCue | null>(null);
  const [isLoadingCues, setIsLoadingCues] = useState(false);
  const [cueError, setCueError] = useState<string | null>(null);
  const profileVersionRef = useRef(0);

  async function refreshMemories(userId = activeUserId, version = profileVersionRef.current) {
    try {
      const response = await memoryCueFetch(`${API_URL}/api/memories`, userId);
      if (!response.ok) return;
      const nextMemories = parseMemoryList(await response.json());
      if (profileVersionRef.current === version) {
        setMemories(nextMemories);
      }
    } catch {
      if (profileVersionRef.current === version) {
        setMemories([]);
      }
    }
  }

  async function refreshCues(userId = activeUserId, version = profileVersionRef.current) {
    if (profileVersionRef.current === version) {
      setIsLoadingCues(true);
      setProactiveCue(null);
      setCueError(null);
    }
    try {
      const response = await memoryCueFetch(`${API_URL}/api/cues`, userId);
      if (!response.ok) return;
      const nextCue = parseProactiveCues(await response.json())[0] ?? null;
      if (profileVersionRef.current === version) {
        setProactiveCue(nextCue);
      }
    } catch (requestError) {
      if (profileVersionRef.current === version) {
        setProactiveCue(null);
        setCueError(requestError instanceof Error ? requestError.message : "The proactive cues could not be loaded.");
      }
    } finally {
      if (profileVersionRef.current === version) {
        setIsLoadingCues(false);
      }
    }
  }

  useEffect(() => {
    const version = profileVersionRef.current + 1;
    profileVersionRef.current = version;
    setDemoLoaded(false);
    setMemories([]);
    setQuestion("");
    setResult(null);
    setIsLoading(false);
    setIsSeeding(false);
    setProactiveCue(null);
    setIsLoadingCues(false);
    setCueError(null);
    setError(null);
    void refreshMemories(activeUserId, version);
    void refreshCues(activeUserId, version);
  }, [activeUserId]);

  async function loadDemo() {
    const version = profileVersionRef.current;
    setIsSeeding(true);
    setError(null);
    try {
      const response = await memoryCueFetch(`${API_URL}/api/demo/seed`, activeUserId, { method: "POST" });
      if (!response.ok) {
        throw new Error(await errorMessage(response, "The demo data could not be reset and loaded."));
      }
      if (profileVersionRef.current !== version) return;
      setDemoLoaded(true);
      await refreshMemories(activeUserId, version);
      await refreshCues(activeUserId, version);
    } catch (requestError) {
      if (profileVersionRef.current === version) {
        setError(requestError instanceof Error ? requestError.message : "The demo data could not be reset and loaded.");
      }
    } finally {
      if (profileVersionRef.current === version) {
        setIsSeeding(false);
      }
    }
  }

  async function dismissCue() {
    if (!proactiveCue) return;
    const cue = proactiveCue;
    const version = profileVersionRef.current;
    setProactiveCue(null);
    setCueError(null);
    try {
      const response = await memoryCueFetch(
        `${API_URL}/api/cues/${encodeURIComponent(cue.id)}/dismiss`,
        activeUserId,
        { method: "POST" },
      );
      if (!response.ok) {
        throw new Error("The proactive cue could not be dismissed.");
      }
    } catch (requestError) {
      if (profileVersionRef.current === version) {
        setCueError(requestError instanceof Error ? requestError.message : "The proactive cue could not be dismissed.");
      }
    }
  }

  async function askQuestion(value = question) {
    const trimmedQuestion = value.trim();
    if (!trimmedQuestion) return;
    const version = profileVersionRef.current;
    setQuestion(trimmedQuestion);
    setIsLoading(true);
    setError(null);
    try {
      const response = await memoryCueFetch(`${API_URL}/api/query`, activeUserId, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: trimmedQuestion }),
      });
      if (!response.ok) {
        throw new Error(await errorMessage(response, "The question could not be answered."));
      }
      const nextResult = parseQueryResult(await response.json());
      if (profileVersionRef.current === version) {
        setResult(nextResult);
      }
    } catch (requestError) {
      if (profileVersionRef.current === version) {
        setError(requestError instanceof Error ? requestError.message : "The question could not be answered.");
      }
    } finally {
      if (profileVersionRef.current === version) {
        setIsLoading(false);
      }
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void askQuestion();
  }

  const activeProfile = DEMO_PROFILES.find((profile) => profile.id === activeUserId) ?? DEMO_PROFILES[0];

  return (
    <main className="demo-shell">
      <SiteNav />
      <section className="demo-page" aria-labelledby="demo-page-title">
        <header className="demo-page-header">
          <div>
            <p className="eyebrow">Development tools</p>
            <h1 id="demo-page-title">Demo workspace</h1>
            <p className="subtitle">Reset local sample data, test supported questions, and inspect API responses.</p>
          </div>
          <div className="demo-toolbar">
            <label className="profile-selector">
              <span>Profile to inspect</span>
              <select value={activeUserId} onChange={(event) => setActiveUserId(Number(event.target.value))}>
                {DEMO_PROFILES.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
              </select>
            </label>
            <button className="primary-button" type="button" onClick={() => void loadDemo()} disabled={isSeeding}>
              {isSeeding ? "Resetting and loading..." : "Reset all data and load demo"}
            </button>
          </div>
        </header>

        <div className="demo-status-card" role="status">
          <span className={`status-dot ${demoLoaded ? "is-loaded" : ""}`} aria-hidden="true" />
          <div>
            <strong>{demoLoaded ? "All demo data reset and loaded" : "Demo reset is ready"}</strong>
            <span>
              {demoLoaded
                ? `Sample data for Alex and Jordan was replaced. You are viewing ${activeProfile.name}.`
                : "This action replaces all prototype data, then loads samples for Alex and Jordan."}
            </span>
          </div>
        </div>

        <div className="demo-grid">
          <section className="demo-card demo-query-card" aria-labelledby="query-tools-heading">
            <p className="section-kicker">Query testing</p>
            <h2 id="query-tools-heading">Ask the memory system</h2>
            <form className="question-form" onSubmit={handleSubmit}>
              <label className="sr-only" htmlFor="demo-question">Ask a question</label>
              <input id="demo-question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Where are my keys?" />
              <button className="primary-button" type="submit" disabled={isLoading || !question.trim()}>{isLoading ? "Asking..." : "Ask"}</button>
            </form>
            <div className="suggestions" aria-label="Quick test questions">
              <p>Quick tests</p>
              <div className="suggestion-list">
                {QUICK_QUESTIONS.map((quickQuestion) => (
                  <button className="suggestion-button" key={quickQuestion} type="button" onClick={() => void askQuestion(quickQuestion)} disabled={isLoading}>
                    {quickQuestion}
                  </button>
                ))}
              </div>
            </div>
            {result && (
              <div className="demo-result" aria-live="polite">
                <div className="answer-heading-row">
                  <div><p className="section-kicker">Grounded response</p><h3>{result.answer}</h3></div>
                  <span className="intent-badge">{result.intent}</span>
                </div>
                <p className="source-line">Source IDs: {result.source_ids.length ? result.source_ids.join(", ") : "None"}</p>
                <details className="debug-details">
                  <summary>Raw response</summary>
                  <pre>{JSON.stringify(result, null, 2)}</pre>
                </details>
              </div>
            )}
          </section>

          <section className="demo-card" aria-labelledby="recent-memory-heading">
            <div className="recent-heading-row">
              <div><p className="section-kicker">Data check</p><h2 id="recent-memory-heading">Recent memories</h2></div>
              <span className="recent-count">{memories.length}</span>
            </div>
            {memories.length ? (
              <div className="recent-list">
                {memories.slice(0, 8).map((memory) => (
                  <article className="recent-memory" key={memory.id}>
                    {memory.image_url && <img src={imageUrl(memory.image_url)} alt="" />}
                    <div><p className="recent-time">{displayTime(memory.timestamp)}</p><p className="recent-location">{memory.location}</p><p className="recent-description">{memory.description}</p></div>
                  </article>
                ))}
              </div>
            ) : <p className="empty-answer">No memories returned for this profile.</p>}
          </section>
        </div>

        <section className="demo-card demo-cue-card" aria-labelledby="proactive-cue-heading">
          <div className="recent-heading-row">
            <div><p className="section-kicker">Proactive context</p><h2 id="proactive-cue-heading">Current cue</h2></div>
            <button className="text-button" type="button" onClick={() => void refreshCues()} disabled={isLoadingCues}>
              {isLoadingCues ? "Checking..." : "Refresh"}
            </button>
          </div>
          {proactiveCue ? (
            <div className="demo-cue-preview">
              <p className="demo-cue-preview-title">{proactiveCue.title}</p>
              <p>{proactiveCue.message}</p>
              <small>Priority {proactiveCue.priority} · {proactiveCue.source_ids.join(", ")}</small>
              <button className="secondary-button" type="button" onClick={() => void dismissCue()}>Dismiss cue</button>
            </div>
          ) : (
            <p className="empty-answer">No eligible cue returned for this profile.</p>
          )}
          {cueError && <p className="error-message" role="alert">{cueError}</p>}
        </section>

        <section className="demo-card demo-config-card" aria-labelledby="config-heading">
          <p className="section-kicker">Environment</p>
          <h2 id="config-heading">API configuration</h2>
          <div className="config-row"><span>API base URL</span><code>{API_URL}</code></div>
          <div className="config-row"><span>Vision analysis</span><strong>Not verified here; requires a configured backend provider</strong></div>
          <div className="config-row"><span>Identity header</span><code>X-MemoryCue-User-Id: {activeUserId}</code></div>
        </section>

        {error && <p className="error-message" role="alert">{error}</p>}
        <footer className="demo-footer"><Link href="/app">Open wearer app</Link><Link href="/caregiver">Open caregiver setup</Link></footer>
      </section>
    </main>
  );
}
