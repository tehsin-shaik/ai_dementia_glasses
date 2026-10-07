import { expect, Page, Route, test } from "@playwright/test";

type RecordedQuery = { question: string; language: string; userId: string | null };

const keysAnswer = {
  answer: "Last recorded: your keys on the kitchen counter at 10:18 AM.",
  intent: "object_location",
  source_ids: ["memory:3"],
  evidence: [
    {
      source_id: "memory:3",
      label: "Saved memory #3",
      detail: "keys visible on kitchen counter",
      recorded_at: "2026-10-03T10:18:00",
      image_url: null,
      corrected_at: null,
      corrected_by: null,
    },
  ],
  language: "en",
};

const unknownAnswer = {
  answer: "I couldn't find matching saved information for that.",
  intent: "unknown",
  source_ids: [],
  evidence: [],
  language: "en",
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*" },
    body: JSON.stringify(body),
  });
}

async function routeQuery(
  page: Page,
  answer: (query: RecordedQuery) => unknown | Promise<unknown>,
): Promise<RecordedQuery[]> {
  const queries: RecordedQuery[] = [];
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") return fulfillJson(route, {});
    if (request.method() === "POST" && new URL(request.url()).pathname === "/api/query") {
      const body = request.postDataJSON() as { question: string; language: string };
      const query = { ...body, userId: request.headers()["x-memorycue-user-id"] ?? null };
      queries.push(query);
      return fulfillJson(route, await answer(query));
    }
    return fulfillJson(route, { detail: "Not found" }, 404);
  });
  return queries;
}

const glasses = (page: Page) => page.getByRole("status", { name: "Glasses display" });

async function saveAllMoments(page: Page) {
  for (let i = 0; i < 4; i += 1) {
    await page.getByRole("button", { name: "Save moment" }).click();
    await page.locator("[data-experience-next]").click();
  }
}

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
});

test("each captured moment must be saved before the walk-through continues", async ({ page }) => {
  await routeQuery(page, () => unknownAnswer);
  await page.goto("/experience");

  await expect(page.getByRole("heading", { name: "A morning through Alex's glasses" })).toBeVisible();
  await expect(page.getByText("Alex · demo profile")).toBeVisible();
  await expect(glasses(page)).toContainText("Making tea");
  await expect(glasses(page)).toContainText("Kitchen · 10:00 AM");

  const next = page.locator("[data-experience-next]");
  await expect(next).toBeDisabled();
  await expect(page.getByText("Save the moment to continue")).toBeVisible();

  await page.getByRole("button", { name: "Save moment" }).click();
  await expect(glasses(page)).toContainText("Saved to memory");
  await expect(next).toBeEnabled();
  await next.click();

  await expect(glasses(page)).toContainText("Reading");
  await expect(next).toBeDisabled();
  await page.locator("[data-experience-back]").click();
  await expect(glasses(page)).toContainText("Saved to memory");
});

test("the keys question uses /api/query for Alex and shows the saved source", async ({ page }) => {
  const queries = await routeQuery(page, (query) => (query.question.includes("keys") ? keysAnswer : unknownAnswer));
  await page.goto("/experience");
  await saveAllMoments(page);

  await expect(page.getByRole("heading", { name: "Where are my keys?" })).toBeVisible();
  await page.getByRole("button", { name: "Ask", exact: true }).click();

  await expect(page.getByTestId("experience-answer")).toHaveText(keysAnswer.answer);
  await expect(glasses(page).getByRole("list", { name: "Sources" })).toContainText("Saved memory #3");
  await expect(page.locator(".exp-canvas")).toHaveAttribute("data-keys-revealed", "true");
  expect(queries).toEqual([{ question: "Where are my keys?", language: "en", userId: "1" }]);
});

test("keys saved somewhere other than the scene's counter are answered without pointing at the counter", async ({ page }) => {
  const tableAnswer = {
    ...keysAnswer,
    answer: "Last recorded: your keys on the hallway table at 5:34 PM.",
    evidence: [{ ...keysAnswer.evidence[0], detail: "keys on the hallway table", recorded_at: "2026-10-03T17:34:00" }],
  };
  await routeQuery(page, () => tableAnswer);
  await page.goto("/experience");
  await saveAllMoments(page);
  await page.getByRole("button", { name: "Ask", exact: true }).click();

  await expect(page.getByTestId("experience-answer")).toHaveText(tableAnswer.answer);
  await expect(page.locator(".exp-canvas")).toHaveAttribute("data-keys-revealed", "false");
});

test("the wallet question shows the unknown answer with no sources", async ({ page }) => {
  const queries = await routeQuery(page, () => unknownAnswer);
  await page.goto("/experience");
  await saveAllMoments(page);
  await page.locator("[data-experience-next]").click();

  await expect(page.getByRole("heading", { name: "Where is my wallet?" })).toBeVisible();
  await page.getByRole("button", { name: "Ask", exact: true }).click();

  await expect(page.getByTestId("experience-answer")).toHaveText(unknownAnswer.answer);
  await expect(glasses(page)).toContainText("MemoryCue does not guess");
  await expect(glasses(page).getByRole("list", { name: "Sources" })).toHaveCount(0);
  expect(queries.map((query) => query.question)).toEqual(["Where is my wallet?"]);
});

test("free-form questions are sent as typed, in the selected language", async ({ page }) => {
  const queries = await routeQuery(page, () => ({ ...unknownAnswer, answer: "لا أملك معلومات محفوظة عن ذلك، ولن أخمّن.", language: "ar" }));
  await page.goto("/experience");
  await saveAllMoments(page);
  await page.locator("[data-experience-next]").click();
  await page.locator("[data-experience-next]").click();

  await page.getByRole("button", { name: "العربية" }).click();
  await expect(page.getByRole("heading", { name: "صباح من خلال نظارة أليكس" })).toBeVisible();
  await page.getByRole("textbox", { name: "اكتب سؤالًا" }).fill("ماذا قال طبيبي؟");
  await page.getByRole("button", { name: "اسأل", exact: true }).click();

  await expect(page.getByTestId("experience-answer")).toHaveText("لا أملك معلومات محفوظة عن ذلك، ولن أخمّن.");
  expect(queries).toEqual([{ question: "ماذا قال طبيبي؟", language: "ar", userId: "1" }]);
});

test("a late answer is dropped after leaving the question step", async ({ page }) => {
  let release: () => void = () => undefined;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await routeQuery(page, async () => {
    await held;
    return keysAnswer;
  });
  await page.goto("/experience");
  await saveAllMoments(page);

  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(glasses(page)).toContainText("Checking saved moments");
  await page.locator("[data-experience-next]").click();
  await expect(page.getByRole("heading", { name: "Where is my wallet?" })).toBeVisible();
  release();

  await page.waitForTimeout(300);
  await expect(page.getByTestId("experience-answer")).toHaveCount(0);
});

test("an unreachable API shows an error instead of an answer", async ({ page }) => {
  await page.route("**/api/**", (route) => route.abort());
  await page.goto("/experience");
  await saveAllMoments(page);
  await page.getByRole("button", { name: "Ask", exact: true }).click();

  await expect(glasses(page).getByRole("alert")).toContainText("MemoryCue couldn't be reached");
  await expect(page.getByTestId("experience-answer")).toHaveCount(0);
});

test("the Arabic layout stays inside a phone-width screen", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await routeQuery(page, () => ({ ...unknownAnswer, answer: "لا أملك معلومات محفوظة عن ذلك، ولن أخمّن.", language: "ar" }));
  await page.goto("/experience");
  await saveAllMoments(page);
  await page.locator("[data-experience-next]").click();
  await page.locator("[data-experience-next]").click();

  await page.getByRole("button", { name: "العربية" }).click();
  await page.getByRole("button", { name: "ماذا كنت أفعل الساعة العاشرة صباحا؟" }).click();
  await expect(page.getByTestId("experience-answer")).toBeVisible();

  const overflow = await page.evaluate(() =>
    [".exp-stage", ".exp-hud", ".exp-narration", ".exp-form", ".exp-suggestions"].filter((selector) => {
      const box = document.querySelector(selector)?.getBoundingClientRect();
      return !box || box.left < 0 || box.right > window.innerWidth;
    }),
  );
  expect(overflow).toEqual([]);
});

test("on a phone the glasses display sits below the scene instead of covering it", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await routeQuery(page, () => keysAnswer);
  await page.goto("/experience");
  await saveAllMoments(page);
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByTestId("experience-answer")).toHaveText(keysAnswer.answer);

  const layout = await page.evaluate(() => {
    const canvas = document.querySelector(".exp-canvas")!.getBoundingClientRect();
    const hud = document.querySelector(".exp-hud")!.getBoundingClientRect();
    return { canvasBottom: canvas.bottom, canvasHeight: canvas.height, hudTop: hud.top };
  });
  expect(layout.canvasHeight).toBeGreaterThan(200);
  expect(layout.hudTop).toBeGreaterThanOrEqual(layout.canvasBottom - 1);
});
