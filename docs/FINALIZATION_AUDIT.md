# Finalization Audit

Scope: harden the existing MemoryCue prototype before any wearable client. No new storage, hardware, authentication, or product surface was added.

## Overall Status

**Prototype needs targeted fixes.**

The backend and data model are stable and every defect found in this pass was fixed and tested. Two targeted items remain before calling it ready: one high-severity npm audit finding in a transitive build dependency (`source-map-js`, fix published three days before this audit and not yet adopted under the seven-day dependency rule), and real-hardware validation (camera, microphone, human speakers) that has never been done.

## What Improved

| Area | Change | Where |
| --- | --- | --- |
| Intent routing | Added `time_anchored_activity` and `today_recall` (renamed from `day_summary`). "today" alone no longer means schedule; yes/no questions ("Did I take my medicine today?") and obligation/future wording ("What was I supposed to do?", "What should I do next?") return unknown instead of the latest activity or the schedule. | `apps/api/app/query_service.py`, `schemas.py` |
| Grounded wording | Activity answers always state the saved moment's own time ("Your last saved moment, at 10:25 AM: preparing to leave.", "The closest saved moment before 10:12 AM was at 10:10 AM: reading."). Stored text is quoted after a colon, removing sentences like "you were keys visible on kitchen counter". | `query_service.py` |
| Upload safety | Uploaded bytes must match the JPEG/PNG/WebP signature of their extension. | `media_storage.py` |
| Vision robustness | Provider output is normalized: blank fields become null, objects below 0.4 confidence dropped, duplicates merged, sorted by confidence. The wearer form only prefills an object at 0.6 confidence or above. | `vision/schemas.py`, `WearerApp.tsx` |
| Face uncertainty | Several photos of one person count as one candidate, so the ambiguity margin is measured only against a different person. Unknown results carry an `outcome` (`no_enrollment`, `no_face`, `multiple_faces`, `low_confidence`, `ambiguous`) and the HUD shows an outcome-specific message without a score. `?diagnostics=true` returns scores, threshold, and margin for development only; embeddings are never returned. | `face/service.py`, `face/routes.py`, `WearerApp.tsx` |
| Cue quality | Recognition cue IDs are per event, so the cooldown never applied and the same person was cued repeatedly. A recognition cue is now suppressed while another recognition of the same person was shown or dismissed within the cooldown. | `cues/service.py` |
| Race safety | `/app` drops a typed answer superseded by a newer question and an AI analysis superseded by a newer image or a discarded capture; a demo photo fetched before a profile switch is ignored. | `WearerApp.tsx` |
| 3D experience | The counter pan and "Last recorded" marker only appear when the real answer names the counter. Before, keys saved elsewhere in `/app` were answered correctly but the scene still pointed at the counter. | `experience/ExperienceWalkthrough.tsx`, `steps.ts` |
| Demo mobile layout | `/demo` cards no longer overflow a 390 px screen. | `globals.css` |
| Rewind wording | A one-moment recap reads "This is 1 saved moment" instead of "These are 1 saved moment". | `rewind_service.py` |
| Dependencies | Next.js 16.3.4 to 16.3.6 (critical advisory). | `apps/web/package.json` |
| Evaluation | 21 deterministic scenarios in `tests/evaluation/scenarios.json`, checked by `apps/api/tests/test_evaluation.py` (intent, source IDs, required and forbidden phrases, unknown answers have zero sources and evidence). No LLM judge. | |
| Docs | `MVP.md`, `MEMORY_ARCHITECTURE.md`, and `architecture.md` updated for the new intents, wording, face outcomes, diagnostics, cue suppression, and vision normalization. | `docs/` |

## Current Capabilities

Only what the code supports today:

* Two seeded demo patients (Alex, Jordan) and caregiver Maya, scoped by development headers (`X-MemoryCue-User-Id`, `X-MemoryCue-Caregiver-Id`).
* Image upload or browser camera frame, optional provider vision analysis (OpenAI or Gemini) or deterministic analysis for bundled scenes, user review, explicit Save into Observation, Event, Episode, and reviewed Memory.
* `/api/query` in English and Arabic: recent activity, time-anchored activity (numeric and spoken English/Arabic times), today recall, object location, person lookup, schedule, and unknown.
* Rewind of recent saved moments with provenance labels and caregiver correction history.
* Caregiver setup of profile, people, schedule, important objects, notes, corrections, and face enrollment.
* Opt-in face recognition against enrolled people of the selected patient only.
* Rule-based proactive cues (schedule, recognized person, important object) with presentation acknowledgement and cooldown.
* Browser speech input (Web Speech API) and spoken answers.
* `/experience`, a Three.js first-person walkthrough that calls the real `/api/query`.
* SQLite locally, Postgres when `DATABASE_URL` is set; cleanup of abandoned unreviewed captures.

## Remaining Limitations

### Unverified

* Real camera, real microphone, and human speakers (all tests used synthetic frames and synthetic or scripted speech).
* Arabic recognition with real speakers and dialects; Edge, Safari, iOS, and Android speech.
* Face recognition quality on real people, lighting, and angles; only synthetic images were matched.
* Vision provider quality on real scenes; provider calls were not part of the automated suite.
* Behaviour in noisy rooms, background tabs, and slow networks.

### Prototype-only

* Header identity is development scoping, not authentication. RLS on Supabase was enabled manually and new tables need the same SQL.
* Timestamps are naive local wall-clock times; time-anchored questions only cover today.
* Arabic answers can contain English stored text (for example a location typed in English); Arabic name lookup does not match names stored in Latin letters.
* Keyword intent rules: phrasing outside the tested set may return unknown.
* `/api/demo/seed` resets both demo profiles without scoping.
* The wearer `/app` disables Ask while a question is loading, so the superseded-answer guard is defensive and only exercised through voice and HUD paths.
* `npm audit`: one high advisory in `source-map-js` 1.2.1 (via PostCSS, build time). The fixed 1.2.2 was published 2026-09-30.
* No lint script in `apps/web`; no Python linter configured in the repo.

### Future production work

* Real authentication and authorization, audit logging, encryption, and consent flows.
* Timezone-aware storage and multi-day recall.
* Wearable capture clients (iPhone, Meta glasses) through the existing capture source.
* Clinical validation; MemoryCue makes no medical or diagnostic claims.

## AI Quality

* **Vision:** output is schema-validated and normalized; deterministic for bundled scenes. Real-scene quality of the providers was not measured.
* **Retrieval:** deterministic and covered by the 21 evaluation scenarios plus unit and API tests on seeded data.
* **Grounding:** unknown questions return zero sources and zero evidence across the evaluation set; unreviewed observations and inferred events are excluded from answers, Rewind, and provenance (architecture tests, including Postgres).
* **Recognition:** threshold and margin logic covered by unit tests (same-person photos, cross-person ambiguity, each unknown outcome); one synthetic dlib match verified in the browser walkthrough. No real-world accuracy figure exists.
* **Voice:** state machine, errors, and profile-switch cancellation covered by scripted browser tests; real Chromium recognition was earlier confirmed with synthetic audio only.

## Demo Readiness

**Yes, with synthetic inputs.** The Phase 25 story was run in a browser against the real FastAPI and Next servers with an isolated database, a synthetic camera, and a synthetic face image:

| Step | Result |
| --- | --- |
| Maya configures Alex: Sarah (daughter), keys object, a visit about 15 minutes ahead | Pass |
| Sarah enrolled (real dlib embedding of a synthetic portrait) | Pass |
| Keys scene captured, analyzed, reviewed, explicitly saved | Pass |
| "Who is this?" shows Sarah / Your daughter; a blank frame shows "I couldn't see a face clearly..." with no score | Pass |
| "Where are my keys?" → "Last recorded: your keys on the Table at 5:34 PM." with a source | Pass |
| "What was I doing?" → "Your last saved moment, at 5:34 PM: Preparing to leave." | Pass |
| "What did my doctor say?", "Did I take my medicine today?" → unknown, no sources | Pass |
| Schedule cue appears in the HUD | Pass |
| Rewind shows saved moments with provenance labels and the singular recap | Pass |
| Delayed Alex query and Rewind responses never render after switching to Jordan | Pass |
| `/experience` keys and wallet answers, English and Arabic at 390 px | Pass after fix (counter marker) |
| `/`, `/app`, `/caregiver`, `/demo`, `/experience` at desktop and 390 px | Pass after fix (`/demo` cards clipped on phones) |

Two defects were found during the walkthrough and fixed with regression tests: the 3D scene pointed at the counter for keys saved elsewhere, and `/demo` cards overflowed a 390 px screen because the single-column grid used `1fr` instead of `minmax(0, 1fr)`. Not covered: a physical camera or microphone, real speech recognition, audible spoken answers, and unfamiliar, ambiguous, or multiple-face cases in the browser (those outcomes are covered by API tests).

## Wearable Integration Readiness

**Yes, for the backend and data architecture.** Captures already enter through one path (image plus metadata to an unreviewed Observation, then explicit review into a Memory), media ownership is checked per patient, upload bytes are validated, and every answer surface reads only reviewed records. A future iPhone or glasses client can post the same capture payload without schema changes. It is **not** ready for real users: identity is header-based, timestamps are not timezone-aware, and no hardware camera or microphone has been tested.

## Acceptance Criteria

| # | Criterion | Status |
| --- | --- | --- |
| 1 | Existing functionality preserved | Met: existing tests pass; changed expectations only where the API contract intentionally changed (intent names, timestamped wording, valid image bytes, face outcome fields). |
| 2 | Critical reliability bugs fixed | Met: every defect found in this pass is fixed with a test. |
| 3 | Memory grounding consistent | Met (evaluation scenarios, architecture tests). |
| 4 | Profile/caregiver isolation preserved | Met (existing isolation tests, browser profile-switch races). |
| 5 | Query intent edge cases tested | Met (`test_finalization.py`, evaluation scenarios). |
| 6 | Face unknown/ambiguity tested | Met (unit and API tests). |
| 7 | Cue delivery reliable | Met (per-person cooldown test, existing cue tests). |
| 8 | Voice/profile races covered | Met (existing voice browser tests). |
| 9 | 3D experience stable | Met (browser tests, counter-marker fix). |
| 10 | Mobile UX reviewed | Met at 390 px on all five pages in the walkthrough. |
| 11 | Visual system coherent | Met: one mobile overflow on `/demo` fixed; no redesign. |
| 12 | Documentation matches implementation | Met for the changed behaviour. |
| 13 | Evaluation fixtures exist | Met. |
| 14 | Backend tests pass | Met: 319 passed, 7 skipped on SQLite; the 7 Postgres tests pass against Postgres 16. |
| 15 | Browser/e2e tests pass | Met: 47 Playwright tests pass. |
| 16 | Frontend build passes | Met. |
| 17 | TypeScript passes | Met. |
| 18 | Dependency audits pass | Partly: `pip check` clean; `npm audit` has 1 high (`source-map-js`), critical resolved. |
| 19 | No secrets or personal data committed | Met (diff reviewed). |
| 20 | No wearable integration added | Met. |
| 21 | Finalization audit created | Met (this file). |
