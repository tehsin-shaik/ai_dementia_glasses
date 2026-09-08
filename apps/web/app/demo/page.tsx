"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import SiteNav from "../SiteNav";
import { memoryCueFetch } from "../api";

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

  async function refreshMemories(userId = activeUserId) {
    try {
      const response = await memoryCueFetch(`${API_URL}/api/memories`, userId);
      if (!response.ok) return;
      setMemories(parseMemoryList(await response.json()));
    } catch {
      setMemories([]);
    }
  }

  useEffect(() => {
    void refreshMemories(activeUserId);
  }, [activeUserId]);

  async function loadDemo() {
    setIsSeeding(true);
    setError(null);
    try {
      const response = await memoryCueFetch(`${API_URL}/api/demo/seed`, activeUserId, { method: "POST" });
      if (!response.ok) {
        throw new Error(await errorMessage(response, "The demo data could not be loaded."));
      }
      setDemoLoaded(true);
      await refreshMemories(activeUserId);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The demo data could not be loaded.");
    } finally {
      setIsSeeding(false);
    }
  }

  async function askQuestion(value = question) {
    const trimmedQuestion = value.trim();
    if (!trimmedQuestion) return;
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
      setResult(parseQueryResult(await response.json()));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The question could not be answered.");
    } finally {
      setIsLoading(false);
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
            <p className="subtitle">Seed a profile, exercise the memory loop, and inspect grounded responses.</p>
          </div>
          <div className="demo-toolbar">
            <label className="profile-selector">
              <span>Active profile</span>
              <select value={activeUserId} onChange={(event) => setActiveUserId(Number(event.target.value))}>
                {DEMO_PROFILES.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
              </select>
            </label>
            <button className="primary-button" type="button" onClick={() => void loadDemo()} disabled={isSeeding}>
              {isSeeding ? "Seeding..." : "Load demo data"}
            </button>
          </div>
        </header>

        <div className="demo-status-card" role="status">
          <span className={`status-dot ${demoLoaded ? "is-loaded" : ""}`} aria-hidden="true" />
          <div>
            <strong>{demoLoaded ? `${activeProfile.name} demo is ready` : "Demo data has not been loaded"}</strong>
            <span>{demoLoaded ? "The wearer app can now answer from seeded context." : "Load deterministic sample context before testing queries."}</span>
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
            ) : <p className="empty-answer">No memories loaded for this profile.</p>}
          </section>
        </div>

        <section className="demo-card demo-config-card" aria-labelledby="config-heading">
          <p className="section-kicker">Environment</p>
          <h2 id="config-heading">AI and API status</h2>
          <div className="config-row"><span>API base URL</span><code>{API_URL}</code></div>
          <div className="config-row"><span>Vision analysis</span><strong>Available through the wearer app</strong></div>
          <div className="config-row"><span>Identity header</span><code>X-MemoryCue-User-Id: {activeUserId}</code></div>
        </section>

        {error && <p className="error-message" role="alert">{error}</p>}
        <footer className="demo-footer"><Link href="/app">Open wearer app</Link><Link href="/caregiver">Open caregiver setup</Link></footer>
      </section>
    </main>
  );
}
