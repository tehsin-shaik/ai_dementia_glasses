"use client";

import { FormEvent, useState } from "react";

import type { VoiceLanguage } from "./voice";

export type MemoryHudState = "idle" | "querying" | "result" | "unknown" | "error";

export type QueryEvidence = {
  source_id: string;
  label: string;
  detail: string;
  recorded_at: string | null;
  image_url: string | null;
  corrected_at: string | null;
  corrected_by: string | null;
};

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
  evidence: QueryEvidence[];
  language: VoiceLanguage;
  proactiveCue: ProactiveCue | null;
  onDismiss: () => void;
};

type MemoryHudControlsProps = {
  isCameraActive: boolean;
  state: MemoryHudState;
  onQuery: (question: string) => void;
  proactiveCuesEnabled: boolean;
  onProactiveCuesChange: (enabled: boolean) => void;
  language: VoiceLanguage;
  onLanguageChange: (language: VoiceLanguage) => void;
  isListening: boolean;
  onListeningChange: (listening: boolean) => void;
  voiceInputSupported: boolean;
  speakAnswers: boolean;
  onSpeakAnswersChange: (enabled: boolean) => void;
  speechOutputSupported: boolean;
};

const QUICK_ACTIONS: Record<VoiceLanguage, string[]> = {
  en: ["What was I doing?", "Where are my keys?", "What am I doing today?"],
  ar: ["ماذا كنت أفعل؟", "أين مفاتيحي؟", "ما هو جدولي اليوم؟"],
};

const COPY = {
  en: {
    kicker: "Camera cues",
    heading: "Ask for a cue",
    questions: "Questions",
    optionalCues: "Optional cues",
    askLabel: "Ask MemoryCue",
    placeholder: "Where are my keys?",
    ask: "Ask",
    checking: "Checking...",
    quickCues: "Quick cues",
    speak: "Speak",
    listening: "Listening...",
    speakAnswers: "Speak answers",
    active: "Questions run only when you choose Ask or Speak. Optional cues use saved context and can be turned off.",
    inactive: "Start the camera to use cues in the preview.",
    noVoice: "This browser does not support voice input. Type your question instead.",
  },
  ar: {
    kicker: "تلميحات الكاميرا",
    heading: "اطلب تلميحًا",
    questions: "الأسئلة",
    optionalCues: "تلميحات اختيارية",
    askLabel: "اسأل MemoryCue",
    placeholder: "أين مفاتيحي؟",
    ask: "اسأل",
    checking: "جارٍ البحث...",
    quickCues: "أسئلة سريعة",
    speak: "تحدّث",
    listening: "أستمع...",
    speakAnswers: "نطق الإجابات",
    active: "تُطرح الأسئلة فقط عند اختيار اسأل أو تحدّث. التلميحات الاختيارية تعتمد على معلومات محفوظة ويمكن إيقافها.",
    inactive: "شغّل الكاميرا لاستخدام التلميحات في المعاينة.",
    noVoice: "هذا المتصفح لا يدعم الإدخال الصوتي. اكتب سؤالك بدلاً من ذلك.",
  },
} as const;

const OVERLAY_COPY = {
  en: {
    checking: "Checking memory",
    lookingUp: "Looking that up...",
    optional: "MemoryCue · Optional cue",
    unavailable: "MemoryCue unavailable",
    title: "MemoryCue",
    dismiss: "Dismiss",
    fallback: "I couldn't find matching saved information.",
    sources: "Answered from saved records",
    photo: "Saved photo on file",
    corrected: "Caregiver corrected",
    noSources: "No saved record matches this. MemoryCue does not guess about your life.",
  },
  ar: {
    checking: "أتحقق من الذاكرة",
    lookingUp: "أبحث عن ذلك...",
    optional: "MemoryCue · تلميح اختياري",
    unavailable: "MemoryCue غير متاح",
    title: "MemoryCue",
    dismiss: "إغلاق",
    fallback: "لا أملك معلومات محفوظة عن ذلك.",
    sources: "الإجابة مأخوذة من سجلات محفوظة",
    photo: "توجد صورة محفوظة",
    corrected: "صحّحه مقدّم الرعاية",
    noSources: "لا يوجد سجل محفوظ يطابق ذلك. MemoryCue لا يخمّن عن حياتك.",
  },
} as const;

function formatRecordedAt(recordedAt: string | null, language: VoiceLanguage): string | null {
  if (recordedAt === null) {
    return null;
  }
  const parsed = new Date(recordedAt);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed.toLocaleString(language === "ar" ? "ar-AE" : "en-US", {
    hour: "numeric",
    minute: "2-digit",
    month: "short",
    day: "numeric",
  });
}

export function MemoryHudOverlay({
  state,
  answer,
  error,
  evidence,
  language,
  proactiveCue,
  onDismiss,
}: MemoryHudOverlayProps) {
  if (state === "idle" && !proactiveCue) {
    return null;
  }

  const copy = OVERLAY_COPY[language];
  const isProactive = state === "idle" && proactiveCue !== null;
  const isError = state === "error" && !isProactive;
  const isUnknown = state === "unknown" && !isProactive;
  const heading = state === "querying"
    ? copy.checking
    : isProactive
      ? copy.optional
      : isError
        ? copy.unavailable
        : copy.title;
  const message = state === "querying" ? copy.lookingUp : isProactive ? proactiveCue.message : isError ? error : answer;
  const showEvidence = state === "result" && !isProactive && evidence.length > 0;

  return (
    <aside
      className={`hud-overlay hud-overlay-${state}`}
      aria-live="polite"
      aria-label="MemoryCue camera cue"
      dir={language === "ar" ? "rtl" : "ltr"}
    >
      <div className="hud-overlay-heading">
        <span className="hud-overlay-label">{heading}</span>
        <button className="hud-dismiss-button" type="button" onClick={onDismiss}>
          {copy.dismiss}
        </button>
      </div>
      {isProactive && <strong className="hud-overlay-cue-title">{proactiveCue.title}</strong>}
      <p className={`hud-overlay-message ${isUnknown ? "is-unknown" : ""}`}>
        {message ?? copy.fallback}
      </p>
      {showEvidence && (
        <div className="hud-provenance" data-testid="hud-provenance">
          <span className="hud-provenance-heading">{copy.sources}</span>
          <ul>
            {evidence.map((item) => {
              const recordedAt = formatRecordedAt(item.recorded_at, language);
              return (
                <li key={item.source_id}>
                  <span className="hud-provenance-label">{item.label}</span>
                  <span className="hud-provenance-detail">{item.detail}</span>
                  {recordedAt && <span className="hud-provenance-time">{recordedAt}</span>}
                  {item.image_url && (
                    <span className="hud-provenance-photo">{copy.photo}</span>
                  )}
                  {item.corrected_at && (
                    <span className="hud-provenance-corrected">
                      {copy.corrected} · {item.corrected_by} ·{" "}
                      {formatRecordedAt(item.corrected_at, language)}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {isUnknown && (
        <p className="hud-provenance-empty" data-testid="hud-no-sources">
          {copy.noSources}
        </p>
      )}
    </aside>
  );
}

export function MemoryHudControls({
  isCameraActive,
  state,
  onQuery,
  proactiveCuesEnabled,
  onProactiveCuesChange,
  language,
  onLanguageChange,
  isListening,
  onListeningChange,
  voiceInputSupported,
  speakAnswers,
  onSpeakAnswersChange,
  speechOutputSupported,
}: MemoryHudControlsProps) {
  const [question, setQuestion] = useState("");
  const copy = COPY[language];
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
    <div
      className="hud-controls"
      aria-label="MemoryCue camera cue controls"
      dir={language === "ar" ? "rtl" : "ltr"}
    >
      <div className="hud-controls-heading">
        <div>
          <p className="section-kicker">{copy.kicker}</p>
          <h3>{copy.heading}</h3>
        </div>
        <div className="hud-control-mode-row">
          <span className="hud-mode-label">{copy.questions}</span>
          <label className="hud-proactive-toggle">
            <span>{copy.optionalCues}</span>
            <input
              type="checkbox"
              checked={proactiveCuesEnabled}
              onChange={(event) => onProactiveCuesChange(event.target.checked)}
            />
            <span aria-hidden="true">{proactiveCuesEnabled ? "On" : "Off"}</span>
          </label>
        </div>
      </div>
      <div className="hud-language-row" role="group" aria-label="Answer language">
        <button
          className={`hud-language-button ${language === "en" ? "is-selected" : ""}`}
          type="button"
          aria-pressed={language === "en"}
          onClick={() => onLanguageChange("en")}
        >
          English
        </button>
        <button
          className={`hud-language-button ${language === "ar" ? "is-selected" : ""}`}
          type="button"
          aria-pressed={language === "ar"}
          onClick={() => onLanguageChange("ar")}
        >
          العربية
        </button>
      </div>
      <form className="hud-query-form" onSubmit={submitQuestion}>
        <label htmlFor="hud-question">{copy.askLabel}</label>
        <div className="hud-query-input-row">
          <input
            id="hud-question"
            type="text"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder={copy.placeholder}
            disabled={isDisabled}
          />
          {voiceInputSupported && (
            <button
              className={`hud-voice-button ${isListening ? "is-listening" : ""}`}
              type="button"
              aria-pressed={isListening}
              onClick={() => onListeningChange(!isListening)}
              disabled={!isCameraActive}
            >
              {isListening ? copy.listening : copy.speak}
            </button>
          )}
          <button className="primary-button" type="submit" disabled={isDisabled || !question.trim()}>
            {isQuerying ? copy.checking : copy.ask}
          </button>
        </div>
      </form>
      {speechOutputSupported && (
        <label className="hud-speak-toggle">
          <input
            type="checkbox"
            checked={speakAnswers}
            onChange={(event) => onSpeakAnswersChange(event.target.checked)}
          />
          <span>{copy.speakAnswers}</span>
        </label>
      )}
      <div className="hud-quick-actions">
        <span>{copy.quickCues}</span>
        <div>
          {QUICK_ACTIONS[language].map((action) => (
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
        {isCameraActive ? copy.active : copy.inactive}
        {!voiceInputSupported && ` ${copy.noVoice}`}
      </p>
    </div>
  );
}
