"use client";

import { ChangeEvent, FormEvent, SyntheticEvent, useCallback, useEffect, useRef, useState } from "react";
import GlassesSimulator from "./GlassesSimulator";
import { MemoryHudState, ProactiveCue } from "./MemoryHud";
import { memoryCueFetch } from "./api";
import SiteNav from "./SiteNav";

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

type CuePresentationAttempt = {
  key: string;
  presentationId: string;
  attempts: number;
  status: "idle" | "pending" | "acknowledged" | "failed";
  retryTimer: number | null;
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
    throw new Error("The person check returned an invalid response.");
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

function cueIsUnexpired(cue: ProactiveCue, now = Date.now()): boolean {
  return !cue.expires_at || new Date(cue.expires_at).getTime() > now;
}

export default function WearerApp() {
  const [activeUserId, setActiveUserId] = useState<number>(DEMO_PROFILES[0].id);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [hudState, setHudState] = useState<MemoryHudState>("idle");
  const [hudAnswer, setHudAnswer] = useState<string | null>(null);
  const [hudError, setHudError] = useState<string | null>(null);
  const [isRecognizingFace, setIsRecognizingFace] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
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
  const [proactiveCuesEnabled, setProactiveCuesEnabled] = useState(true);
  const [proactiveCue, setProactiveCue] = useState<ProactiveCue | null>(null);
  const [proactiveRefreshToken, setProactiveRefreshToken] = useState(0);
  const hudRequestRef = useRef(0);
  const profileVersionRef = useRef(0);
  const proactiveRequestRef = useRef(0);
  const dismissedCueKeysRef = useRef<Set<string>>(new Set());
  const activeUserIdRef = useRef(activeUserId);
  const proactiveCuesEnabledRef = useRef(proactiveCuesEnabled);
  const proactiveCueRef = useRef<ProactiveCue | null>(proactiveCue);
  const visibleProactiveCueRef = useRef<ProactiveCue | null>(null);
  const cuePresentationRef = useRef<CuePresentationAttempt | null>(null);

  activeUserIdRef.current = activeUserId;
  proactiveCuesEnabledRef.current = proactiveCuesEnabled;
  proactiveCueRef.current = proactiveCue;

  const activeProfile = DEMO_PROFILES.find((profile) => profile.id === activeUserId) ?? DEMO_PROFILES[0];

  useEffect(() => {
    setMemoryTimestamp(localDateTimeValue(new Date()));
  }, [activeUserId]);

  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  useEffect(() => {
    const requestGeneration = proactiveRequestRef.current + 1;
    proactiveRequestRef.current = requestGeneration;
    const requestUserId = activeUserId;
    const requestProfileVersion = profileVersionRef.current;
    const controller = new AbortController();

    if (!proactiveCuesEnabled) {
      setProactiveCue(null);
      return () => {
        controller.abort();
        proactiveRequestRef.current += 1;
      };
    }

    async function pollForCue() {
      try {
        const response = await memoryCueFetch(`${API_URL}/api/cues`, requestUserId, {
          signal: controller.signal,
        });
        if (!response.ok) return;
        const nextCue = parseProactiveCues(await response.json())[0] ?? null;
        if (
          proactiveRequestRef.current !== requestGeneration ||
          profileVersionRef.current !== requestProfileVersion
        ) {
          return;
        }
        const cueKey = nextCue ? `${requestUserId}:${nextCue.id}` : null;
        const availableCue = cueKey && dismissedCueKeysRef.current.has(cueKey) ? null : nextCue;
        setProactiveCue((currentCue) => {
          if (availableCue) {
            return availableCue;
          }
          return currentCue && cueIsUnexpired(currentCue) ? currentCue : null;
        });
      } catch (requestError) {
        if (requestError instanceof DOMException && requestError.name === "AbortError") {
          return;
        }
        // Proactive polling is best-effort and should not interrupt manual cues.
      }
    }

    void pollForCue();
    const intervalId = window.setInterval(() => void pollForCue(), 45_000);
    return () => {
      window.clearInterval(intervalId);
      controller.abort();
      proactiveRequestRef.current += 1;
    };
  }, [activeUserId, proactiveCuesEnabled, proactiveRefreshToken]);

  useEffect(() => {
    if (!proactiveCue?.expires_at) {
      return;
    }
    const cueId = proactiveCue.id;
    const delay = Math.max(0, new Date(proactiveCue.expires_at).getTime() - Date.now());
    const timeoutId = window.setTimeout(() => {
      setProactiveCue((currentCue) => currentCue?.id === cueId ? null : currentCue);
    }, delay + 10);
    function clearExpiredCueAfterVisibilityChange() {
      if (document.visibilityState === "visible") {
        setProactiveCue((currentCue) =>
          currentCue && cueIsUnexpired(currentCue) ? currentCue : null,
        );
      }
    }
    document.addEventListener("visibilitychange", clearExpiredCueAfterVisibilityChange);
    return () => {
      window.clearTimeout(timeoutId);
      document.removeEventListener("visibilitychange", clearExpiredCueAfterVisibilityChange);
    };
  }, [proactiveCue]);

  useEffect(() => {
    return () => {
      const retryTimer = cuePresentationRef.current?.retryTimer;
      if (retryTimer !== null && retryTimer !== undefined) {
        window.clearTimeout(retryTimer);
      }
    };
  }, []);

  const handleProactiveCueVisibilityChange = useCallback((cue: ProactiveCue | null) => {
    visibleProactiveCueRef.current = cue;
    if (!cue) {
      if (!proactiveCueRef.current) {
        const retryTimer = cuePresentationRef.current?.retryTimer;
        if (retryTimer !== null && retryTimer !== undefined) {
          window.clearTimeout(retryTimer);
        }
        cuePresentationRef.current = null;
      }
      return;
    }

    const requestUserId = activeUserIdRef.current;
    const requestProfileVersion = profileVersionRef.current;
    const key = `${requestUserId}:${cue.id}`;
    let attempt = cuePresentationRef.current;
    if (!attempt || attempt.key !== key) {
      if (attempt?.retryTimer !== null && attempt?.retryTimer !== undefined) {
        window.clearTimeout(attempt.retryTimer);
      }
      attempt = {
        key,
        presentationId: crypto.randomUUID(),
        attempts: 0,
        status: "idle",
        retryTimer: null,
      };
      cuePresentationRef.current = attempt;
    }
    const presentationAttempt = attempt;
    const cueToAcknowledge = cue;

    async function acknowledgeVisibleCue() {
      const visibleCue = visibleProactiveCueRef.current;
      if (
        cuePresentationRef.current !== presentationAttempt ||
        presentationAttempt.status === "pending" ||
        presentationAttempt.status === "acknowledged" ||
        presentationAttempt.status === "failed" ||
        presentationAttempt.attempts >= 2 ||
        activeUserIdRef.current !== requestUserId ||
        profileVersionRef.current !== requestProfileVersion ||
        !proactiveCuesEnabledRef.current ||
        document.visibilityState !== "visible" ||
        visibleCue?.id !== cueToAcknowledge.id ||
        proactiveCueRef.current?.id !== cueToAcknowledge.id ||
        !cueIsUnexpired(cueToAcknowledge)
      ) {
        return;
      }

      presentationAttempt.status = "pending";
      presentationAttempt.attempts += 1;
      try {
        const response = await memoryCueFetch(`${API_URL}/api/cues/present`, requestUserId, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cue_id: cueToAcknowledge.id, presentation_id: presentationAttempt.presentationId }),
        });
        if (!response.ok) {
          const requestError = new Error("The proactive cue presentation could not be acknowledged.");
          Object.assign(requestError, { status: response.status });
          throw requestError;
        }
        if (cuePresentationRef.current === presentationAttempt) {
          presentationAttempt.status = "acknowledged";
        }
      } catch (requestError) {
        if (cuePresentationRef.current !== presentationAttempt) {
          return;
        }
        const status = isRecord(requestError) && typeof requestError.status === "number"
          ? requestError.status
          : null;
        if (presentationAttempt.attempts < 2 && (status === null || status >= 500)) {
          presentationAttempt.status = "idle";
          presentationAttempt.retryTimer = window.setTimeout(() => {
            presentationAttempt.retryTimer = null;
            void acknowledgeVisibleCue();
          }, 750);
        } else {
          presentationAttempt.status = "failed";
        }
      }
    }

    void acknowledgeVisibleCue();
  }, []);

  function clearProactiveCue() {
    setProactiveCue(null);
  }

  async function dismissProactiveCue(cue: ProactiveCue) {
    const requestUserId = activeUserId;
    const requestProfileVersion = profileVersionRef.current;
    const cueKey = `${requestUserId}:${cue.id}`;
    dismissedCueKeysRef.current.add(cueKey);
    try {
      const response = await memoryCueFetch(
        `${API_URL}/api/cues/${encodeURIComponent(cue.id)}/dismiss`,
        requestUserId,
        { method: "POST" },
      );
      if (!response.ok) {
        throw new Error("The proactive cue could not be dismissed.");
      }
    } catch (requestError) {
      dismissedCueKeysRef.current.delete(cueKey);
      if (profileVersionRef.current === requestProfileVersion) {
        setError(requestError instanceof Error ? requestError.message : "The proactive cue could not be dismissed.");
      }
    }
  }

  function clearHud() {
    hudRequestRef.current += 1;
    setHudState("idle");
    setHudAnswer(null);
    setHudError(null);
    clearProactiveCue();
  }

  function dismissHud() {
    const cue = proactiveCue;
    clearHud();
    if (cue) {
      void dismissProactiveCue(cue);
    }
  }

  async function submitQuery(value: string, surface: "normal" | "hud") {
    const trimmedQuestion = value.trim();
    if (!trimmedQuestion) {
      return;
    }
    const requestUserId = activeUserId;
    const requestProfileVersion = profileVersionRef.current;
    const hudRequestId = surface === "hud" ? hudRequestRef.current + 1 : 0;
    clearProactiveCue();

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
        setProactiveRefreshToken((token) => token + 1);
      } else {
        setHudAnswer("I couldn't match this person to an enrolled face.");
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
      setError("Upload or capture an image before saving a memory.");
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
          ? `Memory saved. ${memoryObjectName.trim()} was recorded at ${savedMemory.location}.`
          : "Memory saved.",
      );
      if (memoryImageSource === "camera") {
        setCameraSaved(true);
      }
    } catch (requestError) {
      if (profileVersionRef.current === requestProfileVersion) {
        setError(requestError instanceof Error ? requestError.message : "The memory could not be saved.");
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
    clearHud();
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
    clearHud();
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
    clearHud();
  }

  function handleProfileChange(event: ChangeEvent<HTMLSelectElement>) {
    const nextUserId = Number(event.target.value);
    if (!DEMO_PROFILES.some((profile) => profile.id === nextUserId)) {
      return;
    }
    profileVersionRef.current += 1;
    proactiveRequestRef.current += 1;
    dismissedCueKeysRef.current.clear();
    setActiveUserId(nextUserId);
    setQuestion("");
    setResult(null);
    setIsLoading(false);
    setIsAnalyzingVision(false);
    setIsSavingMemory(false);
    setIsRecognizingFace(false);
    setProactiveCue(null);
    handleCameraRetake();
  }

  return (
    <main className="wearer-shell wearer-experience page-shell">
      <SiteNav tone="dark" />
      <section className="app-card wearer-card" aria-labelledby="page-title">
        <header className="app-header">
          <div>
            <p className="eyebrow">Wearer app</p>
            <h1 id="page-title">MemoryCue</h1>
            <p className="subtitle">A browser prototype for saved everyday context.</p>
          </div>
          <div className="header-actions">
            <label className="profile-selector">
              <span>Demo profile</span>
              <select value={activeUserId} onChange={handleProfileChange}>
                {DEMO_PROFILES.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.name}
                  </option>
                ))}
              </select>
              <small>Simulated profile — not a secure account</small>
            </label>
          </div>
        </header>

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
          proactiveCue={proactiveCue}
          proactiveCuesEnabled={proactiveCuesEnabled}
          onProactiveCueVisibilityChange={handleProactiveCueVisibilityChange}
          onProactiveCuesChange={(enabled) => {
            setProactiveCuesEnabled(enabled);
            if (!enabled) {
              proactiveRequestRef.current += 1;
              clearProactiveCue();
            }
          }}
          onHudQuery={askHudQuestion}
          onDismissHud={dismissHud}
          onImagePreviewError={reportImagePreviewError}
        />

        <section className="question-panel" aria-labelledby="question-heading">
          <p className="section-kicker">Need a cue?</p>
          <h2 id="question-heading">Ask MemoryCue</h2>
          <form className="question-form" onSubmit={handleSubmit}>
            <label className="sr-only" htmlFor="question">
              Ask a supported memory question
            </label>
            <input
              id="question"
              type="text"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Where are my keys?"
              autoComplete="off"
            />
            <button className="primary-button" type="submit" disabled={isLoading || !question.trim()}>
              {isLoading ? "Asking..." : "Ask"}
            </button>
          </form>

          <div className="suggestions" aria-label="Supported example questions">
            <p>Supported examples</p>
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

        <details
          className="memory-panel memory-review"
          open={Boolean(memoryImage || visionAnalysis || saveMessage)}
          aria-labelledby="memory-heading"
        >
          <summary className="memory-review-summary">
            <span>Add a memory</span>
            <small>Review before saving</small>
          </summary>
          <div className="memory-panel-heading">
            <div>
              <p className="section-kicker">Review memory</p>
              <h2 id="memory-heading">Review before saving</h2>
            </div>
            <p className="memory-helper">
              If an external vision provider is configured, AI can suggest details. Review or edit every field before
              saving, or complete the form manually.
            </p>
          </div>

          <div className="memory-form">
            <label className="file-picker">
              <span>Upload an image</span>
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
        </details>

        {error && <p className="error-message" role="alert">{error}</p>}

        <section className="answer-panel" aria-live="polite" aria-labelledby="answer-heading">
          <div className="answer-heading-row">
            <div>
              <p className="section-kicker">Answer</p>
              <h2 id="answer-heading">From saved information</h2>
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
            <p className="empty-answer">Choose a supported question to retrieve saved information.</p>
          )}
        </section>
      </section>
    </main>
  );
}
