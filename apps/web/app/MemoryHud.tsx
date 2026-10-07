"use client";

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

export function formatRecordedAt(recordedAt: string | null, language: VoiceLanguage): string | null {
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
      lang={language}
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
