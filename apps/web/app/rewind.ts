"use client";

import { memoryCueFetch } from "./api";
import type { VoiceLanguage } from "./voice";

export type RewindMoment = {
  memory_id: number;
  recorded_at: string;
  location: string;
  activity: string | null;
  description: string;
  image_url: string | null;
  source: "capture" | "sample";
};

export type Rewind = {
  summary: string;
  moments: RewindMoment[];
  window_minutes: number;
  within_window: boolean;
  has_earlier: boolean;
};

export const REWIND_WINDOW_MINUTES = 10;
const STRIP_WINDOW_MINUTES = 1440;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object";
}

function parseMoment(payload: unknown): RewindMoment[] {
  if (
    !isRecord(payload) ||
    typeof payload.memory_id !== "number" ||
    typeof payload.recorded_at !== "string" ||
    typeof payload.location !== "string" ||
    typeof payload.description !== "string" ||
    (payload.source !== "capture" && payload.source !== "sample")
  ) {
    return [];
  }
  return [
    {
      memory_id: payload.memory_id,
      recorded_at: payload.recorded_at,
      location: payload.location,
      activity: typeof payload.activity === "string" ? payload.activity : null,
      description: payload.description,
      image_url: typeof payload.image_url === "string" ? payload.image_url : null,
      source: payload.source,
    },
  ];
}

export function parseRewind(payload: unknown): Rewind {
  if (
    !isRecord(payload) ||
    typeof payload.summary !== "string" ||
    typeof payload.window_minutes !== "number" ||
    typeof payload.within_window !== "boolean" ||
    typeof payload.has_earlier !== "boolean"
  ) {
    throw new Error("The rewind request returned an invalid response.");
  }
  const moments = Array.isArray(payload.moments) ? payload.moments.flatMap(parseMoment) : [];
  return {
    summary: payload.summary,
    moments,
    window_minutes: payload.window_minutes,
    within_window: payload.within_window,
    has_earlier: payload.has_earlier,
  };
}

export async function fetchRewind(
  apiUrl: string,
  userId: number,
  options: {
    windowMinutes?: number;
    includeEarlier?: boolean;
    language?: VoiceLanguage;
    signal?: AbortSignal;
  } = {},
): Promise<Rewind> {
  const params = new URLSearchParams({
    window_minutes: String(options.windowMinutes ?? REWIND_WINDOW_MINUTES),
    include_earlier: String(options.includeEarlier ?? false),
    language: options.language ?? "en",
  });
  const response = await memoryCueFetch(`${apiUrl}/api/rewind?${params.toString()}`, userId, {
    signal: options.signal,
  });
  if (!response.ok) {
    throw new Error("Saved moments could not be loaded.");
  }
  return parseRewind(await response.json());
}

export function fetchRecentStrip(
  apiUrl: string,
  userId: number,
  language: VoiceLanguage,
  signal?: AbortSignal,
): Promise<Rewind> {
  return fetchRewind(apiUrl, userId, {
    windowMinutes: STRIP_WINDOW_MINUTES,
    includeEarlier: true,
    language,
    signal,
  });
}
