"use client";

import { ChangeEvent, FormEvent, SyntheticEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";

import GlassesSimulator from "./GlassesSimulator";
import { MemoryHudState } from "./MemoryHud";
import { memoryCueFetch } from "./api";

type QueryResult = {
  answer: string;
  intent: string;
  source_ids: string[];
};

type FaceRecognitionResult = {
  recognized: boolean;
  person_id: number | null;
  name: string | null;
  relationship: string | null;
  confidence: number;
};

type MemoryListItem = {
  id: number;
  timestamp: string;
  location: string;
  description: string;
  image_url: string | null;
};

type DetectedObject = {
  name: string;
  location: string | null;
  confidence: number | null;
};

type VisionAnalysis = {
  description: string;
  location: string | null;
  activity: string | null;
  objects: DetectedObject[];
};

type MemoryImageSource = "upload" | "camera" | null;

type ApiError = {
  detail?: string;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SUGGESTED_QUESTIONS = [
  "What was I doing?",
  "Where are my keys?",
  "Who is Sarah?",
  "What am I doing today?",
];
const DEMO_PROFILES = [
  { id: 1, name: "Alex" },
  { id: 2, name: "Jordan" },
] as const;

function localDateTimeValue(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

function displayTime(timestamp: string): string {
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(timestamp));
}

function imageUrl(path: string): string {
  return path.startsWith("http") ? path : `${API_URL}${path}`;
}

async function errorMessage(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as ApiError | null;
  return typeof payload?.detail === "string" ? payload.detail : fallback;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object";
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
  return {
    answer: payload.answer,
    intent: payload.intent,
    source_ids: payload.source_ids,
  };
}

function parseFaceRecognitionResult(payload: unknown): FaceRecognitionResult {
  if (
    !isRecord(payload) ||
    typeof payload.recognized !== "boolean" ||
    (payload.person_id !== null && typeof payload.person_id !== "number") ||
    (payload.name !== null && typeof payload.name !== "string") ||
    (payload.relationship !== null && typeof payload.relationship !== "string") ||
    typeof payload.confidence !== "number" ||
    payload.confidence < 0 ||
    payload.confidence > 1
  ) {
    throw new Error("Face recognition returned an invalid response.");
  }
  return payload as FaceRecognitionResult;
}

function parseVisionAnalysis(payload: unknown): VisionAnalysis {
  if (!isRecord(payload) || typeof payload.description !== "string" || !Array.isArray(payload.objects)) {
    throw new Error("The image analysis returned an invalid response.");
  }

  const objects = payload.objects;
  if (
    !objects.every(
      (object) =>
        isRecord(object) &&
        typeof object.name === "string" &&
        (object.location === null || typeof object.location === "string") &&
        (object.confidence === null || typeof object.confidence === "number"),
    )
  ) {
    throw new Error("The image analysis returned an invalid response.");
  }

  const { description, location, activity } = payload;
  if (
    (location !== null && typeof location !== "string") ||
    (activity !== null && typeof activity !== "string")
  ) {
    throw new Error("The image analysis returned an invalid response.");
  }

  return {
    description,
    location: location as string | null,
    activity: activity as string | null,
    objects: objects as DetectedObject[],
  };
}

function parseSavedMemory(payload: unknown): { location: string; object_observation_id: number | null } {
  if (
    !isRecord(payload) ||
    typeof payload.location !== "string" ||
    (payload.object_observation_id !== null && typeof payload.object_observation_id !== "number")
  ) {
    throw new Error("The memory save returned an invalid response.");
  }
  return {
    location: payload.location,
    object_observation_id: payload.object_observation_id,
  };
}

function parseMemoryList(payload: unknown): MemoryListItem[] {
  if (!Array.isArray(payload)) {
    throw new Error("The memory list returned an invalid response.");
  }
  if (
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

export default function Home() {
  const [activeUserId, setActiveUserId] = useState<number>(DEMO_PROFILES[0].id);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [hudState, setHudState] = useState<MemoryHudState>("idle");
  const [hudAnswer, setHudAnswer] = useState<string | null>(null);
  const [hudError, setHudError] = useState<string | null>(null);
  const [isRecognizingFace, setIsRecognizingFace] = useState(false);
  const [demoLoaded, setDemoLoaded] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isSeeding, setIsSeeding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [memoryImage, setMemoryImage] = useState<File | null>(null);
  const [memoryImageSource, setMemoryImageSource] = useState<MemoryImageSource>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [memoryTimestamp, setMemoryTimestamp] = useState("");
  const [memoryLocation, setMemoryLocation] = useState("");
  const [memoryActivity, setMemoryActivity] = useState("");
  const [memoryDescription, setMemoryDescription] = useState("");
  const [memoryObjectName, setMemoryObjectName] = useState("");
  const [visionAnalysis, setVisionAnalysis] = useState<VisionAnalysis | null>(null);
  const [visionMessage, setVisionMessage] = useState<string | null>(null);
  const [visionError, setVisionError] = useState(false);
  const [isAnalyzingVision, setIsAnalyzingVision] = useState(false);
  const [isSavingMemory, setIsSavingMemory] = useState(false);
  const [cameraSaved, setCameraSaved] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [recentMemories, setRecentMemories] = useState<MemoryListItem[]>([]);
  const hudRequestRef = useRef(0);
  const profileVersionRef = useRef(0);

  const activeProfile = DEMO_PROFILES.find((profile) => profile.id === activeUserId) ?? DEMO_PROFILES[0];

  useEffect(() => {
    setMemoryTimestamp(localDateTimeValue(new Date()));
    setRecentMemories([]);
    void refreshMemories(activeUserId, profileVersionRef.current);
  }, [activeUserId]);

  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  async function refreshMemories(
    userId = activeUserId,
    profileVersion = profileVersionRef.current,
  ) {
    try {
      const response = await memoryCueFetch(`${API_URL}/api/memories`, userId);
      if (response.ok && profileVersionRef.current === profileVersion) {
        setRecentMemories(parseMemoryList(await response.json()));
      }
    } catch {
      // The page remains usable when the API has not been started yet.
    }
  }

  async function loadDemo() {
    const requestUserId = activeUserId;
    const requestProfileVersion = profileVersionRef.current;
    setIsSeeding(true);
    setError(null);
    setSaveMessage(null);
    try {
      const response = await memoryCueFetch(`${API_URL}/api/demo/seed`, requestUserId, { method: "POST" });
      if (!response.ok) {
        throw new Error(await errorMessage(response, "The demo data could not be loaded."));
      }
      if (profileVersionRef.current !== requestProfileVersion) {
        return;
      }
      setDemoLoaded(true);
      await refreshMemories(requestUserId, requestProfileVersion);
    } catch (requestError) {
      if (profileVersionRef.current === requestProfileVersion) {
        setError(requestError instanceof Error ? requestError.message : "Something went wrong.");
      }
    } finally {
      if (profileVersionRef.current === requestProfileVersion) {
        setIsSeeding(false);
      }
    }
  }

  function dismissHud() {
    hudRequestRef.current += 1;
    setHudState("idle");
    setHudAnswer(null);
    setHudError(null);
  }

  async function submitQuery(value: string, surface: "normal" | "hud") {
    const trimmedQuestion = value.trim();
    if (!trimmedQuestion) {
      return;
    }
    const requestUserId = activeUserId;
    const requestProfileVersion = profileVersionRef.current;
    const hudRequestId = surface === "hud" ? hudRequestRef.current + 1 : 0;

    if (surface === "normal") {
      setQuestion(trimmedQuestion);
      setIsLoading(true);
      setError(null);
    } else {
      hudRequestRef.current = hudRequestId;
      setHudState("querying");
      setHudAnswer(null);
      setHudError(null);
    }

    try {
      const response = await memoryCueFetch(`${API_URL}/api/query`, requestUserId, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: trimmedQuestion }),
      });
      if (!response.ok) {
        throw new Error(await errorMessage(response, "The question could not be answered."));
      }
      const queryResult = parseQueryResult(await response.json());
      if (profileVersionRef.current !== requestProfileVersion) {
        return;
      }
      setResult(queryResult);
      if (surface === "hud" && hudRequestRef.current === hudRequestId) {
        setHudAnswer(queryResult.answer);
        setHudState(queryResult.intent === "unknown" ? "unknown" : "result");
      }
    } catch (requestError) {
      if (profileVersionRef.current !== requestProfileVersion) {
        return;
      }
      const message = requestError instanceof Error ? requestError.message : "Something went wrong.";
      if (surface === "hud") {
        if (hudRequestRef.current === hudRequestId) {
          setHudError(message);
          setHudState("error");
        }
      } else {
        setError(message);
      }
    } finally {
      if (surface === "normal" && profileVersionRef.current === requestProfileVersion) {
        setIsLoading(false);
      }
    }
  }

  async function askQuestion(value = question) {
    await submitQuery(value, "normal");
  }

  function askHudQuestion(value: string) {
    void submitQuery(value, "hud");
  }

  async function recognizePerson(file: File) {
    const requestUserId = activeUserId;
    const requestProfileVersion = profileVersionRef.current;
    const hudRequestId = hudRequestRef.current + 1;
    hudRequestRef.current = hudRequestId;
    setIsRecognizingFace(true);
    setHudState("querying");
    setHudAnswer(null);
    setHudError(null);

    const formData = new FormData();
    formData.append("image", file);
    try {
      const response = await memoryCueFetch(`${API_URL}/api/face/recognize`, requestUserId, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        throw new Error(await errorMessage(response, "The person could not be checked."));
      }
      const recognition = parseFaceRecognitionResult(await response.json());
      if (
        profileVersionRef.current !== requestProfileVersion ||
        hudRequestRef.current !== hudRequestId
      ) {
        return;
      }
      if (recognition.recognized && recognition.name && recognition.relationship) {
        setHudAnswer(`${recognition.name}\nYour ${recognition.relationship.toLowerCase()}`);
        setHudState("result");
      } else {
        setHudAnswer("I don't recognize this person.");
        setHudState("unknown");
      }
    } catch (requestError) {
      if (
        profileVersionRef.current === requestProfileVersion &&
        hudRequestRef.current === hudRequestId
      ) {
        setHudError(requestError instanceof Error ? requestError.message : "The person could not be checked.");
        setHudState("error");
      }
    } finally {
      if (profileVersionRef.current === requestProfileVersion) {
        setIsRecognizingFace(false);
      }
    }
  }

  async function saveMemory() {
    if (!memoryImage) {
      setError("Choose an image before saving the memory.");
      return;
    }
    if (!memoryTimestamp || !memoryLocation.trim() || !memoryDescription.trim()) {
      setError("Time, location, and description are required.");
      return;
    }

    setIsSavingMemory(true);
    setError(null);
    setSaveMessage(null);
    const requestUserId = activeUserId;
    const requestProfileVersion = profileVersionRef.current;
    const formData = new FormData();
    formData.append("image", memoryImage);
    formData.append("timestamp", memoryTimestamp);
    formData.append("location", memoryLocation);
    formData.append("description", memoryDescription);
    if (memoryActivity.trim()) {
      formData.append("activity", memoryActivity);
    }
    if (memoryObjectName.trim()) {
      formData.append("object_name", memoryObjectName);
    }

    try {
      const response = await memoryCueFetch(`${API_URL}/api/memories`, requestUserId, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        throw new Error(await errorMessage(response, "The memory could not be saved."));
      }
      const savedMemory = parseSavedMemory(await response.json());
      if (profileVersionRef.current !== requestProfileVersion) {
        return;
      }
      setSaveMessage(
        savedMemory.object_observation_id
          ? `Memory saved — ${memoryObjectName.trim()} observed at ${savedMemory.location}.`
          : "Memory saved.",
      );
      if (memoryImageSource === "camera") {
        setCameraSaved(true);
      }
      await refreshMemories(requestUserId, requestProfileVersion);
    } catch (requestError) {
      if (profileVersionRef.current === requestProfileVersion) {
        setError(requestError instanceof Error ? requestError.message : "Something went wrong.");
      }
    } finally {
      if (profileVersionRef.current === requestProfileVersion) {
        setIsSavingMemory(false);
      }
    }
  }

  async function analyzeImage() {
    if (!memoryImage) {
      setVisionError(true);
      setVisionMessage("Choose an image before asking MemoryCue to analyze it.");
      return;
    }

    setIsAnalyzingVision(true);
    setVisionError(false);
    setVisionMessage(null);
    setError(null);
    setSaveMessage(null);
    const requestUserId = activeUserId;
    const requestProfileVersion = profileVersionRef.current;
    const formData = new FormData();
    formData.append("image", memoryImage);

    try {
      const response = await memoryCueFetch(`${API_URL}/api/vision/analyze`, requestUserId, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        throw new Error(await errorMessage(response, "The image could not be analyzed."));
      }

      const analysis = parseVisionAnalysis(await response.json());
      if (profileVersionRef.current !== requestProfileVersion) {
        return;
      }
      setVisionAnalysis(analysis);
      setCameraSaved(false);
      setMemoryLocation(analysis.location ?? "");
      setMemoryActivity(analysis.activity ?? "");
      setMemoryDescription(analysis.description);
      setMemoryObjectName(analysis.objects[0]?.name ?? "");
      setVisionMessage("AI suggestions added below. Review or edit them before saving.");
    } catch (requestError) {
      if (profileVersionRef.current === requestProfileVersion) {
        setVisionError(true);
        setVisionMessage(
          `${requestError instanceof Error ? requestError.message : "The image could not be analyzed."} You can still complete the form manually.`,
        );
      }
    } finally {
      if (profileVersionRef.current === requestProfileVersion) {
        setIsAnalyzingVision(false);
      }
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void askQuestion();
  }

  function handleImagePreviewError(event: SyntheticEvent<HTMLImageElement>) {
    event.currentTarget.hidden = true;
    setError("A memory image could not be displayed.");
  }

  function reportImagePreviewError() {
    setError("A memory image could not be displayed.");
  }

  function handleImageChange(event: ChangeEvent<HTMLInputElement>) {
    const nextFile = event.target.files?.[0] ?? null;
    setMemoryImage(nextFile);
    setMemoryImageSource(nextFile ? "upload" : null);
    setSaveMessage(null);
    setError(null);
    setVisionAnalysis(null);
    setVisionMessage(null);
    setVisionError(false);
    setCameraSaved(false);
    setPreviewUrl(nextFile ? URL.createObjectURL(nextFile) : null);
    dismissHud();
  }

  function handleCameraCapture(file: File) {
    setMemoryImage(file);
    setMemoryImageSource("camera");
    setMemoryTimestamp(localDateTimeValue(new Date()));
    setMemoryLocation("");
    setMemoryActivity("");
    setMemoryDescription("");
    setMemoryObjectName("");
    setVisionAnalysis(null);
    setVisionMessage(null);
    setVisionError(false);
    setCameraSaved(false);
    setSaveMessage(null);
    setError(null);
    setPreviewUrl(URL.createObjectURL(file));
    dismissHud();
  }

  function handleCameraRetake() {
    setMemoryImage(null);
    setMemoryImageSource(null);
    setMemoryLocation("");
    setMemoryActivity("");
    setMemoryDescription("");
    setMemoryObjectName("");
    setVisionAnalysis(null);
    setVisionMessage(null);
    setVisionError(false);
    setCameraSaved(false);
    setSaveMessage(null);
    setError(null);
    setPreviewUrl(null);
    dismissHud();
  }

  function handleProfileChange(event: ChangeEvent<HTMLSelectElement>) {
    const nextUserId = Number(event.target.value);
    if (!DEMO_PROFILES.some((profile) => profile.id === nextUserId)) {
      return;
    }
    profileVersionRef.current += 1;
    setActiveUserId(nextUserId);
    setQuestion("");
    setResult(null);
    setRecentMemories([]);
    setIsLoading(false);
    setIsSeeding(false);
    setIsAnalyzingVision(false);
    setIsSavingMemory(false);
    setIsRecognizingFace(false);
    handleCameraRetake();
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
          <div className="header-actions">
            <Link className="caregiver-link" href="/caregiver">
              Caregiver setup
            </Link>
            <label className="profile-selector">
              <span>Development profile</span>
              <select value={activeUserId} onChange={handleProfileChange}>
                {DEMO_PROFILES.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.name}
                  </option>
                ))}
              </select>
              <small>{activeProfile.name}&apos;s private demo context · not authentication</small>
            </label>
            <div className={`demo-status ${demoLoaded ? "is-loaded" : ""}`}>
              <span className="status-dot" aria-hidden="true" />
              {demoLoaded ? "Demo data loaded" : "Demo data not loaded"}
            </div>
          </div>
        </header>

        <div className="content-grid">
          <section className="setup-panel" aria-labelledby="demo-heading">
            <p className="section-kicker">Start with the demo</p>
            <h2 id="demo-heading">Load a small, grounded memory set.</h2>
            <p>
              This prototype uses deterministic example memories, a pre-seeded person record, and today&apos;s schedule.
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

        <GlassesSimulator
          capturedFrame={memoryImageSource === "camera" ? memoryImage : null}
          capturedPreviewUrl={memoryImageSource === "camera" ? previewUrl : null}
          isAnalyzing={isAnalyzingVision && memoryImageSource === "camera"}
          isSaving={isSavingMemory && memoryImageSource === "camera"}
          analysisComplete={Boolean(visionAnalysis && memoryImageSource === "camera")}
          saved={cameraSaved}
          onCapture={handleCameraCapture}
          onRetake={handleCameraRetake}
          onAnalyze={() => void analyzeImage()}
          onRecognize={(file) => void recognizePerson(file)}
          isRecognizing={isRecognizingFace}
          hudState={hudState}
          hudAnswer={hudAnswer}
          hudError={hudError}
          onHudQuery={askHudQuestion}
          onDismissHud={dismissHud}
          onImagePreviewError={reportImagePreviewError}
        />

        <section className="memory-panel" aria-labelledby="memory-heading">
          <div className="memory-panel-heading">
            <div>
              <p className="section-kicker">Manual memory creation</p>
              <h2 id="memory-heading">Add a memory</h2>
            </div>
            <p className="memory-helper">Use AI to suggest details, then review them. You can always enter the memory manually.</p>
          </div>

          <div className="memory-form">
            <label className="file-picker">
              <span>Image</span>
              <input
                type="file"
                accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
                onChange={handleImageChange}
              />
            </label>
            {memoryImage && (
              <div className="selected-image">
                {previewUrl && (
                  <img src={previewUrl} alt="Selected memory preview" onError={handleImagePreviewError} />
                )}
                <div>
                  <strong>{memoryImage.name}</strong>
                  <span>{Math.max(1, Math.round(memoryImage.size / 1024))} KB selected</span>
                </div>
              </div>
            )}
            <div className="analysis-actions">
              <button
                className="secondary-button"
                type="button"
                onClick={() => void analyzeImage()}
                disabled={!memoryImage || isAnalyzingVision || isSavingMemory}
              >
                {isAnalyzingVision ? "Analyzing..." : "Analyze with AI"}
              </button>
              {visionMessage && (
                <p className={`vision-status ${visionError ? "is-error" : ""}`} role="status">
                  {visionMessage}
                </p>
              )}
            </div>
            {visionAnalysis && (
              <div className="ai-suggestions" role="status">
                <strong>AI suggestions — review before saving</strong>
                <span>
                  Visible objects: {visionAnalysis.objects.length
                    ? visionAnalysis.objects.map((object) => object.name).join(", ")
                    : "none identified"}
                </span>
              </div>
            )}

            <div className="memory-form-grid">
              <label>
                <span>Time</span>
                <input
                  type="datetime-local"
                  value={memoryTimestamp}
                  onChange={(event) => setMemoryTimestamp(event.target.value)}
                />
              </label>
              <label>
                <span>Location</span>
                <input
                  type="text"
                  value={memoryLocation}
                  onChange={(event) => setMemoryLocation(event.target.value)}
                  placeholder="e.g. Kitchen counter"
                />
              </label>
            </div>
            <label>
              <span>Description</span>
              <textarea
                value={memoryDescription}
                onChange={(event) => setMemoryDescription(event.target.value)}
                placeholder="e.g. I left my keys on the kitchen counter."
                rows={3}
              />
            </label>
            <label>
              <span>Activity <em>(optional)</em></span>
              <input
                type="text"
                value={memoryActivity}
                onChange={(event) => setMemoryActivity(event.target.value)}
                placeholder="e.g. preparing to leave"
              />
            </label>
            <label>
              <span>Object <em>(optional)</em></span>
              <input
                type="text"
                value={memoryObjectName}
                onChange={(event) => setMemoryObjectName(event.target.value)}
                placeholder="e.g. keys"
              />
            </label>
            <div className="save-row">
              <button className="primary-button" type="button" onClick={saveMemory} disabled={isSavingMemory}>
                {isSavingMemory ? "Saving..." : "Save memory"}
              </button>
              {saveMessage && <p className="success-message" role="status">{saveMessage}</p>}
            </div>
          </div>
        </section>

        {recentMemories.length > 0 && (
          <section className="recent-panel" aria-labelledby="recent-heading">
            <div className="recent-heading-row">
              <div>
                <p className="section-kicker">Stored context</p>
                <h2 id="recent-heading">Recent memories</h2>
              </div>
              <span className="recent-count">Showing {Math.min(recentMemories.length, 5)}</span>
            </div>
            <div className="recent-list">
              {recentMemories.slice(0, 5).map((memory) => (
                <article className="recent-memory" key={memory.id}>
                  {memory.image_url && <img src={imageUrl(memory.image_url)} alt="" onError={handleImagePreviewError} />}
                  <div>
                    <p className="recent-time">{displayTime(memory.timestamp)}</p>
                    <p className="recent-location">{memory.location}</p>
                    <p className="recent-description">{memory.description}</p>
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}

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
