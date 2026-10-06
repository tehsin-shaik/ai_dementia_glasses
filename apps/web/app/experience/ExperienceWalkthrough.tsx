"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { memoryCueFetch } from "../api";
import {
  isSpeechOutputSupported,
  isVoiceInputSupported,
  speak,
  speechInputMessage,
  startSpeechInput,
  stopSpeaking,
  type SpeechInputSession,
  type VoiceLanguage,
} from "../voice";
import { createApartmentScene, type ApartmentScene } from "./apartmentScene";
import { EXPERIENCE_STEPS, type ExperienceStep } from "./steps";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ALEX_USER_ID = 1;

type Evidence = { label: string; detail: string; recordedAt: string | null };

type HudAnswer =
  | { status: "idle" }
  | { status: "asking"; question: string }
  | { status: "answer" | "unknown"; question: string; answer: string; evidence: Evidence[] }
  | { status: "error"; question: string; message: string };

const COPY = {
  en: {
    eyebrow: "First-person simulation",
    heading: "A morning through Alex's glasses",
    intro: "Walk through Alex's demo morning in 3D. The panel in the corner is what the glasses would show.",
    profile: "Alex · demo profile",
    sceneTime: "Scene time",
    captured: "Moment captured",
    saveQuestion: "Keep this moment?",
    save: "Save moment",
    saved: "Saved to memory",
    savedNote: "Only saved moments can be used in answers.",
    asking: "Checking saved moments…",
    ask: "Ask",
    unknownNote: "No saved record matches this. MemoryCue does not guess.",
    from: "From",
    error: "MemoryCue couldn't be reached. Start the API and try again.",
    back: "Back",
    next: "Next",
    restart: "Start again",
    saveFirst: "Save the moment to continue",
    speakAnswers: "Read answers aloud",
    voice: "Ask by voice",
    stopVoice: "Stop listening",
    listening: "Listening…",
    placeholder: "Type a question",
    noWebgl: "3D view isn't available in this browser. The glasses panel still works.",
    disclaimer: "Simulation of a future glasses display. Moments shown are Alex's seeded demo records; Save here does not write new data.",
    tryApp: "Open the full app",
    stepOf: (current: number, total: number) => `Step ${current} of ${total}`,
    lastRecorded: (time: string) => `Last recorded · ${time}`,
  },
  ar: {
    eyebrow: "محاكاة من منظور الشخص",
    heading: "صباح من خلال نظارة أليكس",
    intro: "تجوّل في صباح أليكس التجريبي ثلاثي الأبعاد. اللوحة في الزاوية هي ما ستعرضه النظارة.",
    profile: "أليكس · ملف تجريبي",
    sceneTime: "وقت المشهد",
    captured: "تم التقاط لحظة",
    saveQuestion: "هل تريد حفظ هذه اللحظة؟",
    save: "حفظ اللحظة",
    saved: "حُفظت في الذاكرة",
    savedNote: "تُستخدم اللحظات المحفوظة فقط في الإجابات.",
    asking: "جارٍ البحث في اللحظات المحفوظة…",
    ask: "اسأل",
    unknownNote: "لا يوجد سجل محفوظ يطابق ذلك. MemoryCue لا يخمّن.",
    from: "من",
    error: "تعذّر الوصول إلى MemoryCue. شغّل الواجهة الخلفية وحاول مجددًا.",
    back: "السابق",
    next: "التالي",
    restart: "ابدأ من جديد",
    saveFirst: "احفظ اللحظة للمتابعة",
    speakAnswers: "قراءة الإجابات بصوت عالٍ",
    voice: "اسأل بالصوت",
    stopVoice: "إيقاف الاستماع",
    listening: "جارٍ الاستماع…",
    placeholder: "اكتب سؤالًا",
    noWebgl: "العرض ثلاثي الأبعاد غير متاح في هذا المتصفح. لوحة النظارة ما زالت تعمل.",
    disclaimer: "محاكاة لشاشة نظارة مستقبلية. اللحظات المعروضة هي سجلات أليكس التجريبية؛ الحفظ هنا لا يكتب بيانات جديدة.",
    tryApp: "افتح التطبيق الكامل",
    stepOf: (current: number, total: number) => `الخطوة ${current} من ${total}`,
    lastRecorded: (time: string) => `آخر تسجيل · ${time}`,
  },
} as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseEvidence(value: unknown): Evidence[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter(isRecord).map((item) => ({
    label: typeof item.label === "string" ? item.label : "",
    detail: typeof item.detail === "string" ? item.detail : "",
    recordedAt: typeof item.recorded_at === "string" ? item.recorded_at : null,
  }));
}

function formatTime(value: string, language: VoiceLanguage): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString(language === "ar" ? "ar" : "en-US", { hour: "numeric", minute: "2-digit" });
}

export default function ExperienceWalkthrough() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const sceneRef = useRef<ApartmentScene | null>(null);
  const requestRef = useRef(0);
  const voiceRef = useRef<SpeechInputSession | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [language, setLanguage] = useState<VoiceLanguage>("en");
  const [savedSteps, setSavedSteps] = useState<Set<string>>(() => new Set());
  const [hud, setHud] = useState<HudAnswer>({ status: "idle" });
  const [sceneUnavailable, setSceneUnavailable] = useState(false);
  const [keysRevealed, setKeysRevealed] = useState(false);
  const [speakAnswers, setSpeakAnswers] = useState(false);
  const [speechOutput, setSpeechOutput] = useState(false);
  const [voiceInput, setVoiceInput] = useState(false);
  const [listening, setListening] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const step: ExperienceStep = EXPERIENCE_STEPS[stepIndex];
  const copy = COPY[language];
  const isLastStep = stepIndex === EXPERIENCE_STEPS.length - 1;
  const needsSave = step.kind === "moment" && !savedSteps.has(step.id);

  useEffect(() => {
    setSpeechOutput(isSpeechOutputSupported());
    setVoiceInput(isVoiceInputSupported());
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }
    try {
      sceneRef.current = createApartmentScene(canvas, EXPERIENCE_STEPS[0].view);
    } catch {
      setSceneUnavailable(true);
    }
    return () => {
      sceneRef.current?.dispose();
      sceneRef.current = null;
    };
  }, []);

  const cancelVoice = useCallback(() => {
    voiceRef.current?.cancel();
    voiceRef.current = null;
    setListening(false);
  }, []);

  useEffect(() => {
    requestRef.current += 1;
    cancelVoice();
    stopSpeaking();
    setHud({ status: "idle" });
    setVoiceError(null);
    setDraft("");
    sceneRef.current?.showKeysMarker(null);
    setKeysRevealed(false);
    sceneRef.current?.moveTo(EXPERIENCE_STEPS[stepIndex].view);
  }, [stepIndex, language, cancelVoice]);

  useEffect(() => () => {
    voiceRef.current?.cancel();
    stopSpeaking();
  }, []);

  async function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed) {
      return;
    }
    const requestId = requestRef.current + 1;
    requestRef.current = requestId;
    const askedStep = step;
    setHud({ status: "asking", question: trimmed });
    try {
      const response = await memoryCueFetch(`${API_URL}/api/query`, ALEX_USER_ID, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: trimmed, language }),
      });
      if (!response.ok) {
        throw new Error(`Query failed with ${response.status}`);
      }
      const payload: unknown = await response.json();
      if (!isRecord(payload) || typeof payload.answer !== "string" || typeof payload.intent !== "string") {
        throw new Error("Invalid query response");
      }
      if (requestRef.current !== requestId) {
        return;
      }
      const evidence = parseEvidence(payload.evidence);
      const unknown = payload.intent === "unknown";
      setHud({ status: unknown ? "unknown" : "answer", question: trimmed, answer: payload.answer, evidence });
      if (speakAnswers) {
        speak(payload.answer, language);
      }
      const recordedAt = evidence[0]?.recordedAt;
      const answerText = `${payload.answer} ${evidence[0]?.detail ?? ""}`.toLowerCase();
      if (
        !unknown &&
        askedStep.kind === "question" &&
        askedStep.revealView &&
        recordedAt &&
        askedStep.revealPlaces?.some((place) => answerText.includes(place))
      ) {
        sceneRef.current?.moveTo(askedStep.revealView);
        sceneRef.current?.showKeysMarker(copy.lastRecorded(formatTime(recordedAt, language)));
        setKeysRevealed(true);
      }
    } catch {
      if (requestRef.current === requestId) {
        setHud({ status: "error", question: trimmed, message: copy.error });
      }
    }
  }

  function startVoice() {
    cancelVoice();
    setVoiceError(null);
    const session = startSpeechInput(language, {
      onPhase: (phase) => setListening(phase === "listening" || phase === "requesting"),
      onTranscript: (transcript) => {
        voiceRef.current = null;
        setListening(false);
        setDraft(transcript);
        void ask(transcript);
      },
      onError: (error) => {
        voiceRef.current = null;
        setListening(false);
        setVoiceError(speechInputMessage(error));
      },
      onEnd: () => setListening(false),
    });
    voiceRef.current = session;
  }

  function submitDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void ask(draft);
  }

  function goTo(index: number) {
    setStepIndex(Math.max(0, Math.min(EXPERIENCE_STEPS.length - 1, index)));
  }

  function next() {
    if (isLastStep) {
      setSavedSteps(new Set());
      goTo(0);
      return;
    }
    if (!needsSave) {
      goTo(stepIndex + 1);
    }
  }

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.target instanceof HTMLInputElement) {
        return;
      }
      if (event.key === "ArrowRight") {
        document.querySelector<HTMLButtonElement>("[data-experience-next]")?.click();
      } else if (event.key === "ArrowLeft") {
        document.querySelector<HTMLButtonElement>("[data-experience-back]")?.click();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function renderHudBody() {
    if (step.kind === "moment") {
      if (savedSteps.has(step.id)) {
        return (
          <div className="exp-hud-saved">
            <span className="exp-hud-chip exp-hud-chip-ok">✓ {copy.saved}</span>
            <strong>{step.capture[language]}</strong>
            <small>{step.location[language]} · {step.sceneTime}</small>
            <p>{copy.savedNote}</p>
          </div>
        );
      }
      return (
        <div className="exp-hud-capture">
          <span className="exp-hud-chip">● {copy.captured}</span>
          <strong>{step.capture[language]}</strong>
          <small>{step.location[language]} · {step.sceneTime}</small>
          <p>{copy.saveQuestion}</p>
          <button
            type="button"
            className="exp-hud-button"
            onClick={() => setSavedSteps((current) => new Set(current).add(step.id))}
          >
            {copy.save}
          </button>
        </div>
      );
    }

    if (hud.status === "idle") {
      if (step.kind === "question") {
        return (
          <div className="exp-hud-ask">
            <p className="exp-hud-question">“{step.question[language]}”</p>
            <button type="button" className="exp-hud-button" onClick={() => void ask(step.question[language])}>
              {copy.ask}
            </button>
          </div>
        );
      }
      return <p className="exp-hud-muted">{copy.placeholder}…</p>;
    }
    if (hud.status === "asking") {
      return (
        <div className="exp-hud-ask">
          <p className="exp-hud-question">“{hud.question}”</p>
          <p className="exp-hud-muted">{copy.asking}</p>
        </div>
      );
    }
    if (hud.status === "error") {
      return (
        <div className="exp-hud-ask">
          <p className="exp-hud-question">“{hud.question}”</p>
          <p className="exp-hud-error" role="alert">{hud.message}</p>
        </div>
      );
    }
    return (
      <div className={`exp-hud-answer ${hud.status === "unknown" ? "is-unknown" : ""}`}>
        <p className="exp-hud-question">“{hud.question}”</p>
        <strong data-testid="experience-answer">{hud.answer}</strong>
        {hud.status === "unknown" ? (
          <small>{copy.unknownNote}</small>
        ) : (
          <ul className="exp-hud-evidence" aria-label="Sources">
            {hud.evidence.map((item, index) => (
              <li key={`${item.label}-${index}`}>
                {copy.from}: {item.label}
                {item.recordedAt ? ` · ${formatTime(item.recordedAt, language)}` : ""}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  const dir = language === "ar" ? "rtl" : "ltr";

  return (
    <section className="exp-shell" aria-labelledby="experience-heading" dir={dir} lang={language}>
      <header className="exp-header">
        <div>
          <span className="exp-eyebrow">{copy.eyebrow}</span>
          <h1 id="experience-heading">{copy.heading}</h1>
          <p>{copy.intro}</p>
        </div>
        <div className="exp-header-controls">
          <div className="exp-toggle" role="group" aria-label="Language">
            <button type="button" aria-pressed={language === "en"} onClick={() => setLanguage("en")}>English</button>
            <button type="button" aria-pressed={language === "ar"} onClick={() => setLanguage("ar")}>العربية</button>
          </div>
          {speechOutput && (
            <label className="exp-check">
              <input type="checkbox" checked={speakAnswers} onChange={(event) => setSpeakAnswers(event.target.checked)} />
              {copy.speakAnswers}
            </label>
          )}
        </div>
      </header>

      <div className="exp-stage">
        <canvas
          ref={canvasRef}
          className="exp-canvas"
          aria-hidden="true"
          data-keys-revealed={keysRevealed ? "true" : "false"}
        />
        {sceneUnavailable && <p className="exp-fallback" role="note">{copy.noWebgl}</p>}
        <div className="exp-lens" aria-hidden="true" />
        <aside className="exp-hud" role="status" aria-live="polite" aria-label="Glasses display" dir={dir}>
          <div className="exp-hud-top">
            <span>MemoryCue</span>
            <span>{copy.sceneTime} {step.sceneTime}</span>
          </div>
          {renderHudBody()}
        </aside>
        <span className="exp-profile">{copy.profile}</span>
      </div>

      <div className="exp-narration">
        <div className="exp-narration-text">
          <span className="exp-step-count">{copy.stepOf(stepIndex + 1, EXPERIENCE_STEPS.length)}</span>
          <h2>{step.title[language]}</h2>
          <p>{step.narration[language]}</p>
          {step.kind === "open" && (
            <div className="exp-open">
              <div className="exp-suggestions">
                {step.suggestions.map((suggestion) => (
                  <button
                    key={suggestion.en}
                    type="button"
                    className="exp-suggestion"
                    onClick={() => {
                      setDraft(suggestion[language]);
                      void ask(suggestion[language]);
                    }}
                  >
                    {suggestion[language]}
                  </button>
                ))}
              </div>
              <form className="exp-form" onSubmit={submitDraft}>
                <input
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder={copy.placeholder}
                  aria-label={copy.placeholder}
                />
                <button type="submit" className="exp-primary" disabled={!draft.trim()}>{copy.ask}</button>
                {voiceInput && (
                  <button
                    type="button"
                    className="exp-secondary"
                    aria-pressed={listening}
                    onClick={() => (listening ? cancelVoice() : startVoice())}
                  >
                    {listening ? copy.stopVoice : copy.voice}
                  </button>
                )}
              </form>
              {listening && <p className="exp-hint">{copy.listening}</p>}
              {voiceError && <p className="exp-hint exp-hint-error" role="alert">{voiceError}</p>}
            </div>
          )}
        </div>
        <div className="exp-controls">
          <ol className="exp-dots" aria-label="Steps">
            {EXPERIENCE_STEPS.map((item, index) => (
              <li key={item.id} aria-current={index === stepIndex ? "step" : undefined}>
                <span className="exp-dot" />
              </li>
            ))}
          </ol>
          <div className="exp-buttons">
            <button type="button" className="exp-secondary" data-experience-back onClick={() => goTo(stepIndex - 1)} disabled={stepIndex === 0}>
              {copy.back}
            </button>
            <button type="button" className="exp-primary" data-experience-next onClick={next} disabled={needsSave}>
              {isLastStep ? copy.restart : copy.next}
            </button>
          </div>
          {needsSave && <p className="exp-hint">{copy.saveFirst}</p>}
        </div>
      </div>

      <footer className="exp-footer">
        <p>{copy.disclaimer}</p>
        <Link href="/app">{copy.tryApp} →</Link>
      </footer>
    </section>
  );
}
