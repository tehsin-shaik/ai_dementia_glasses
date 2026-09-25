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

export function voiceErrorMessage(error: string): string {
  if (error === "not-allowed" || error === "service-not-allowed") {
    return "Microphone permission was denied. Allow microphone access and try again.";
  }
  if (error === "no-speech") {
    return "I didn't hear a question. Try speaking again.";
  }
  if (error === "audio-capture") {
    return "No microphone was found. Connect one and try again.";
  }
  if (error === "network") {
    return "Speech recognition needs a network connection.";
  }
  return "The question could not be heard. Try again or type it.";
}

type ListenCallbacks = {
  onTranscript: (transcript: string) => void;
  onError: (message: string) => void;
  onEnd: () => void;
};

/**
 * Start one dictation turn and return a stop function, or null when the
 * browser has no Web Speech recognition support.
 */
export function startListening(
  language: VoiceLanguage,
  callbacks: ListenCallbacks,
): (() => void) | null {
  const Recognition = recognitionConstructor();
  if (Recognition === null) {
    return null;
  }

  const recognition = new Recognition();
  recognition.lang = RECOGNITION_LOCALES[language];
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  recognition.onresult = (event) => {
    const transcript = event.results[0]?.[0]?.transcript?.trim();
    if (transcript) {
      callbacks.onTranscript(transcript);
    }
  };
  recognition.onerror = (event) => {
    callbacks.onError(voiceErrorMessage(event.error));
  };
  recognition.onend = () => {
    callbacks.onEnd();
  };

  recognition.start();
  return () => recognition.abort();
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
