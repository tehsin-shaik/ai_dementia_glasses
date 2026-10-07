import { expect, Page, Route, test } from "@playwright/test";

type SpeechScript =
  | { mode: "result"; transcript: string }
  | { mode: "empty" }
  | { mode: "error"; error: string }
  | { mode: "pending" }
  | { mode: "started" }
  | { mode: "listening" };

type SpeechLog = { languages: string[]; aborts: number };

type RecordedQuery = { question: string; language: string; userId: string | null };

/**
 * Replace the browser speech engine with a scripted one: the app code under
 * test is unchanged, only the recognition events are supplied by the test.
 */
async function installSpeech(page: Page, script: SpeechScript | null) {
  await page.addInitScript((initial) => {
    const state = window as Window & { __speech?: unknown; __speechLog?: SpeechLog };
    if (initial === null) {
      Object.defineProperty(window, "SpeechRecognition", { value: undefined, configurable: true });
      Object.defineProperty(window, "webkitSpeechRecognition", { value: undefined, configurable: true });
      return;
    }
    state.__speech = initial;
    state.__speechLog = { languages: [], aborts: 0 };
    Object.defineProperty(window, "speechSynthesis", {
      configurable: true,
      value: { cancel: () => undefined, speak: () => undefined },
    });
    class FakeRecognition {
      lang = "";
      continuous = false;
      interimResults = false;
      maxAlternatives = 1;
      onstart: (() => void) | null = null;
      onaudiostart: (() => void) | null = null;
      onspeechend: (() => void) | null = null;
      onresult: ((event: unknown) => void) | null = null;
      onerror: ((event: unknown) => void) | null = null;
      onend: (() => void) | null = null;
      start() {
        const script = state.__speech as SpeechScript;
        state.__speechLog?.languages.push(this.lang);
        const later = (fn: () => void) => setTimeout(fn, 30);
        if (script.mode === "result") {
          later(() => {
            this.onstart?.();
            this.onaudiostart?.();
            this.onspeechend?.();
            this.onresult?.({ results: [[{ transcript: script.transcript }]] });
            this.onend?.();
          });
        } else if (script.mode === "empty") {
          later(() => {
            this.onstart?.();
            this.onaudiostart?.();
            this.onspeechend?.();
            this.onresult?.({ results: [[{ transcript: "   " }]] });
            this.onend?.();
          });
        } else if (script.mode === "error") {
          later(() => {
            this.onerror?.({ error: script.error });
            this.onend?.();
          });
        } else if (script.mode === "started") {
          later(() => this.onstart?.());
        } else if (script.mode === "listening") {
          later(() => {
            this.onstart?.();
            this.onaudiostart?.();
          });
        }
      }
      stop() {
        this.onend?.();
      }
      abort() {
        if (state.__speechLog) {
          state.__speechLog.aborts += 1;
        }
        setTimeout(() => {
          this.onerror?.({ error: "aborted" });
          this.onend?.();
        }, 0);
      }
    }
    Object.defineProperty(window, "SpeechRecognition", { value: FakeRecognition, configurable: true });
  }, script);
}

async function setSpeech(page: Page, script: SpeechScript) {
  await page.evaluate((next) => {
    (window as Window & { __speech?: unknown }).__speech = next;
  }, script);
}

async function speechLog(page: Page): Promise<SpeechLog> {
  return page.evaluate(() => (window as Window & { __speechLog?: SpeechLog }).__speechLog ?? { languages: [], aborts: 0 });
}

async function fulfillJson(route: Route, payload: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: { "access-control-allow-origin": "*" },
    body: JSON.stringify(payload),
  });
}

/** Mock the API, recording every /api/query call and every other write. */
async function routeApi(page: Page, answerFor: (query: RecordedQuery) => { status?: number; body: unknown }) {
  const queries: RecordedQuery[] = [];
  const otherWrites: string[] = [];
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") {
      return route.fulfill({
        status: 204,
        headers: {
          "access-control-allow-origin": "*",
          "access-control-allow-headers": "*",
          "access-control-allow-methods": "GET,POST,PATCH,DELETE,OPTIONS",
        },
      });
    }
    const path = new URL(request.url()).pathname;
    if (request.method() === "POST" && path === "/api/query") {
      const payload = request.postDataJSON() as { question: string; language: string };
      const query = { ...payload, userId: await request.headerValue("x-memorycue-user-id") };
      queries.push(query);
      const { status, body } = answerFor(query);
      return fulfillJson(route, body, status);
    }
    if (request.method() !== "GET") {
      otherWrites.push(`${request.method()} ${path}`);
    }
    if (path === "/api/cues") {
      return fulfillJson(route, { cues: [] });
    }
    if (path === "/api/rewind") {
      return fulfillJson(route, { moments: [], recap: null });
    }
    return fulfillJson(route, { detail: "Not found" }, 404);
  });
  return { queries, otherWrites };
}

function answer(text: string, language = "en") {
  return {
    body: {
      answer: text,
      intent: "object_location",
      source_ids: ["memory:2"],
      evidence: [],
      language,
    },
  };
}

const keysAnswer = "Last recorded: your keys on the kitchen counter at 10:18 AM.";

function questionInput(page: Page) {
  return page.locator("#question");
}

function voiceButton(page: Page) {
  return page.getByRole("button", { name: "Ask by voice" });
}

function voiceStatus(page: Page) {
  return page.getByTestId("voice-question-status");
}

function answerText(page: Page) {
  return page.locator(".answer-panel .answer-text");
}

test("a spoken question fills the question box and goes through /api/query without the camera", async ({ page }) => {
  await installSpeech(page, { mode: "result", transcript: "Where are my keys?" });
  const api = await routeApi(page, () => answer(keysAnswer));

  await page.goto("/app");
  await expect(page.getByText("Camera active", { exact: true })).toHaveCount(0);
  await voiceButton(page).click();

  await expect(answerText(page)).toHaveText(keysAnswer);
  await expect(questionInput(page)).toHaveValue("Where are my keys?");
  await expect(voiceStatus(page)).toHaveText("Heard: “Where are my keys?”");
  expect(api.queries).toEqual([{ question: "Where are my keys?", language: "en", userId: "1" }]);
  expect(api.otherWrites).toEqual([]);
  expect((await speechLog(page)).languages).toEqual(["en-US"]);
});

test("typed and spoken questions send the identical request and show the same answer", async ({ page }) => {
  await installSpeech(page, { mode: "result", transcript: "Where are my keys?" });
  const api = await routeApi(page, () => answer(keysAnswer));

  await page.goto("/app");
  await questionInput(page).fill("Where are my keys?");
  await page.locator(".question-form").getByRole("button", { name: "Ask", exact: true }).click();
  await expect(answerText(page)).toHaveText(keysAnswer);

  await questionInput(page).fill("");
  await voiceButton(page).click();
  await expect(voiceStatus(page)).toHaveText("Heard: “Where are my keys?”");
  await expect.poll(() => api.queries.length).toBe(2);
  await expect(answerText(page)).toHaveText(keysAnswer);

  expect(api.queries[1]).toEqual(api.queries[0]);
});

test("the microphone states are shown and Stop listening cancels without asking", async ({ page }) => {
  await installSpeech(page, { mode: "pending" });
  const api = await routeApi(page, () => answer(keysAnswer));

  await page.goto("/app");
  await voiceButton(page).click();
  await expect(voiceStatus(page)).toHaveText("Waiting for microphone permission...");
  const stop = page.getByRole("button", { name: "Stop listening" });
  await expect(stop).toHaveAttribute("aria-pressed", "true");
  await stop.click();
  await expect(voiceStatus(page)).toHaveCount(0);
  await expect(voiceButton(page)).toBeVisible();

  await setSpeech(page, { mode: "started" });
  await voiceButton(page).click();
  await page.waitForTimeout(200);
  await expect(voiceStatus(page)).toHaveText("Waiting for microphone permission...");
  await page.getByRole("button", { name: "Stop listening" }).click();
  await expect(voiceStatus(page)).toHaveCount(0);

  await setSpeech(page, { mode: "listening" });
  await voiceButton(page).click();
  await expect(voiceStatus(page)).toHaveText("Microphone on. Ask one question.");
  await page.getByRole("button", { name: "Stop listening" }).click();
  await expect(voiceStatus(page)).toHaveCount(0);

  expect((await speechLog(page)).aborts).toBe(3);
  expect(api.queries).toEqual([]);
});

const errorCases = [
  { error: "not-allowed", message: "Microphone permission was denied. Allow microphone access in your browser, or type your question." },
  {
    error: "service-not-allowed",
    message: "Speech recognition is disabled or unavailable in this browser or device settings (for example, Siri/Dictation is off). Type your question instead.",
  },
  { error: "audio-capture", message: "No microphone was found. Connect one, or type your question." },
  { error: "no-speech", message: "I didn't hear a question. Try again or type it." },
  { error: "network", message: "Speech recognition in this browser needs a network connection. Type your question instead." },
  { error: "bad-grammar", message: "The question could not be heard. Try again or type it." },
];

for (const { error, message } of errorCases) {
  test(`a "${error}" recognition error is explained and typing still works`, async ({ page }) => {
    await installSpeech(page, { mode: "error", error });
    const api = await routeApi(page, () => answer(keysAnswer));

    await page.goto("/app");
    await voiceButton(page).click();
    await expect(voiceStatus(page)).toHaveText(message);
    await expect(voiceButton(page)).toBeEnabled();
    expect(api.queries).toEqual([]);

    await questionInput(page).fill("Where are my keys?");
    await page.locator(".question-form").getByRole("button", { name: "Ask", exact: true }).click();
    await expect(answerText(page)).toHaveText(keysAnswer);
    expect(api.queries).toHaveLength(1);
    expect(api.otherWrites).toEqual([]);
  });
}

test("an empty transcript does not submit a query", async ({ page }) => {
  await installSpeech(page, { mode: "empty" });
  const api = await routeApi(page, () => answer(keysAnswer));

  await page.goto("/app");
  await voiceButton(page).click();
  await expect(voiceStatus(page)).toHaveText("I didn't hear a question. Try again or type it.");
  await expect(questionInput(page)).toHaveValue("");
  expect(api.queries).toEqual([]);
});

test("listening stops after the timeout without asking", async ({ page }) => {
  await page.clock.install();
  await installSpeech(page, { mode: "listening" });
  const api = await routeApi(page, () => answer(keysAnswer));

  await page.goto("/app");
  await voiceButton(page).click();
  await page.clock.runFor(100);
  await expect(voiceStatus(page)).toHaveText("Microphone on. Ask one question.");
  await page.clock.runFor(15_000);
  await expect(voiceStatus(page)).toHaveText(
    "Listening stopped after 15 seconds without a question. Try again or type it.",
  );
  expect((await speechLog(page)).aborts).toBe(1);
  expect(api.queries).toEqual([]);
});

test("browsers without speech recognition hide the voice button and keep typing", async ({ page }) => {
  await installSpeech(page, null);
  const api = await routeApi(page, () => answer(keysAnswer));

  await page.goto("/app");
  await expect(voiceStatus(page)).toHaveText("Voice input is not available in this browser. Type your question instead.");
  await expect(voiceButton(page)).toHaveCount(0);
  await questionInput(page).fill("Where are my keys?");
  await page.locator(".question-form").getByRole("button", { name: "Ask", exact: true }).click();
  await expect(answerText(page)).toHaveText(keysAnswer);
  expect(api.queries).toHaveLength(1);
});

test("a failed /api/query after transcription shows the existing error and writes nothing", async ({ page }) => {
  await installSpeech(page, { mode: "result", transcript: "Where are my keys?" });
  const api = await routeApi(page, () => ({ status: 500, body: { detail: "The memory service is unavailable." } }));

  await page.goto("/app");
  await voiceButton(page).click();
  await expect(page.locator(".error-message")).toHaveText("The memory service is unavailable.");
  await expect(voiceStatus(page)).toHaveText("Heard: “Where are my keys?”");
  expect(api.queries).toHaveLength(1);
  expect(api.otherWrites).toEqual([]);
});

test("Arabic speech is recognized in Arabic and sent unchanged", async ({ page }) => {
  await installSpeech(page, { mode: "result", transcript: "أين مفاتيحي؟" });
  const api = await routeApi(page, (query) =>
    answer(query.question.includes("مفاتيح") ? "آخر تسجيل: مفاتيحك على طاولة المطبخ." : "كنت تقرأ.", "ar"),
  );

  await page.goto("/app");
  await page.getByRole("button", { name: "العربية" }).click();
  await page.getByRole("button", { name: "اسأل بالصوت" }).click();
  await expect(answerText(page)).toHaveText("آخر تسجيل: مفاتيحك على طاولة المطبخ.");

  await setSpeech(page, { mode: "result", transcript: "ماذا كنت أفعل الساعة 10 صباحًا؟" });
  await page.getByRole("button", { name: "اسأل بالصوت" }).click();
  await expect(questionInput(page)).toHaveValue("ماذا كنت أفعل الساعة 10 صباحًا؟");
  await expect(answerText(page)).toHaveText("كنت تقرأ.");

  expect(api.queries).toEqual([
    { question: "أين مفاتيحي؟", language: "ar", userId: "1" },
    { question: "ماذا كنت أفعل الساعة 10 صباحًا؟", language: "ar", userId: "1" },
  ]);
  expect((await speechLog(page)).languages).toEqual(["ar-AE", "ar-AE"]);
});

test("English time questions are sent unchanged", async ({ page }) => {
  await installSpeech(page, { mode: "result", transcript: "What was I doing at 10 AM?" });
  const api = await routeApi(page, () => answer("At 10:05 AM you were reading in the living room."));

  await page.goto("/app");
  await voiceButton(page).click();
  await expect(answerText(page)).toHaveText("At 10:05 AM you were reading in the living room.");
  expect(api.queries).toEqual([{ question: "What was I doing at 10 AM?", language: "en", userId: "1" }]);
});

test("voice questions use the selected profile, and switching profile cancels listening", async ({ page }) => {
  await installSpeech(page, { mode: "result", transcript: "Where are my keys?" });
  const api = await routeApi(page, (query) => answer(query.userId === "2" ? "Jordan's keys" : "Alex's keys"));

  await page.goto("/app");
  await voiceButton(page).click();
  await expect(answerText(page)).toHaveText("Alex's keys");

  await setSpeech(page, { mode: "listening" });
  await voiceButton(page).click();
  await expect(voiceStatus(page)).toHaveText("Microphone on. Ask one question.");
  await page.getByRole("combobox", { name: "Profile" }).selectOption({ label: "Jordan" });
  await expect(voiceButton(page)).toBeVisible();
  expect((await speechLog(page)).aborts).toBe(1);

  await setSpeech(page, { mode: "result", transcript: "Where are my keys?" });
  await voiceButton(page).click();
  await expect(answerText(page)).toHaveText("Jordan's keys");

  expect(api.queries.map((query) => query.userId)).toEqual(["1", "2"]);
});

test("with the camera on, the one question box also answers in the camera view", async ({ page }) => {
  await installSpeech(page, { mode: "result", transcript: "Where are my keys?" });
  const api = await routeApi(page, () => answer(keysAnswer));

  await page.goto("/app");
  await page.getByRole("button", { name: "Start camera" }).click();
  await expect(page.getByText("Camera active", { exact: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: /Ask a supported memory question/ })).toHaveCount(1);
  await voiceButton(page).click();

  await expect(page.getByRole("complementary", { name: "MemoryCue camera cue" }).getByText(keysAnswer)).toBeVisible();
  await expect(answerText(page)).toHaveText(keysAnswer);
  await expect(questionInput(page)).toHaveValue("Where are my keys?");
  expect(api.queries).toEqual([{ question: "Where are my keys?", language: "en", userId: "1" }]);
  expect(api.otherWrites).toEqual([]);
});

test("switching profile clears the question box and the camera answer", async ({ page }) => {
  await installSpeech(page, { mode: "result", transcript: "Where are my keys?" });
  await routeApi(page, () => answer(keysAnswer));

  await page.goto("/app");
  await page.getByRole("button", { name: "Start camera" }).click();
  await expect(page.getByText("Camera active", { exact: true })).toBeVisible();
  const cameraCue = page.getByRole("complementary", { name: "MemoryCue camera cue" });
  await voiceButton(page).click();
  await expect(questionInput(page)).toHaveValue("Where are my keys?");
  await expect(cameraCue.getByText(keysAnswer)).toBeVisible();

  await page.getByRole("combobox", { name: "Profile" }).selectOption({ label: "Jordan" });
  await expect(questionInput(page)).toHaveValue("");
  await expect(cameraCue.getByText(keysAnswer)).toHaveCount(0);
  await expect(answerText(page)).toHaveCount(0);
  await expect(page.getByText("Camera active", { exact: true })).toBeVisible();

  await questionInput(page).fill("Where is my wallet?");
  await page.getByRole("combobox", { name: "Profile" }).selectOption({ label: "Alex" });
  await expect(questionInput(page)).toHaveValue("");
});

test("on a phone the camera answer fits inside the camera view with its dismiss button reachable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const evidence = (id: number, detail: string) => ({
    source_id: `memory:${id}`,
    label: `Saved memory #${id}`,
    detail,
    recorded_at: "2026-10-03T10:18:00",
    image_url: null,
    corrected_at: null,
    corrected_by: null,
  });
  await routeApi(page, () => ({
    body: {
      ...answer(keysAnswer).body,
      evidence: [
        evidence(2, "Keys visible on the kitchen counter next to the fruit bowl."),
        evidence(3, "Alex's keys were visible on the kitchen counter."),
      ],
    },
  }));

  await page.goto("/app");
  await page.getByRole("button", { name: "Start camera" }).click();
  await expect(page.getByText("Camera active", { exact: true })).toBeVisible();
  await questionInput(page).fill("Where are my keys?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  const cameraCue = page.getByRole("complementary", { name: "MemoryCue camera cue" });
  await expect(cameraCue.getByText(keysAnswer)).toBeVisible();

  const layout = await page.evaluate(() => {
    const view = document.querySelector(".camera-view")!.getBoundingClientRect();
    const hud = document.querySelector(".hud-overlay")!.getBoundingClientRect();
    const dismiss = document.querySelector(".hud-dismiss-button")!.getBoundingClientRect();
    return { viewTop: view.top, viewBottom: view.bottom, hudTop: hud.top, hudBottom: hud.bottom, dismissTop: dismiss.top };
  });
  expect(layout.hudTop).toBeGreaterThanOrEqual(layout.viewTop);
  expect(layout.hudBottom).toBeLessThanOrEqual(layout.viewBottom);
  expect(layout.dismissTop).toBeGreaterThanOrEqual(layout.viewTop);
  await cameraCue.getByRole("button", { name: "Dismiss" }).click();
  await expect(cameraCue.getByText(keysAnswer)).toHaveCount(0);
});
