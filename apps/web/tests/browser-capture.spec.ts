import { expect, Page, Route, test } from "@playwright/test";

type Posted = { path: string; body: string };

async function fulfillJson(route: Route, payload: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: { "access-control-allow-origin": "*" },
    body: JSON.stringify(payload),
  });
}

function field(body: string, name: string): string | null {
  const match = body.match(new RegExp(`name="${name}"(?:; filename="[^"]*")?\\r\\n(?:Content-Type: [^\\r]*\\r\\n)?\\r\\n([^\\r]*)`));
  return match ? match[1] : null;
}

async function routeApi(page: Page, posted: Posted[], observationStatus = 201) {
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
    if (request.method() === "POST" && (path === "/api/observations" || path === "/api/memories")) {
      posted.push({ path, body: request.postDataBuffer()?.toString("latin1") ?? "" });
      if (path === "/api/observations") {
        return observationStatus === 201
          ? fulfillJson(route, { id: 41 }, 201)
          : fulfillJson(route, { detail: "Unavailable" }, observationStatus);
      }
      return fulfillJson(route, { id: 7, location: "Hallway table", object_observation_id: null }, 201);
    }
    if (path === "/api/cues") return fulfillJson(route, { cues: [] });
    if (path === "/api/rewind") return fulfillJson(route, { window_minutes: 60, moments: [], earlier: [] });
    return fulfillJson(route, { detail: "Not found" }, 404);
  });
}

async function captureAndSave(page: Page) {
  await page.goto("/app");
  await page.getByRole("button", { name: "Start camera" }).click();
  await expect(page.getByText("Camera active", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Capture image" }).click();
  await expect(page.getByText("Image captured", { exact: true })).toBeVisible();
  await page.getByLabel("Location").fill("Hallway table");
  await page.getByLabel("Description").fill("My wallet is on the hallway table.");
  const save = page.getByRole("button", { name: "Save memory" });
  await expect(save).toBeEnabled();
  await save.click();
  await expect(page.getByText("Memory saved.", { exact: true })).toBeVisible();
}

test("a camera capture becomes an observation and saving reviews it", async ({ page }) => {
  const posted: Posted[] = [];
  await routeApi(page, posted);
  await captureAndSave(page);

  expect(posted.map((entry) => entry.path)).toEqual(["/api/observations", "/api/memories"]);
  const [observation, memory] = posted;
  expect(field(observation.body, "source")).toBe("browser_camera");
  expect(field(observation.body, "analyze")).toBe("false");
  expect(field(observation.body, "timestamp")).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/);
  expect(observation.body).toContain('name="image"; filename="glasses-capture-');
  expect(observation.body).not.toContain('name="latitude"');
  expect(field(memory.body, "observation_id")).toBe("41");
  expect(memory.body).not.toContain('name="image"');
  expect(field(memory.body, "timestamp")).toBe(field(observation.body, "timestamp")?.slice(0, 16));
});

test("saving still uploads the photo when the capture could not be recorded", async ({ page }) => {
  const posted: Posted[] = [];
  await routeApi(page, posted, 503);
  await captureAndSave(page);

  const memory = posted.find((entry) => entry.path === "/api/memories");
  expect(memory?.body).toContain('name="image"; filename="glasses-capture-');
  expect(field(memory?.body ?? "", "source")).toBe("browser_camera");
  expect(memory?.body).not.toContain('name="observation_id"');
});
