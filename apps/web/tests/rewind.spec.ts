import { expect, Page, Route, test } from "@playwright/test";

type RewindQuery = { windowMinutes: string; includeEarlier: string };

const PNG_PIXEL = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

async function fulfillJson(route: Route, payload: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: { "access-control-allow-origin": "*" },
    body: JSON.stringify(payload),
  });
}

function moment(memoryId: number, description: string, recordedAt: string, source = "capture") {
  return {
    memory_id: memoryId,
    recorded_at: recordedAt,
    location: "Kitchen",
    activity: description,
    description,
    image_url: `/api/media/moment-${memoryId}.jpg`,
    source,
  };
}

const recentMoments = [
  moment(1, "Pouring water in the kitchen", "2026-09-25T11:02:00"),
  moment(2, "Setting keys on the counter", "2026-09-25T11:05:00"),
];

async function routeRewind(
  page: Page,
  handler: (query: RewindQuery) => unknown,
  queries: RewindQuery[] = [],
) {
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
    const url = new URL(request.url());
    if (url.pathname === "/api/rewind") {
      const query = {
        windowMinutes: url.searchParams.get("window_minutes") ?? "",
        includeEarlier: url.searchParams.get("include_earlier") ?? "",
      };
      queries.push(query);
      return fulfillJson(route, handler(query));
    }
    if (url.pathname.startsWith("/api/media/")) {
      return route.fulfill({
        status: 200,
        contentType: "image/png",
        headers: { "access-control-allow-origin": "*" },
        body: PNG_PIXEL,
      });
    }
    if (url.pathname === "/api/cues") {
      return fulfillJson(route, { cues: [] });
    }
    return fulfillJson(route, { detail: "Not found" }, 404);
  });
}

function panel(page: Page) {
  return page.getByRole("region", { name: "MemoryCue saved moments" });
}

test("saved moments appear with their photo, time, and source", async ({ page }) => {
  await routeRewind(page, () => ({
    summary: "These are 2 saved moments, not continuous recording.",
    moments: recentMoments,
    window_minutes: 1440,
    within_window: true,
    has_earlier: false,
  }));

  await page.goto("/app");

  const strip = page.getByTestId("rewind-strip");
  await expect(strip.getByText("Setting keys on the counter")).toBeVisible();
  await expect(strip.getByText("Live capture").first()).toBeVisible();
  await expect(strip.locator("img")).toHaveCount(2);
});

test("each saved moment names where its photo came from", async ({ page }) => {
  await routeRewind(page, () => ({
    summary: "These are 4 saved moments, not continuous recording.",
    moments: [
      moment(1, "Camera moment", "2026-09-25T11:00:00", "capture"),
      moment(2, "Uploaded moment", "2026-09-25T11:01:00", "upload"),
      moment(3, "Unknown-origin moment", "2026-09-25T11:02:00", "photo"),
      { ...moment(4, "Seeded moment", "2026-09-25T11:03:00", "sample"), image_url: null },
    ],
    window_minutes: 1440,
    within_window: true,
    has_earlier: false,
  }));

  await page.goto("/app");

  const strip = page.getByTestId("rewind-strip");
  const card = (text: string) => strip.locator("li", { hasText: text });
  await expect(card("Camera moment")).toContainText("Live capture");
  await expect(card("Uploaded moment")).toContainText("Uploaded photo");
  await expect(card("Uploaded moment")).not.toContainText("Live capture");
  await expect(card("Unknown-origin moment")).toContainText("Saved photo");
  await expect(card("Seeded moment")).toContainText("Sample record");
  await expect(strip.getByText("Live capture")).toHaveCount(1);
});

test("rewinding an empty window says so and can show earlier moments", async ({ page }) => {
  const queries: RewindQuery[] = [];
  await routeRewind(
    page,
    (query) => {
      if (query.windowMinutes === "1440") {
        return {
          summary: "These are 2 saved moments, not continuous recording.",
          moments: recentMoments,
          window_minutes: 1440,
          within_window: true,
          has_earlier: false,
        };
      }
      if (query.includeEarlier === "true") {
        return {
          summary: "These are 2 saved moments, not continuous recording.",
          moments: recentMoments,
          window_minutes: 10,
          within_window: false,
          has_earlier: true,
        };
      }
      return {
        summary: "No moments were saved in the last 10 minutes. You can show earlier saved moments.",
        moments: [],
        window_minutes: 10,
        within_window: false,
        has_earlier: true,
      };
    },
    queries,
  );

  await page.goto("/app");
  await panel(page).getByRole("button", { name: "Rewind recent moments" }).click();

  const recap = page.getByTestId("rewind-recap");
  await expect(recap).toContainText("No moments were saved in the last 10 minutes.");
  await recap.getByRole("button", { name: "Show earlier saved moments" }).click();

  await expect(recap).toContainText("Earlier saved moments, not the last 10 minutes");
  await expect(recap).toContainText("not continuous recording");
  expect(queries.slice(-2)).toEqual([
    { windowMinutes: "10", includeEarlier: "false" },
    { windowMinutes: "10", includeEarlier: "true" },
  ]);
});
