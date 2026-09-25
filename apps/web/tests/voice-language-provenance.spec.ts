import { expect, Page, Route, test } from "@playwright/test";

type QueryPayload = { question: string; language: string };

async function fulfillJson(route: Route, payload: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: { "access-control-allow-origin": "*" },
    body: JSON.stringify(payload),
  });
}

async function fulfillPreflight(route: Route): Promise<boolean> {
  if (route.request().method() !== "OPTIONS") {
    return false;
  }
  await route.fulfill({
    status: 204,
    headers: {
      "access-control-allow-origin": "*",
      "access-control-allow-headers": "*",
      "access-control-allow-methods": "GET,POST,PATCH,DELETE,OPTIONS",
    },
  });
  return true;
}

/** Record spoken utterances and expose a scripted speech-recognition result. */
async function installSpeech(page: Page, transcript: string) {
  await page.addInitScript((spokenTranscript) => {
    const state = window as Window & {
      __spokenAnswers?: Array<{ text: string; lang: string }>;
    };
    state.__spokenAnswers = [];
    class FakeUtterance {
      text: string;
      lang = "";
      rate = 1;
      constructor(text: string) {
        this.text = text;
      }
    }
    Object.defineProperty(window, "SpeechSynthesisUtterance", { value: FakeUtterance, configurable: true });
    Object.defineProperty(window, "speechSynthesis", {
      configurable: true,
      value: {
        cancel: () => undefined,
        speak: (utterance: { text: string; lang: string }) => {
          state.__spokenAnswers?.push({ text: utterance.text, lang: utterance.lang });
        },
      },
    });
    class FakeRecognition {
      lang = "";
      continuous = false;
      interimResults = false;
      maxAlternatives = 1;
      onresult: ((event: unknown) => void) | null = null;
      onerror: ((event: unknown) => void) | null = null;
      onend: (() => void) | null = null;
      start() {
        setTimeout(() => {
          this.onresult?.({ results: [[{ transcript: spokenTranscript }]] });
          this.onend?.();
        }, 50);
      }
      stop() {
        this.onend?.();
      }
      abort() {
        this.onend?.();
      }
    }
    Object.defineProperty(window, "SpeechRecognition", { value: FakeRecognition, configurable: true });
  }, transcript);
}

async function routeApi(page: Page, onQuery: (payload: QueryPayload) => unknown) {
  await page.route("**/api/**", async (route) => {
    if (await fulfillPreflight(route)) return;
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "POST" && path === "/api/query") {
      return fulfillJson(route, onQuery(request.postDataJSON() as QueryPayload));
    }
    if (request.method() === "GET" && path === "/api/cues") {
      return fulfillJson(route, { cues: [] });
    }
    return fulfillJson(route, { detail: "Not found" }, 404);
  });
}

function hud(page: Page) {
  return page.getByRole("complementary", { name: "MemoryCue camera cue" });
}

const keysAnswer = {
  answer: "I last saw your keys on the kitchen counter at 10:18 AM.",
  intent: "object_location",
  source_ids: ["memory:2"],
  evidence: [
    {
      source_id: "memory:2",
      label: "Saved memory",
      detail: "kitchen counter",
      recorded_at: "2026-09-25T10:18:00",
    },
  ],
  language: "en",
};

test("a spoken question is answered aloud with its saved source", async ({ page }) => {
  await installSpeech(page, "Where are my keys?");
  const questions: QueryPayload[] = [];
  await routeApi(page, (payload) => {
    questions.push(payload);
    return keysAnswer;
  });

  await page.goto("/app");
  await page.getByRole("button", { name: "Start camera" }).click();
  await expect(page.getByText("Camera active", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Speak" }).click();

  await expect(hud(page).getByText(keysAnswer.answer, { exact: true })).toBeVisible();
  expect(questions).toEqual([{ question: "Where are my keys?", language: "en" }]);

  const provenance = page.getByTestId("hud-provenance");
  await expect(provenance).toContainText("Saved memory");
  await expect(provenance).toContainText("kitchen counter");

  const spoken = await page.evaluate(
    () => (window as Window & { __spokenAnswers?: Array<{ text: string; lang: string }> }).__spokenAnswers ?? [],
  );
  expect(spoken).toEqual([{ text: keysAnswer.answer, lang: "en-US" }]);
});

test("the Arabic toggle sends and speaks Arabic answers", async ({ page }) => {
  await installSpeech(page, "أين مفاتيحي؟");
  const questions: QueryPayload[] = [];
  await routeApi(page, (payload) => {
    questions.push(payload);
    return { ...keysAnswer, answer: "آخر مرة رأيت مفاتيحك على kitchen counter.", language: "ar" };
  });

  await page.goto("/app");
  await page.getByRole("button", { name: "Start camera" }).click();
  await expect(page.getByText("Camera active", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "العربية" }).click();
  await page.getByRole("button", { name: "أين مفاتيحي؟" }).click();

  await expect(hud(page).getByText("آخر مرة رأيت مفاتيحك على kitchen counter.", { exact: true })).toBeVisible();
  expect(questions).toEqual([{ question: "أين مفاتيحي؟", language: "ar" }]);

  const spoken = await page.evaluate(
    () => (window as Window & { __spokenAnswers?: Array<{ text: string; lang: string }> }).__spokenAnswers ?? [],
  );
  expect(spoken).toEqual([{ text: "آخر مرة رأيت مفاتيحك على kitchen counter.", lang: "ar-AE" }]);
});

test("an ungrounded question shows no sources and refuses to guess", async ({ page }) => {
  await installSpeech(page, "Where is my passport?");
  await routeApi(page, () => ({
    answer: "I couldn't find matching saved information for that.",
    intent: "unknown",
    source_ids: [],
    evidence: [],
    language: "en",
  }));

  await page.goto("/app");
  await page.getByRole("button", { name: "Start camera" }).click();
  await expect(page.getByText("Camera active", { exact: true })).toBeVisible();
  const hudControls = page.getByLabel("MemoryCue camera cue controls");
  await hudControls.getByRole("textbox", { name: "Ask MemoryCue" }).fill("Where is my passport?");
  await hudControls.getByRole("button", { name: "Ask", exact: true }).click();

  await expect(
    hud(page).getByText("I couldn't find matching saved information for that.", { exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("hud-no-sources")).toContainText("does not guess");
  await expect(page.getByTestId("hud-provenance")).toHaveCount(0);
});
