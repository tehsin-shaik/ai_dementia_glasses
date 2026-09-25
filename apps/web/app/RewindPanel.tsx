"use client";

import { useCallback, useEffect, useState } from "react";

import { memoryCueFetch } from "./api";
import {
  fetchRecentStrip,
  fetchRewind,
  REWIND_WINDOW_MINUTES,
  type Rewind,
  type RewindMoment,
} from "./rewind";
import type { VoiceLanguage } from "./voice";

type RewindPanelProps = {
  apiUrl: string;
  userId: number;
  language: VoiceLanguage;
  refreshToken: number;
};

const COPY = {
  en: {
    kicker: "Saved moments",
    heading: "Recent saved moments",
    empty: "No saved moments yet for this profile.",
    rewind: "Rewind recent moments",
    rewinding: "Building recap...",
    earlier: "Show earlier saved moments",
    recapHeading: "Recap",
    earlierBadge: "Earlier saved moments, not the last 10 minutes",
    evidence: "Evidence",
    capture: "Live capture",
    sample: "Sample record",
    noPhoto: "No photo saved",
    corrected: "Caregiver corrected",
    failed: "Saved moments could not be loaded.",
    times: `Times are shown exactly as recorded. Rewind covers the last ${REWIND_WINDOW_MINUTES} minutes.`,
  },
  ar: {
    kicker: "اللحظات المحفوظة",
    heading: "أحدث اللحظات المحفوظة",
    empty: "لا توجد لحظات محفوظة لهذا الملف بعد.",
    rewind: "استرجاع اللحظات الأخيرة",
    rewinding: "جارٍ إعداد الملخّص...",
    earlier: "عرض لحظات محفوظة أقدم",
    recapHeading: "الملخّص",
    earlierBadge: "لحظات محفوظة أقدم، وليست آخر ١٠ دقائق",
    evidence: "الدليل",
    capture: "تصوير مباشر",
    sample: "سجل تجريبي",
    noPhoto: "لا توجد صورة محفوظة",
    corrected: "صحّحه مقدّم الرعاية",
    failed: "تعذّر تحميل اللحظات المحفوظة.",
    times: `تُعرض الأوقات كما سُجّلت. يغطي الاسترجاع آخر ${REWIND_WINDOW_MINUTES} دقيقة.`,
  },
} as const;

function formatMomentTime(recordedAt: string, language: VoiceLanguage): string {
  const parsed = new Date(recordedAt);
  if (Number.isNaN(parsed.getTime())) {
    return recordedAt;
  }
  return parsed.toLocaleString(language === "ar" ? "ar-AE" : "en-US", {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function MomentPhoto({
  apiUrl,
  userId,
  moment,
  fallback,
}: {
  apiUrl: string;
  userId: number;
  moment: RewindMoment;
  fallback: string;
}) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);

  useEffect(() => {
    if (moment.image_url === null) {
      return;
    }
    let active = true;
    let created: string | null = null;
    const controller = new AbortController();
    memoryCueFetch(`${apiUrl}${moment.image_url}`, userId, { signal: controller.signal })
      .then((response) => (response.ok ? response.blob() : null))
      .then((blob) => {
        if (!active || blob === null) {
          return;
        }
        created = URL.createObjectURL(blob);
        setObjectUrl(created);
      })
      .catch(() => undefined);
    return () => {
      active = false;
      controller.abort();
      if (created) {
        URL.revokeObjectURL(created);
      }
    };
  }, [apiUrl, moment.image_url, userId]);

  if (objectUrl === null) {
    return <div className="rewind-photo is-empty">{fallback}</div>;
  }
  return <img className="rewind-photo" src={objectUrl} alt={moment.description} />;
}

function MomentCard({
  apiUrl,
  userId,
  moment,
  language,
}: {
  apiUrl: string;
  userId: number;
  moment: RewindMoment;
  language: VoiceLanguage;
}) {
  const copy = COPY[language];
  return (
    <li className="rewind-card">
      <MomentPhoto apiUrl={apiUrl} userId={userId} moment={moment} fallback={copy.noPhoto} />
      <p className="rewind-card-description">{moment.description}</p>
      <span className="rewind-card-time">{formatMomentTime(moment.recorded_at, language)}</span>
      <span className="rewind-card-source">
        {moment.source === "capture" ? copy.capture : copy.sample}
      </span>
      {moment.corrected_at !== null && (
        <span className="rewind-card-corrected">
          {copy.corrected} · {moment.corrected_by} · {formatMomentTime(moment.corrected_at, language)}
        </span>
      )}
    </li>
  );
}

export default function RewindPanel({ apiUrl, userId, language, refreshToken }: RewindPanelProps) {
  const copy = COPY[language];
  const [strip, setStrip] = useState<RewindMoment[]>([]);
  const [recap, setRecap] = useState<Rewind | null>(null);
  const [isRewinding, setIsRewinding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setRecap(null);
    setError(null);
    fetchRecentStrip(apiUrl, userId, language, controller.signal)
      .then((result) => setStrip(result.moments))
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") {
          return;
        }
        setStrip([]);
        setError(copy.failed);
      });
    return () => controller.abort();
  }, [apiUrl, copy.failed, language, refreshToken, userId]);

  const loadRecap = useCallback(
    async (includeEarlier: boolean) => {
      setIsRewinding(true);
      setError(null);
      try {
        setRecap(await fetchRewind(apiUrl, userId, { includeEarlier, language }));
      } catch {
        setRecap(null);
        setError(copy.failed);
      } finally {
        setIsRewinding(false);
      }
    },
    [apiUrl, copy.failed, language, userId],
  );

  return (
    <section
      className="rewind-panel"
      aria-label="MemoryCue saved moments"
      dir={language === "ar" ? "rtl" : "ltr"}
    >
      <div className="rewind-heading">
        <div>
          <p className="section-kicker">{copy.kicker}</p>
          <h3>{copy.heading}</h3>
        </div>
        <button
          className="primary-button"
          type="button"
          onClick={() => loadRecap(false)}
          disabled={isRewinding}
        >
          {isRewinding ? copy.rewinding : copy.rewind}
        </button>
      </div>
      {strip.length === 0 ? (
        <p className="rewind-empty" data-testid="rewind-strip-empty">
          {copy.empty}
        </p>
      ) : (
        <ul className="rewind-strip" data-testid="rewind-strip">
          {strip.map((moment) => (
            <MomentCard
              key={moment.memory_id}
              apiUrl={apiUrl}
              userId={userId}
              moment={moment}
              language={language}
            />
          ))}
        </ul>
      )}
      {recap && (
        <div className="rewind-recap" data-testid="rewind-recap">
          <span className="rewind-recap-heading">{copy.recapHeading}</span>
          {!recap.within_window && recap.moments.length > 0 && (
            <span className="rewind-recap-badge">{copy.earlierBadge}</span>
          )}
          <p className="rewind-recap-summary">{recap.summary}</p>
          {recap.moments.length > 0 && (
            <>
              <span className="rewind-recap-heading">{copy.evidence}</span>
              <ul className="rewind-strip">
                {recap.moments.map((moment) => (
                  <MomentCard
                    key={moment.memory_id}
                    apiUrl={apiUrl}
                    userId={userId}
                    moment={moment}
                    language={language}
                  />
                ))}
              </ul>
            </>
          )}
          {!recap.within_window && recap.has_earlier && recap.moments.length === 0 && (
            <button
              className="secondary-button"
              type="button"
              onClick={() => loadRecap(true)}
              disabled={isRewinding}
            >
              {copy.earlier}
            </button>
          )}
        </div>
      )}
      {error && <p className="rewind-error">{error}</p>}
      <p className="rewind-note">{copy.times}</p>
    </section>
  );
}
