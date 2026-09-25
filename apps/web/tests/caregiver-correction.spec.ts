import { expect, Page, Route, test } from "@playwright/test";

type Moment = {
  memory_id: number;
  recorded_at: string;
  location: string;
  description: string;
  image_url: string | null;
  object_name: string | null;
  object_location: string | null;
  corrections: Array<{
    id: number;
    memory_id: number;
    caregiver_id: number;
    caregiver_name: string;
    field: string;
    old_value: string;
    new_value: string;
    corrected_at: string;
  }>;
};

const PATIENT = {
  user_id: 1,
  name: "Alex Rivera",
  preferred_name: "Alex",
  role: "primary",
  can_manage_profile: true,
  can_manage_people: true,
  can_manage_schedule: true,
  can_manage_objects: true,
  can_manage_notes: true,
};

async function fulfillJson(route: Route, payload: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: { "access-control-allow-origin": "*" },
    body: JSON.stringify(payload),
  });
}

async function routeCaregiver(page: Page, moments: Moment[], canManage = true) {
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
    if (url.pathname.endsWith("/corrections") && request.method() === "POST") {
      if (!canManage) {
        return fulfillJson(route, { detail: "Caregiver permission required." }, 403);
      }
      const body = request.postDataJSON() as { field: string; value: string };
      const target = moments[0];
      target.corrections = [
        {
          id: 1,
          memory_id: target.memory_id,
          caregiver_id: 1,
          caregiver_name: "Maya",
          field: body.field,
          old_value: target.object_location ?? target.description,
          new_value: body.value,
          corrected_at: "2026-09-25T12:30:00",
        },
        ...target.corrections,
      ];
      target.object_location = body.value;
      return fulfillJson(route, target, 201);
    }
    if (url.pathname.endsWith("/moments")) {
      return fulfillJson(route, moments);
    }
    if (url.pathname.endsWith("/patients")) {
      return fulfillJson(route, [
        { ...PATIENT, can_manage_objects: canManage, can_manage_notes: canManage },
      ]);
    }
    if (url.pathname.endsWith("/profile")) {
      return fulfillJson(route, {
        user_id: 1,
        preferred_name: "Alex",
        short_bio: null,
        home_context: null,
        response_style: null,
      });
    }
    return fulfillJson(route, []);
  });
}

function savedMoment(): Moment {
  return {
    memory_id: 7,
    recorded_at: "2026-09-25T11:05:00",
    location: "Kitchen",
    description: "Keys on the kitchen counter.",
    image_url: "/api/media/keys.jpg",
    object_name: "keys",
    object_location: "kitchen counter",
    corrections: [],
  };
}

async function openMoments(page: Page) {
  await page.goto("/caregiver");
  await page.getByRole("button", { name: "Alex" }).click();
  await page.getByRole("button", { name: "Saved moments" }).click();
}

test("a caregiver corrects a saved detail and the history records who changed it", async ({ page }) => {
  await routeCaregiver(page, [savedMoment()]);
  await openMoments(page);

  const moments = page.getByTestId("caregiver-moments");
  await expect(moments).toContainText("kitchen counter");
  await moments.getByLabel("Correct the recorded location").fill("hallway shelf");
  await moments.getByRole("button", { name: "Correct saved detail" }).click();

  await expect(page.getByRole("status")).toContainText("corrected");
  await expect(moments).toContainText("Caregiver corrected");
  await expect(moments).toContainText("hallway shelf");
  await expect(moments).toContainText("Maya");
  await expect(moments).toContainText("Observed");
});

test("a read-only caregiver cannot correct a saved detail", async ({ page }) => {
  await routeCaregiver(page, [savedMoment()], false);
  await openMoments(page);

  const moments = page.getByTestId("caregiver-moments");
  await expect(moments.getByRole("button", { name: "Correct saved detail" })).toBeDisabled();
});
