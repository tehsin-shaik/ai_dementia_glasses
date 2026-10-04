"use client";

export type VoiceLanguage = "en" | "ar";

type SpeechRecognitionAlternative = {
  transcript: string;
};

type SpeechRecognitionResult = {
  readonly length: number;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
  isFinal: boolean;
};

type SpeechRecognitionResultList = {
  readonly length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
};

type SpeechRecognitionEventLike = {
  results: SpeechRecognitionResultList;
};

type SpeechRecognitionErrorEventLike = {
  error: string;
};

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onstart: (() => void) | null;
  onspeechend: (() => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

type SpeechCapableWindow = Window & {
  SpeechRecognition?: SpeechRecognitionConstructor;
  webkitSpeechRecognition?: SpeechRecognitionConstructor;
};

export const RECOGNITION_LOCALES: Record<VoiceLanguage, string> = {
  en: "en-US",
  ar: "ar-AE",
};

function recognitionConstructor(): SpeechRecognitionConstructor | null {
  if (typeof window === "undefined") {
    return null;
  }
  const speechWindow = window as SpeechCapableWindow;
  return speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition ?? null;
}

export function isVoiceInputSupported(): boolean {
  return recognitionConstructor() !== null;
}

export function isSpeechOutputSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

/** One dictation turn: requesting → listening → processing → transcript, or an error. */
export type VoicePhase = "idle" | "requesting" | "listening" | "processing" | "transcript" | "error";

export type SpeechInputPhase = "requesting" | "listening" | "processing";

export type SpeechInputError =
  | "permission-denied"
  | "no-microphone"
  | "unsupported"
  | "no-speech"
  | "timeout"
  | "network"
  | "failed";

export const SPEECH_INPUT_TIMEOUT_MS = 15_000;

export function isVoiceActive(phase: VoicePhase): boolean {
  return phase === "requesting" || phase === "listening" || phase === "processing";
}

function speechInputError(code: string): SpeechInputError {
  if (code === "not-allowed" || code === "service-not-allowed") {
    return "permission-denied";
  }
  if (code === "audio-capture") {
    return "no-microphone";
  }
  if (code === "no-speech") {
    return "no-speech";
  }
  if (code === "network") {
    return "network";
  }
  if (code === "language-not-supported") {
    return "unsupported";
  }
  return "failed";
}

export function speechInputMessage(error: SpeechInputError): string {
  switch (error) {
    case "permission-denied":
      return "Microphone permission was denied. Allow microphone access in your browser, or type your question.";
    case "no-microphone":
      return "No microphone was found. Connect one, or type your question.";
    case "unsupported":
      return "Speech recognition is not available for this language in this browser. Type your question instead.";
    case "no-speech":
      return "I didn't hear a question. Try again or type it.";
    case "timeout":
      return "Listening stopped after 15 seconds without a question. Try again or type it.";
    case "network":
      return "Speech recognition in this browser needs a network connection. Type your question instead.";
    case "failed":
      return "The question could not be heard. Try again or type it.";
  }
}

type SpeechInputCallbacks = {
  onPhase: (phase: SpeechInputPhase) => void;
  onTranscript: (transcript: string) => void;
  onError: (error: SpeechInputError) => void;
  onEnd: () => void;
};

export type SpeechInputSession = {
  cancel: () => void;
};

/**
 * Start one user-triggered dictation turn. Exactly one of onTranscript or
 * onError fires unless the turn is cancelled; the microphone is released when
 * the turn ends or after the timeout. Returns null without Web Speech support.
 */
export function startSpeechInput(
  language: VoiceLanguage,
  callbacks: SpeechInputCallbacks,
  timeoutMs = SPEECH_INPUT_TIMEOUT_MS,
): SpeechInputSession | null {
  const Recognition = recognitionConstructor();
  if (Recognition === null) {
    return null;
  }

  const recognition = new Recognition();
  recognition.lang = RECOGNITION_LOCALES[language];
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  let settled = false;
  let timer: number | undefined;
  const settle = (): boolean => {
    if (settled) {
      return false;
    }
    settled = true;
    window.clearTimeout(timer);
    return true;
  };
  const fail = (error: SpeechInputError) => {
    if (settle()) {
      callbacks.onError(error);
    }
  };

  recognition.onstart = () => {
    if (!settled) {
      callbacks.onPhase("listening");
    }
  };
  recognition.onspeechend = () => {
    if (!settled) {
      callbacks.onPhase("processing");
    }
  };
  recognition.onresult = (event) => {
    const transcript = event.results[0]?.[0]?.transcript?.trim() ?? "";
    if (transcript && settle()) {
      callbacks.onTranscript(transcript);
    }
  };
  recognition.onerror = (event) => {
    fail(speechInputError(event.error));
  };
  recognition.onend = () => {
    fail("no-speech");
    callbacks.onEnd();
  };

  callbacks.onPhase("requesting");
  try {
    recognition.start();
  } catch {
    fail("failed");
    callbacks.onEnd();
    return { cancel: () => undefined };
  }
  timer = window.setTimeout(() => {
    fail("timeout");
    recognition.abort();
  }, timeoutMs);

  return {
    cancel: () => {
      if (settle()) {
        recognition.abort();
      }
    },
  };
}

export function speak(text: string, language: VoiceLanguage): void {
  if (!isSpeechOutputSupported()) {
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = RECOGNITION_LOCALES[language];
  utterance.rate = 0.95;
  window.speechSynthesis.speak(utterance);
}

export function stopSpeaking(): void {
  if (isSpeechOutputSupported()) {
    window.speechSynthesis.cancel();
  }
}
