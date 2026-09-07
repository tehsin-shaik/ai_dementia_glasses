"use client";

import { FormEvent, useState } from "react";

type QueryResult = {
  answer: string;
  intent: string;
  source_ids: string[];
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SUGGESTED_QUESTIONS = [
  "What was I doing?",
  "Where are my keys?",
  "Who is Sarah?",
  "What am I doing today?",
];

export default function Home() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [demoLoaded, setDemoLoaded] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isSeeding, setIsSeeding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadDemo() {
    setIsSeeding(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/demo/seed`, { method: "POST" });
      if (!response.ok) {
        throw new Error("The demo data could not be loaded.");
      }
      setDemoLoaded(true);
      setResult(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Something went wrong.");
    } finally {
      setIsSeeding(false);
    }
  }

  async function askQuestion(value = question) {
    const trimmedQuestion = value.trim();
    if (!trimmedQuestion) {
      return;
    }

    setQuestion(trimmedQuestion);
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: trimmedQuestion }),
      });
      if (!response.ok) {
        throw new Error("The question could not be answered.");
      }
      setResult((await response.json()) as QueryResult);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Something went wrong.");
    } finally {
      setIsLoading(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void askQuestion();
  }

  return (
    <main className="page-shell">
      <section className="app-card" aria-labelledby="page-title">
        <header className="app-header">
          <div>
            <p className="eyebrow">MemoryCue</p>
            <h1 id="page-title">MemoryCue</h1>
            <p className="subtitle">Software memory assistant prototype</p>
          </div>
          <div className={`demo-status ${demoLoaded ? "is-loaded" : ""}`}>
            <span className="status-dot" aria-hidden="true" />
            {demoLoaded ? "Demo data loaded" : "Demo data not loaded"}
          </div>
        </header>

        <div className="content-grid">
          <section className="setup-panel" aria-labelledby="demo-heading">
            <p className="section-kicker">Start with the demo</p>
            <h2 id="demo-heading">Load a small, grounded memory set.</h2>
            <p>
              This prototype uses deterministic example memories, a caregiver-provided profile,
              and today&apos;s schedule.
            </p>
            <button className="secondary-button" type="button" onClick={loadDemo} disabled={isSeeding}>
              {isSeeding ? "Loading..." : "Load demo data"}
            </button>
          </section>

          <section className="question-panel" aria-labelledby="question-heading">
            <p className="section-kicker">Ask a question</p>
            <h2 id="question-heading">What would you like to remember?</h2>
            <form className="question-form" onSubmit={handleSubmit}>
              <label className="sr-only" htmlFor="question">
                Ask MemoryCue something...
              </label>
              <input
                id="question"
                type="text"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Ask MemoryCue something..."
                autoComplete="off"
              />
              <button className="primary-button" type="submit" disabled={isLoading || !question.trim()}>
                {isLoading ? "Asking..." : "Ask"}
              </button>
            </form>

            <div className="suggestions" aria-label="Suggested questions">
              <p>Try one of these:</p>
              <div className="suggestion-list">
                {SUGGESTED_QUESTIONS.map((suggestion) => (
                  <button
                    className="suggestion-button"
                    key={suggestion}
                    type="button"
                    onClick={() => void askQuestion(suggestion)}
                    disabled={isLoading}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          </section>
        </div>

        {error && <p className="error-message" role="alert">{error}</p>}

        <section className="answer-panel" aria-live="polite" aria-labelledby="answer-heading">
          <div className="answer-heading-row">
            <div>
              <p className="section-kicker">Response</p>
              <h2 id="answer-heading">Grounded answer</h2>
            </div>
            {result && <span className="intent-badge">{result.intent}</span>}
          </div>
          {result ? (
            <>
              <p className="answer-text">{result.answer}</p>
              <details className="debug-details">
                <summary>Developer details</summary>
                <p>Source IDs: {result.source_ids.length ? result.source_ids.join(", ") : "None"}</p>
              </details>
            </>
          ) : (
            <p className="empty-answer">Load the demo data, then ask MemoryCue a question.</p>
          )}
        </section>
      </section>
    </main>
  );
}
