import { expect, Page, Route, test } from "@playwright/test";

const API_ORIGIN = "http://localhost:8000";
const PRIMARY_CAPABILITIES = {
  role: "primary",
  can_manage_profile: true,
  can_manage_people: true,
  can_manage_schedule: true,
  can_manage_objects: true,
  can_manage_notes: true,
};
const VIEWER_CAPABILITIES = {
  role: "viewer",
  can_manage_profile: false,
  can_manage_people: false,
  can_manage_schedule: false,
  can_manage_objects: false,
  can_manage_notes: false,
};

const alex = { user_id: 1, name: "Alex", preferred_name: "Alex", ...PRIMARY_CAPABILITIES };
const jordan = { user_id: 2, name: "Jordan", preferred_name: "Jordan", ...PRIMARY_CAPABILITIES };
const taylorAlex = { user_id: 1, name: "Alex", preferred_name: "Alex", ...VIEWER_CAPABILITIES };

function cue(message = "Sarah visits at 3:30 PM.", expiresInMs = 60_000) {
  return {
    id: "schedule:101",
    type: "schedule_upcoming",
    title: "Coming up",
    message,
    priority: 50,
    source_ids: ["schedule:101"],
    expires_at: new Date(Date.now() + expiresInMs).toISOString(),
  };
}

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

async function installCamera(page: Page, options: { visible?: boolean; fastCuePoll?: boolean } = {}) {
  await page.addInitScript(({ visible, fastCuePoll }) => {
    const state = window as Window & {
      __memoryCueVisible?: boolean;
      __setMemoryCueVisibility?: (next: boolean) => void;
    };
    state.__memoryCueVisible = visible;
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => state.__memoryCueVisible ? "visible" : "hidden",
    });
    state.__setMemoryCueVisibility = (next) => {
      state.__memoryCueVisible = next;
      document.dispatchEvent(new Event("visibilitychange"));
    };
    if (fastCuePoll) {
      const nativeSetInterval = window.setInterval.bind(window);
      window.setInterval = ((handler: TimerHandler, timeout?: number, ...args: unknown[]) =>
        nativeSetInterval(handler, timeout === 45_000 ? 150 : timeout, ...args)) as typeof window.setInterval;
    }
  }, { visible: options.visible ?? true, fastCuePoll: options.fastCuePoll ?? false });
}

function patientProfile(userId: number, preferredName: string) {
  return {
    user_id: userId,
    preferred_name: preferredName,
    short_bio: `${preferredName} profile`,
    home_context: `${preferredName} home`,
    response_style: "Short, calm reminders",
  };
}

async function fulfillPatientDetail(route: Route, patientId: number) {
  const path = new URL(route.request().url()).pathname;
  const name = patientId === 1 ? "Alex" : "Jordan";
  if (path.endsWith("/profile")) {
    return fulfillJson(route, patientProfile(patientId, name));
  }
  if (path.endsWith("/people")) {
    return fulfillJson(route, [{ id: patientId * 10, name: "Sarah", relationship: patientId === 1 ? "Daughter" : "Neighbor", face_enrolled: false }]);
  }
  if (path.endsWith("/objects")) {
    return fulfillJson(route, [{ id: patientId * 20, name: "keys", notes: `${name} keys` }]);
  }
  if (path.endsWith("/schedule")) {
    return fulfillJson(route, [{ id: patientId * 30, title: `${name} visit`, scheduled_at: "2026-09-12T15:30:00" }]);
  }
  if (path.endsWith("/notes")) {
    return fulfillJson(route, [{ id: patientId * 40, caregiver_id: 1, note: `${name} note`, created_at: "2026-09-12T10:00:00" }]);
  }
  return fulfillJson(route, { detail: "Not found" }, 404);
}

test("an inactive camera and hidden page do not acknowledge an unseen cue", async ({ page }) => {
  await installCamera(page, { visible: false });
  let acknowledgementCount = 0;
  await page.route("**/api/**", async (route) => {
    if (await fulfillPreflight(route)) return;
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "GET" && path === "/api/cues") {
      return fulfillJson(route, { cues: [cue()] });
    }
    if (request.method() === "POST" && path === "/api/cues/present") {
      acknowledgementCount += 1;
      return fulfillJson(route, { status: "presented", cue_id: "schedule:101", presented_at: new Date().toISOString() });
    }
    return fulfillJson(route, { detail: "Not found" }, 404);
  });

  await page.goto("/app");
  await expect.poll(() => acknowledgementCount).toBe(0);
  await page.getByRole("button", { name: "Start camera" }).click();
  await expect(page.getByText("Camera active", { exact: true })).toBeVisible();
  await page.waitForTimeout(250);
  expect(acknowledgementCount).toBe(0);

  await page.evaluate(() => {
    (window as Window & { __setMemoryCueVisibility?: (next: boolean) => void })
      .__setMemoryCueVisibility?.(true);
  });
  await expect.poll(() => acknowledgementCount).toBe(1);
  await expect(page.getByText("Sarah visits at 3:30 PM.", { exact: true })).toBeVisible();
});

test("a displayed cue survives an empty poll, acknowledges once, and expires promptly", async ({ page }) => {
  await installCamera(page, { fastCuePoll: true });
  let offerCue = false;
  let offeredCueReads = 0;
  let acknowledgementCount = 0;
  await page.route("**/api/**", async (route) => {
    if (await fulfillPreflight(route)) return;
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "GET" && path === "/api/cues") {
      if (!offerCue) {
        return fulfillJson(route, { cues: [] });
      }
      offeredCueReads += 1;
      return fulfillJson(route, { cues: offeredCueReads === 1 ? [cue("Visible reminder", 2_500)] : [] });
    }
    if (request.method() === "POST" && path === "/api/cues/present") {
      acknowledgementCount += 1;
      return fulfillJson(route, { status: "presented", cue_id: "schedule:101", presented_at: new Date().toISOString() });
    }
    return fulfillJson(route, { detail: "Not found" }, 404);
  });

  await page.goto("/app");
  await page.getByRole("button", { name: "Start camera" }).click();
  await expect(page.getByText("Camera active", { exact: true })).toBeVisible();
  const cueToggle = page.getByRole("checkbox", { name: "Optional cues" });
  await cueToggle.uncheck();
  offerCue = true;
  await cueToggle.check();
  await expect(page.getByText("Visible reminder", { exact: true })).toBeVisible();
  await expect.poll(() => acknowledgementCount).toBe(1);
  await expect.poll(() => offeredCueReads).toBeGreaterThanOrEqual(2);
  await expect(page.getByText("Visible reminder", { exact: true })).toBeVisible();
  await page.waitForTimeout(300);
  expect(acknowledgementCount).toBe(1);
  await expect(page.getByText("Visible reminder", { exact: true })).toBeHidden({ timeout: 4_000 });
});

test("stale caregiver detail responses cannot cross a patient selection", async ({ page }) => {
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/patients/1/notes") && (!init?.method || init.method === "GET")) {
        return nativeFetch(input, { ...init, signal: undefined });
      }
      return nativeFetch(input, init);
    }) as typeof window.fetch;
  });
  let releaseAlexNotes!: () => void;
  let alexNotesStarted = false;
  const alexNotesGate = new Promise<void>((resolve) => { releaseAlexNotes = resolve; });
  await page.route("**/api/caregiver/**", async (route) => {
    if (await fulfillPreflight(route)) return;
    const request = route.request();
    const path = new URL(request.url()).pathname;
    expect(request.headers()["x-memorycue-caregiver-id"]).toBe("1");
    if (path === "/api/caregiver/patients") {
      return fulfillJson(route, [alex, jordan]);
    }
    const match = path.match(/\/patients\/(\d+)\//);
    if (!match) return fulfillJson(route, { detail: "Not found" }, 404);
    const patientId = Number(match[1]);
    if (patientId === 1 && path.endsWith("/notes")) {
      alexNotesStarted = true;
      await alexNotesGate;
    }
    return fulfillPatientDetail(route, patientId);
  });

  await page.goto("/caregiver");
  await expect.poll(() => alexNotesStarted).toBe(true);
  await page.getByRole("button", { name: "Jordan Jordan" }).click();
  await expect(page.getByRole("heading", { name: "Jordan's setup" })).toBeVisible();
  await expect(page.getByLabel("Preferred name")).toHaveValue("Jordan");
  releaseAlexNotes();
  await page.waitForTimeout(250);
  await expect(page.getByLabel("Preferred name")).toHaveValue("Jordan");
  await expect(page.getByRole("heading", { name: "Jordan's setup" })).toBeVisible();
});

test("late caregiver mutation feedback cannot update another selected profile", async ({ page }) => {
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/patients/1/profile") && init?.method === "PATCH") {
        return nativeFetch(input, { ...init, signal: undefined });
      }
      return nativeFetch(input, init);
    }) as typeof window.fetch;
  });
  let releaseSave!: () => void;
  let saveStarted = false;
  const saveGate = new Promise<void>((resolve) => { releaseSave = resolve; });
  await page.route("**/api/caregiver/**", async (route) => {
    if (await fulfillPreflight(route)) return;
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/caregiver/patients") return fulfillJson(route, [alex, jordan]);
    if (request.method() === "PATCH" && path.endsWith("/patients/1/profile")) {
      saveStarted = true;
      await saveGate;
      return fulfillJson(route, patientProfile(1, "Changed Alex"));
    }
    const match = path.match(/\/patients\/(\d+)\//);
    return match ? fulfillPatientDetail(route, Number(match[1])) : fulfillJson(route, { detail: "Not found" }, 404);
  });

  await page.goto("/caregiver");
  await expect(page.getByLabel("Preferred name")).toHaveValue("Alex");
  await page.getByLabel("Preferred name").fill("Changed Alex");
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect.poll(() => saveStarted).toBe(true);
  await page.getByRole("button", { name: "Jordan Jordan" }).click();
  await expect(page.getByLabel("Preferred name")).toHaveValue("Jordan");
  releaseSave();
  await page.waitForTimeout(250);
  await expect(page.getByText("Profile information saved.", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Preferred name")).toHaveValue("Jordan");
});

test("viewer capabilities keep caregiver data readable and every mutation control disabled", async ({ page }) => {
  let rejectedMutationCount = 0;
  await page.route("**/api/caregiver/**", async (route) => {
    if (await fulfillPreflight(route)) return;
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const caregiverId = request.headers()["x-memorycue-caregiver-id"];
    if (path === "/api/caregiver/patients") {
      return fulfillJson(route, caregiverId === "3" ? [taylorAlex] : [alex]);
    }
    if (request.method() !== "GET") {
      rejectedMutationCount += 1;
      return fulfillJson(route, { detail: "Caregiver permission required." }, 403);
    }
    return fulfillPatientDetail(route, 1);
  });

  await page.goto("/caregiver");
  await page.getByLabel("Demo caregiver").selectOption("3");
  await expect(page.getByText("This caregiver can view this section but cannot make changes.")).toBeVisible();
  await expect(page.getByLabel("Preferred name")).toBeDisabled();
  await expect(page.getByRole("button", { name: "Save profile" })).toBeDisabled();

  await page.getByRole("button", { name: "People" }).click();
  await expect(page.getByLabel("Person name")).toHaveValue("Sarah");
  await expect(page.getByLabel("Person name")).toBeDisabled();
  await expect(page.getByRole("button", { name: "Add person" })).toBeDisabled();
  await expect(page.locator('input[type="file"]')).toBeDisabled();

  await page.getByRole("button", { name: "Important objects" }).click();
  await expect(page.getByLabel("Important object name")).toBeDisabled();
  await expect(page.getByRole("button", { name: "Add object" })).toBeDisabled();

  await page.getByRole("button", { name: "Schedule" }).click();
  await expect(page.getByLabel("Schedule title")).toBeDisabled();
  await expect(page.getByRole("button", { name: "Add schedule item" })).toBeDisabled();

  await page.getByRole("button", { name: "Notes" }).click();
  await expect(page.getByLabel("Caregiver note")).toBeDisabled();
  await expect(page.getByRole("button", { name: "Add note" })).toBeDisabled();

  const responseStatus = await page.evaluate(async () => {
    const response = await fetch("http://localhost:8000/api/caregiver/patients/1/profile", {
      method: "PATCH",
      headers: { "Content-Type": "application/json", "X-MemoryCue-Caregiver-Id": "3" },
      body: JSON.stringify({ preferred_name: "Not allowed" }),
    });
    return response.status;
  });
  expect(responseStatus).toBe(403);
  expect(rejectedMutationCount).toBe(1);
});

test("demo failures differ from empty results and protected thumbnails stay profile-scoped", async ({ page }) => {
  let memoryMode: "error" | "data" | "empty" = "error";
  let cueMode: "error" | "empty" = "error";
  let releaseAlexImage!: () => void;
  let alexImageStarted = false;
  const alexImageGate = new Promise<void>((resolve) => { releaseAlexImage = resolve; });
  const mediaHeaders: Array<{ path: string; userId: string | undefined }> = [];
  await page.addInitScript(() => {
    const state = window as Window & {
      __createdMemoryBlobs?: Array<{ url: string; size: number }>;
      __revokedMemoryBlobs?: string[];
    };
    state.__createdMemoryBlobs = [];
    state.__revokedMemoryBlobs = [];
    const nativeCreate = URL.createObjectURL.bind(URL);
    const nativeRevoke = URL.revokeObjectURL.bind(URL);
    URL.createObjectURL = (blob) => {
      const url = nativeCreate(blob);
      state.__createdMemoryBlobs?.push({ url, size: blob instanceof Blob ? blob.size : -1 });
      return url;
    };
    URL.revokeObjectURL = (url) => {
      state.__revokedMemoryBlobs?.push(url);
      nativeRevoke(url);
    };
    const nativeFetch = window.fetch.bind(window);
    window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.endsWith("/api/media/alex.jpg")) {
        return nativeFetch(input, { ...init, signal: undefined });
      }
      return nativeFetch(input, init);
    }) as typeof window.fetch;
  });
  await page.route("**/api/**", async (route) => {
    if (await fulfillPreflight(route)) return;
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const userId = request.headers()["x-memorycue-user-id"];
    if (request.method() === "GET" && path === "/api/memories") {
      if (memoryMode === "error") return fulfillJson(route, { detail: "Memory database unavailable." }, 500);
      if (memoryMode === "empty") return fulfillJson(route, []);
      const isAlex = userId === "1";
      return fulfillJson(route, [{
        id: isAlex ? 1 : 2,
        timestamp: "2026-09-12T10:00:00",
        location: isAlex ? "Alex room" : "Jordan room",
        description: isAlex ? "Alex memory" : "Jordan memory",
        image_url: isAlex ? "/api/media/alex.jpg" : "/api/media/jordan.jpg",
      }]);
    }
    if (request.method() === "GET" && path === "/api/cues") {
      return cueMode === "error"
        ? fulfillJson(route, { detail: "Cue access denied." }, 401)
        : fulfillJson(route, { cues: [] });
    }
    if (request.method() === "GET" && path.startsWith("/api/media/")) {
      mediaHeaders.push({ path, userId });
      if (path.endsWith("alex.jpg")) {
        alexImageStarted = true;
        await alexImageGate;
      }
      const size = path.endsWith("alex.jpg") ? 20 : 10;
      return route.fulfill({
        status: 200,
        contentType: "image/jpeg",
        headers: { "access-control-allow-origin": "*" },
        body: Buffer.alloc(size, 1),
      });
    }
    return fulfillJson(route, { detail: "Not found" }, 404);
  });

  await page.goto("/demo");
  await expect(page.getByText("Couldn't load memories.", { exact: true })).toBeVisible();
  await expect(page.getByText("Couldn't load the current cue.", { exact: true })).toBeVisible();
  await expect(page.getByText("No memories returned for this profile.")).toHaveCount(0);
  await expect(page.getByText("No eligible cue returned for this profile.")).toHaveCount(0);

  memoryMode = "empty";
  cueMode = "empty";
  const memoryCard = page.locator("section.demo-card").filter({ has: page.getByRole("heading", { name: "Recent memories" }) });
  const cueCard = page.locator("section.demo-card").filter({ has: page.getByRole("heading", { name: "Current cue" }) });
  await memoryCard.getByRole("button", { name: "Retry" }).click();
  await cueCard.getByRole("button", { name: "Retry" }).click();
  await expect(memoryCard.getByText("No memories returned for this profile.")).toBeVisible();
  await expect(cueCard.getByText("No eligible cue returned for this profile.")).toBeVisible();

  memoryMode = "data";
  await page.getByLabel("Profile to inspect").selectOption("2");
  await expect(page.getByText("Jordan room", { exact: true })).toBeVisible();
  await page.getByLabel("Profile to inspect").selectOption("1");
  await expect.poll(() => alexImageStarted).toBe(true);
  await page.getByLabel("Profile to inspect").selectOption("2");
  await expect(page.getByText("Jordan room", { exact: true })).toBeVisible();
  await expect.poll(async () => page.evaluate(() =>
    (window as Window & { __createdMemoryBlobs?: Array<{ size: number }> }).__createdMemoryBlobs?.map((entry) => entry.size) ?? [],
  )).toContain(10);
  releaseAlexImage();
  await page.waitForTimeout(250);
  const createdSizes = await page.evaluate(() =>
    (window as Window & { __createdMemoryBlobs?: Array<{ size: number }> }).__createdMemoryBlobs?.map((entry) => entry.size) ?? [],
  );
  expect(createdSizes).not.toContain(20);
  expect(mediaHeaders).toContainEqual({ path: "/api/media/alex.jpg", userId: "1" });
  expect(mediaHeaders).toContainEqual({ path: "/api/media/jordan.jpg", userId: "2" });

  const jordanImageUrl = await page.locator(".recent-memory img").getAttribute("src");
  await page.getByLabel("Profile to inspect").selectOption("1");
  await expect(page.getByText("Alex room", { exact: true })).toBeVisible();
  await expect.poll(async () => page.evaluate(() =>
    (window as Window & { __revokedMemoryBlobs?: string[] }).__revokedMemoryBlobs ?? [],
  )).toContain(jordanImageUrl);
});

test("the 390px camera heading aligns with its helper and the face-check sentence has spacing", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/**", async (route) => {
    if (await fulfillPreflight(route)) return;
    return fulfillJson(route, { cues: [] });
  });
  await page.goto("/app");
  await expect(page.locator(".camera-panel-heading")).toHaveCSS("align-items", "flex-start");
  await expect(page.locator(".camera-helper")).toContainText("Who is this? checks one image");
  const widths = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
  expect(widths.scroll).toBe(widths.client);
});
