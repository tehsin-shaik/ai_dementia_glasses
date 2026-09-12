# MemoryCue Current-State Audit

- **Audit date:** 12 September 2026
- **Repository:** `ai_dementia_glasses`
- **Branch / commit:** `main` at `27aac14298a60225b1989aeca8ed868ea1f43ca7`
- **Audit type:** read-only product audit with isolated test databases and media directories

## Executive assessment

MemoryCue is a credible, working local research prototype. It can demonstrate a complete reviewed-memory loop, deterministic retrieval, profile isolation, caregiver-managed context, explicit known-person checks, and three kinds of optional proactive cue. The homepage, wearer app, caregiver app, and development workspace now read as parts of one product rather than disconnected stage demos.

The statement “Stage 8 is implemented” is supported by the code. The stronger statement “Stage 8 is reliably complete” is not yet supported. Two reproducible defects need attention before that claim is used as a clean baseline:

1. Cue retrieval changes server state as part of a `GET`. In the running development app, two mount-time requests consumed a valid cue and then cleared it before it appeared. The demo workspace can also consume a wearer cue merely by inspecting it.
2. The caregiver detail guard does not version patient changes. With two linked profiles and one delayed response, the page showed Jordan’s heading with Alex’s profile fields.

The local prototype is suitable for a controlled demonstration with synthetic data. It is not ready for public deployment or real patient data. Header-selected identities are scoping aids, not authentication; the reset endpoint is unauthenticated and destructive; captured media and face embeddings have no production consent, retention, encryption, or deletion system.

## Repository state audited

| Item | Audited state |
|---|---|
| Branch | `main`, matching `origin/main` at audit time |
| HEAD | `27aac14298a60225b1989aeca8ed868ea1f43ca7` — `feat: add cinematic MemoryCue homepage intro` |
| Recent functional history | Stage 8 cues (`0825020`), responsive/content passes (`08ad5df`, `22aedf0`, `67a064a`), caregiver reliability/layout (`c856edd`), cinematic intro (`27aac14`) |
| Pre-existing worktree entry | `apps/web/app/layout.tsx`: uncommitted `data-scroll-behavior="smooth"` attribute on `<html>` |
| Generated worktree entry | `apps/web/next-env.d.ts`: reported modified by Git, but no textual diff at audit start or finish |
| Audit-created tracked file | `docs/AUDIT_CURRENT_STATE.md` only |
| Commits / pushes | None |

The production build temporarily changed `next-env.d.ts` from development to production generated type paths. Those two generated imports were restored to their exact audit-start values. The pre-existing `layout.tsx` change was not edited.

Applicable instructions and claims reviewed:

- `AGENTS.md` and `apps/web/AGENTS.md`
- `README.md`
- `docs/MVP.md`
- `docs/architecture.md`
- `docs/AUDIT_STAGE_1_TO_5.md`
- `docs/AUDIT_FRONTEND.md`
- `docs/CONTENT_REVIEW.md`

Earlier reports were treated as claims. One documentation inconsistency remains: `docs/AUDIT_FRONTEND.md` refers to both 74 and 64 backend tests. The current collected count is 74.

### Data protection

The running backend’s normal database was identified as:

`apps/api/memorycue.db`

With no environment override, the backend resolves `sqlite:///./memorycue.db` and `data/media` relative to the server working directory. Starting it from `apps/api` therefore selects the database above and `apps/api/data/media`. No normal media directory existed during this audit.

Before and after all testing, the normal database had the same:

- size: 184,320 bytes;
- modification time: `2026-09-09T09:33:13.482395Z`;
- row counts in all 13 application tables, including 8 memories, 2 users, 3 caregivers, 3 access links, and 0 cue states or face enrollments.

Every reset, upload, edit, permission, face, cue, and race test used a uniquely named directory below the operating-system temporary directory. Each temporary database/media directory was verified before mutation and removed afterward.

## Verified capability inventory

“Implemented” describes source state. “Verified” describes what this audit actually exercised; the two are intentionally separate.

| Capability | What the implementation actually does | Status | Verification | Requirements / limits |
|---|---|---|---|---|
| Image upload and memory creation | Accepts JPEG/PNG/WebP up to 10 MB, stores a UUID-named file, writes a patient-scoped memory and optional object observation, and removes the file on DB rollback | Implemented | Backend suite plus isolated live upload/save/media smoke | Extension and declared MIME are checked; actual image bytes are not decoded during memory save |
| Optional AI image analysis | Sends an explicit image to one configured OpenAI Responses API model using strict structured output and `store: false`; does not save the result | Implemented, optional | Mocked provider success/error tests; unconfigured-provider browser fallback verified | Real provider not configured or called; requires `VISION_PROVIDER`, `VISION_MODEL`, and `VISION_API_KEY` |
| Browser camera capture | Opens `getUserMedia`, displays a local preview, captures a scaled JPEG frame, and stops tracks on stop/unmount | Implemented | End-to-end fake-camera run reached `readyState=4` and captured a preview | Real laptop/mobile camera and permission UX not exercised |
| Review and save | Capture or upload opens editable timestamp, location, description, activity, and object fields; “Analyze” and “Save memory” remain separate actions | Implemented | Browser capture → failed optional analysis → manual edit → save succeeded | Saving requires timestamp, location, description, and an image |
| Recent activity retrieval | Returns the newest memory with a non-empty activity for the selected profile | Implemented | Backend tests | Deterministic exact-intent matcher, not open-ended language understanding |
| Last-seen object retrieval | Returns the latest patient-scoped keys observation ordered by observation time and ID, using “I last saw…” wording | Implemented | Backend tests and Alex/Jordan live queries | Typed query supports keys variants, not arbitrary configured objects |
| Person name / relationship lookup | `Who is Sarah?` returns the selected profile’s stored Sarah relationship | Partial | Backend tests, including patient scoping and caregiver update flow | Other typed names are not dynamically parsed; camera recognition is a separate path |
| Daily schedule retrieval | Returns same-day stored schedule items in time order | Implemented | Backend tests | Exact supported “today” question variants; server-local naive dates |
| Glasses-style HUD | Shows manual query states, recognition result/unknown states, and an optional proactive cue over an active camera preview | Implemented | Fake-camera browser walkthrough | No physical glasses or wearable display integration |
| Alex/Jordan isolation | Sends `X-MemoryCue-User-Id` on personal requests and scopes memories, media, observations, people, queries, recognition, and cues in the backend | Implemented | Backend isolation tests plus different live keys answers for Alex and Jordan | Header is user-selectable and not secure authentication |
| Caregiver identities and links | Maya lists Alex, Sam lists Jordan, and Taylor lists Alex from access-link rows | Implemented | Backend suite and browser switching | Fixed simulated IDs in frontend; no accounts, invitations, or consent workflow |
| Caregiver permissions | API distinguishes view, primary profile management, and people/schedule/object/note flags; unlinked access is hidden with 404 and denied mutation uses 403 | Implemented in API; partial in UI | Tests and a live Taylor profile edit returning 403 | UI receives no capability flags and leaves denied controls enabled |
| Profile fields | Stores preferred name, short bio, home context, and response style | Implemented storage | Caregiver load/save tests | Only preferred name is displayed in profile summaries; these fields do not change retrieval or cues |
| People | Patient-scoped create/update/delete; relationship powers Sarah lookup and recognized-person output | Implemented | Backend CRUD tests and isolated browser add | Typed lookup remains Sarah-specific |
| Important objects | Patient-scoped definitions mark objects eligible for proactive object cues | Implemented | Backend CRUD and cue tests | Definition is not a last-seen observation; notes are stored only |
| Schedules | Patient-scoped CRUD; data feeds today retrieval and upcoming cues | Implemented | Backend CRUD/query tests and controlled cue creation | Naive server-local timestamps |
| Caregiver notes | Patient-scoped add/list/delete with author caregiver ID | Implemented storage | Backend tests | Notes are not consumed by retrieval, vision, recognition, or cues |
| Face enrollment | Requires an existing person and people-management permission; extracts one local 128-value dlib embedding | Implemented | Mocked enrollment tests; local runtime loaded and rejected a blank image; browser no-face error verified | No suitable real face reference used |
| Face replace/remove | Replaces the one enrollment per person or deletes it; deleting a person removes enrollment/recognition records explicitly | Implemented | Backend tests | Derived embedding is stored; raw reference image is not retained |
| Camera recognition | Explicit button captures one frame, compares only the selected patient’s enrollments, and returns stored name/relationship only for a strong unambiguous match | Implemented | Mocked match/weak/ambiguous/scoping tests; no-enrollment browser unknown state | Accuracy on real people is unverified; no continuous scanning |
| Schedule cue | Eligible only from now through a configurable same-day lookahead (default 30 minutes) | Implemented | Controlled-time tests and browser display | Cue-delivery state bug described below |
| Recognition cue | Uses the most recent patient-scoped recognition event inside the default 10-minute window; optionally adds a same-day matching schedule | Implemented | Controlled mocked tests | Requires a successful prior explicit recognition event |
| Important-object cue | Requires an important-object definition, latest matching observation, a recent linked memory, observation no later than memory, and a leaving-activity phrase | Implemented | Controlled-time tests | Default lookback 30 minutes and narrow deterministic leaving phrases |
| Cue priority / one-at-a-time | Sorts recognition 100, schedule 50, object 25, then returns the first candidate | Implemented | Source review and backend tests | Selection and presentation are coupled in one state-changing GET |
| Cue cooldown / dismissal | Records `last_shown_at` for default 20-minute cooldown; dismissal persists for that cue ID | Implemented | Tests and isolated browser enable/disable/dismiss run | “Shown” currently means fetched, even if no HUD displayed |
| Cue expiration | Schedule expires at event time; recognition at recognition-window/event boundary; object at memory + lookback | Implemented | Source and controlled-time tests | Visible client cue can remain until the next render/poll, up to roughly 45 seconds |
| Cue enable/disable | Checkbox defaults on; off clears local cue and stops the polling effect; on polls immediately; manual questions clear the cue | Implemented | Isolated fake-camera browser run | Preference is in-memory only and resets on reload |
| Demo tools/reset | Lists/query profiles, inspects one cue/config, and globally deletes/recreates deterministic demo rows | Implemented | Reset and query exercised only on isolated DB | Endpoint is unauthenticated; reset replaces all application data in the selected DB |
| Homepage | Product-focused hero, four capability sections, caregiver CTA, final CTA, and candid draggable About section | Implemented | Source review and desktop/tablet/mobile visual inspection | Illustrative smart-glasses concept, not available hardware |
| Cinematic intro | 9.35-second CSS/React sequence, black start, three words, Skip/Escape, scroll lock, staged hero reveal, and reduced-motion bypass | Implemented | Five visual frames; Escape focus/scroll cleanup and reduced-motion bypass exercised | Plays on every homepage load; full duration delays navigation unless skipped |
| Responsive navigation/layouts | Desktop links become a 44px mobile menu; product/app/caregiver/demo layouts reflow; caregiver tabs horizontally scroll | Implemented | Measured at 1440, 900, and 390 CSS pixels | Chrome only; real touch and other engines unverified |

## Architecture and data-flow observations

### Main flows

| Flow | Trace |
|---|---|
| Capture and save | `GlassesSimulator` → scaled local JPEG in `camera.ts` → `WearerApp` editable form → `POST /api/memories` → media directory + `Memory` + optional `ObjectObservation` → success message |
| Optional analysis | Captured/uploaded file → `POST /api/vision/analyze` → configured `VisionAnalyzer` → validated `VisionAnalysis` → editable suggestions only; no database write |
| Retrieval | Selected demo profile → `X-MemoryCue-User-Id` → `POST /api/query` → deterministic intent in `query_service.py` → patient-scoped DB lookup → grounded answer/source IDs |
| Caregiver setup | Selected demo caregiver → `X-MemoryCue-Caregiver-Id` → centralized access check → profile/people/object/schedule/note routes → patient-scoped rows |
| Recognition | Active camera frame → `POST /api/face/recognize` → selected-patient enrollments → dlib comparison threshold/margin → stored name/relationship → recognition event on match |
| Proactive cue | Wearer/demo `GET /api/cues` → `CueEngine` evaluates three rule sets → priority/suppression → one cue → route records it presented immediately |

### Positive architecture findings

- Route, authorization, provider, storage, query, face, and cue responsibilities are separated enough for the current prototype.
- Pydantic request/response models constrain field lengths and response shapes.
- Personal routes derive patient identity from headers instead of trusting a patient ID in a memory payload.
- Media ownership returns 404 to another profile; traversal and unsupported served extensions are blocked.
- Foreign keys are enabled on every SQLite connection.
- Memory save handles the file/DB split carefully: a failed commit removes the newly written file.
- Vision output is schema-validated and kept reviewable. Capture and analysis do not create memories.
- Wearer query, vision, save, recognition, and cue paths use profile/request guards; profile switching cleared answers and unsaved captured data in the browser run.
- Camera tracks, polling intervals, and preview object URLs have explicit cleanup paths.
- Optional AI failure degrades to a clear manual workflow rather than blocking save.

### Concrete architecture inconsistencies

- The cue read route performs a write. `apps/api/app/cues/routes.py:19-29` evaluates and records presentation in the same GET request.
- Relative defaults in `apps/api/app/database.py:11` and `media_storage.py:26-27` make the selected database/media directory depend on backend working directory. This explains how a server can appear to have “missing” demo data while pointing at another new SQLite file.
- There is no migration system. Startup creates missing tables and has one bespoke `image_path` alteration; future changes to existing constraints/columns have no managed upgrade or rollback path.
- There is no request cancellation. Most wearer/demo responses have generation guards, but bandwidth/work continues. The caregiver patient-detail guard is incomplete and produces a real stale-data defect.
- `/demo` fetches five-memory data and a cue whenever the profile changes. The cue request is not observational because it consumes cooldown state.
- `globals.css` is 3,847 physical lines and contains repeated generations of wearer/demo/responsive rules. This is maintainability debt, not by itself a reason for a redesign.

### Which caregiver data affects behavior

| Data | Current consumer |
|---|---|
| Preferred name | Caregiver/profile labels only |
| Short bio | Stored only |
| Home context | Stored only |
| Response style | Stored only |
| Person name/relationship | Sarah typed lookup, face-recognition response, recognition cue |
| Important-object name | Important-object cue eligibility |
| Important-object notes | Stored only |
| Schedule title/time | Today retrieval, schedule cue, optional name-matched recognition cue context |
| Caregiver notes | Stored/listed only |

## Functional verification results

### Retrieval accuracy and uncertainty

- Alex and Jordan returned different patient-scoped keys answers (`kitchen counter` versus `bedroom desk`).
- Latest observation ordering, newest non-empty activity, same-day schedule ordering, and patient scoping passed backend tests.
- Object answers retain explicitly uncertain last-seen language.
- Unknown/unsupported questions return `I couldn't find matching saved information for that.` rather than synthesized personal details.
- Vision instructions explicitly prohibit inferred names, relationships, diagnoses, emotions, and hidden facts.
- The provider result remains editable, and capture/analyze remain separate from save.
- Wearer-facing answers hide intent and source IDs; those details are limited to hidden developer UI/demo diagnostics.
- The caregiver profile list now has distinct loading, failed/retry, and successful-empty branches. A controlled API response of `200 []` was distinguished from the browser-tested network failure.
- The demo page does not consistently make the same distinction; see F-05.

### Caregiver isolation and permissions

- Deterministic seed relationships were verified: Maya → Alex primary, Sam → Jordan primary, Taylor → Alex viewer.
- Unlinked data is returned as 404, and all mutation permissions are enforced server-side.
- Memories, observations/media, people, schedules, objects, notes, enrollments, recognition events, and cues are patient-scoped in tests.
- An isolated browser run added a person as Sam, rejected a blank enrollment image, and rejected Taylor’s profile save with 403.
- Switching wearer profiles cleared the old answer and captured-memory form while preserving an active camera stream. The next query used the newly selected profile.
- Simulated header identity is correctly labeled in the UI, but it must not be described as authentication.

### Face recognition

- Enrollment routes first require a linked patient, an existing patient-owned person, and `manage_people` permission.
- No-face, multiple-face, replacement, removal, embedding-hidden, weak-match, ambiguity-margin, and cross-patient tests passed.
- The installed dlib runtime and model files loaded successfully; a generated blank JPEG produced the expected `No usable face was found` in 1.1 seconds.
- A fake-camera “Who is this?” action with no enrollment returned the calm unknown HUD state.
- Raw enrollment photos and recognition frames are not stored by the face paths. The 128-value derived embedding is stored as JSON text in SQLite.
- No real face pair was available, so real-world accuracy, false-positive/negative behavior, demographic performance, and camera-lighting robustness remain unverified. Passing mocked vector comparisons is not evidence of recognition accuracy.
- Recognition is explicit per button press. There is no continuous scanning or automatic enrollment.

### Proactive cues

Controlled tests verified:

- same-day schedule inclusion inside and exclusion outside the lookahead;
- patient scoping;
- recognition window and stored relationship;
- no cue with insufficient context;
- important-object last-seen wording and leaving-activity requirement;
- priority ordering in source;
- one returned cue;
- cooldown and dismissal;
- browser enable, disable, display, dismiss, and manual-question clearing.

The corrected browser control run displayed three separately created schedule cues in turn, cleared one when the toggle was disabled, dismissed another through the HUD, and removed a third when a manual question was asked.

The delivery mechanism still has a high-impact flaw. A controlled development-mode load generated two immediate `GET /api/cues` requests. The first response marked a valid schedule cue presented; the second returned empty, and no HUD appeared. A separate two-consumer test returned a cue to the first GET and `[]` to an immediate second GET. This also means `/demo` can suppress the cue for `/app`, and polling while the camera is inactive can consume a cue the user never saw.

## Product walkthrough

### `/`

- The value proposition is understandable quickly: memory support, recent moments, last-seen items, familiar people, today’s schedule, and caregiver context.
- Both “Try MemoryCue” calls to action point to `/app`.
- Claims match the implementation when read with the About section. The About copy clearly says browser prototype, future glasses concept, optional AI, reviewed saves, and medical/caregiver limitations.
- The visual language is consistent with the other routes. No external intro asset can fail because the sequence is React/CSS only.

### Cinematic intro

- It begins on a black screen, expands an off-white stage, and displays the three large word phases before assembling the homepage.
- The 9.35-second duration blocks page interaction and scrolling, but Skip is visible, is a native button, and Escape works.
- Keyboard Escape removed the intro, restored scrolling, and focused `.homepage-content`.
- `prefers-reduced-motion: reduce` bypassed the intro immediately with no hidden content or scroll lock.
- At 390px it remains bounded with no document overflow.
- The sequence is all code and adds no network/asset payload. Its main cost is intentional time-to-content, not download size.
- The `001`/`002`/`003` markers are implemented in black, but their `0.8rem–1rem` size is visually easy to miss against the oversized words.

### `/app`

- Fake camera start, capture, recognition unknown, review, manual edit, save, retrieval, stop, and profile switch all worked.
- With no provider configured, Analyze returned: `Vision analysis is not configured. You can still complete the form manually.`
- A saved notebook observation produced the expected success message; keys retrieval remained grounded in the latest keys observation.
- Optional cues worked once delivered; initial delivery is affected by F-01.

### `/caregiver`

- Linked profiles, tabs, profile fields, people, objects, schedules, notes, and face controls are present and visually organized.
- Failure and retry were exercised; retry recovered Alex. Sam loaded Jordan. Taylor’s unauthorized save was blocked by the API.
- Successful empty API behavior was separately verified with an isolated caregiver whose link was removed.
- Face enrollment rows are aligned on desktop and stack cleanly on mobile.
- A multi-patient delayed-response run reproduced F-02.

### `/demo`

- The destructive scope is explicit: “Reset all data and load demo” and “This action replaces all prototype data.”
- Reset was run only against an isolated database and restored the documented sample counts.
- Query and API URL/identity diagnostics are accurate. Vision status correctly says it is not verified there and needs a configured provider.
- Cue inspection is not passive, uploaded thumbnails cannot authenticate, and HTTP error/empty presentation needs correction.

## UX, responsive, and accessibility findings

### Manual visual inspection

Headless Chrome 152 screenshots were inspected after actual page rendering at 1440, 900, and emulated 390 CSS-pixel widths. A separate set of intro frames covered black start, word/stage phases, and full-stage transition.

- All four routes measured `document.scrollWidth === clientWidth` at all three widths.
- Homepage hero/cards reflowed cleanly; no headline or CTA clipping was observed.
- Mobile navigation is discoverable as a labeled 44px “Menu” button.
- App camera/HUD and form controls remain inside the 390px viewport.
- Caregiver forms become one column. Tabs intentionally extend inside a horizontal scroll region without creating page overflow.
- Demo query buttons and cards wrap into a usable single-column flow.
- The four routes share navigation, palette, typography, controls, radii, and explanatory tone. `/demo` is appropriately identified as development tooling.
- F-07 records the small mobile camera-heading and copy-spacing defects.

### Automated DOM/accessibility evidence

A lightweight rendered-DOM audit was run on every route. It is not a substitute for axe, Lighthouse, or assistive-technology testing.

- Every route had one main landmark.
- No duplicate IDs, unnamed visible controls, or images missing an `alt` attribute were detected.
- Heading order was coherent at the rendered state inspected.
- Global `:focus-visible` styling provides a 3px outline for links, buttons, inputs, selects, textareas, and summaries.
- Native labels or ARIA labels are present on forms and custom controls.
- Some navigation/footer text links render below 24px in height, but they are ordinary inline-link exceptions rather than overlapping targets. The optional-cue checkbox itself is 16px; its surrounding label is clickable.

### Source-reviewed accessibility and unverified areas

- Mobile menu focus moves to the first link and Escape returns focus to the trigger; it is a disclosure menu, not a modal trap.
- The intro makes underlying content inert/hidden while active and supports pointer, touch, keyboard activation, Escape, and reduced motion.
- Draggable About windows use pointer events for mouse/touch, pointer capture, clamping, front stacking, and text-selection suppression. Their title bars are exposed as “Drag … window” buttons, but keyboard Enter/Space only brings a window forward; keyboard users cannot reposition it.
- Formal color-contrast scanning, screen-reader announcements, switch control, browser zoom/reflow, real touch dragging, and Safari/Firefox behavior were not tested.

## Actionable findings

### Reproducible defects

#### F-01 — High — Cue reads can consume and suppress unseen cues

- **Area/source:** `apps/api/app/cues/routes.py:19-29`, `apps/web/app/WearerApp.tsx:221-258`, `apps/web/app/GlassesSimulator.tsx`, and `apps/web/app/demo/page.tsx:133-154`.
- **Observed:** `GET /api/cues` writes `last_shown_at`. In development, mount produced two GETs: the first consumed the cue and the second cleared it. A first/second consumer trace returned one schedule cue then an immediate empty result. `/demo` uses the same endpoint. Wearer polling runs even with the camera inactive, although proactive HUD display requires an active stream.
- **Impact:** A valid cue may never be shown, may disappear before camera start, or may be suppressed for the default 20-minute cooldown by the demo inspector.
- **Reproduction:** Create a schedule 10 minutes ahead in isolated data, load `/app` in Next development mode, and inspect two GETs/no HUD; alternatively call `/api/cues` twice with the same profile.
- **Smallest fix:** Make evaluation/peek read-only and acknowledge presentation in a separate POST only when the HUD actually renders. Deduplicate the mount poll and keep demo inspection non-mutating.

#### F-02 — High — Late caregiver response can put one patient’s data under another heading

- **Area/source:** `apps/web/app/caregiver/page.tsx:264-322` and patient selection near `:990`.
- **Observed:** The detail effect captures `requestVersionRef.current`, but selecting another patient does not increment it. In a controlled Maya-with-two-profiles run, Jordan first loaded as `preferred_name=Jordan`; releasing one delayed Alex request then produced heading `Jordan's setup` with preferred name `Alex`.
- **Impact:** A multi-profile caregiver can view or edit stale data while believing it belongs to the selected patient. This is both integrity and privacy risk.
- **Reproduction:** Give one caregiver two links, hold one `/patients/1/notes` response, select patient 2, then release the held response.
- **Smallest fix:** Version or abort every detail load by both caregiver and patient ID, clear previous detail data on patient selection, and verify both IDs before applying all five responses.

#### F-03 — Medium — Uploaded memory thumbnails fail in the demo

- **Area/source:** `apps/web/app/demo/page.tsx:337` and authenticated media route `apps/api/app/main.py:220`.
- **Observed:** The demo renders `image_url` directly in `<img>`. Browser image requests cannot attach `X-MemoryCue-User-Id`; the isolated end-to-end run logged `GET /api/media/[file] 401 Unauthorized` after a successful upload.
- **Impact:** Uploaded memories appear in the list, but their images are broken, weakening the developer verification path.
- **Reproduction:** Save an uploaded/camera memory, open `/demo`, and inspect the media request.
- **Smallest fix:** Fetch media with `memoryCueFetch`, render a temporary object URL, and revoke it on replacement/unmount; or expose a narrowly scoped authenticated media delivery mechanism.

#### F-04 — Medium — Read-only caregiver permissions are enforced only after interaction

- **Area/source:** `PatientSummary` in `apps/api/app/schemas.py:38`, access flags in `models.py:48-51`, and unconditional caregiver forms.
- **Observed:** Taylor sees enabled profile and management controls. Clicking Save returns `Caregiver permission required.` The API correctly preserves data, but the frontend cannot know capabilities because the list response omits them.
- **Impact:** Viewer experience is confusing and repeatedly invites actions that can never succeed.
- **Reproduction:** Select Taylor and submit Save profile.
- **Smallest fix:** Include the existing role/capabilities in the linked-profile response and disable or hide unsupported mutations while retaining readable data.

#### F-05 — Medium — Demo HTTP failures can be presented as successful empty states

- **Area/source:** `apps/web/app/demo/page.tsx:118-154`, with empty copy at `:342` and `:361`.
- **Observed:** `refreshMemories` and `refreshCues` return silently for non-2xx HTTP responses. The page can retain stale data or say “No memories returned” / “No eligible cue” without an error. Network exceptions are handled more clearly than HTTP errors.
- **Impact:** The development workspace can misdiagnose identity, backend, or server failures as absent data/context.
- **Reproduction:** Return 401/500 from either endpoint without terminating the connection.
- **Smallest fix:** Throw parsed API errors for non-2xx responses and render explicit loading, successful-empty, and failed/retry branches.

#### F-06 — Low — Memory upload accepts non-image bytes

- **Area/source:** `apps/api/app/media_storage.py:39-91`.
- **Observed:** A file named `fake.png`, declared `image/png`, containing `not actually an image` was accepted with 201 and served as `image/png` with 200.
- **Impact:** Corrupt or disguised files can become saved memory media and later fail previews/analysis.
- **Reproduction:** Upload arbitrary bytes with an allowed extension and matching declared MIME.
- **Smallest fix:** Decode and verify the image before saving, reject malformed content, and retain current size/extension limits.

#### F-07 — Low — Two mobile wearer presentation defects

- **Area/source:** high-specificity `align-items: end` at `apps/web/app/globals.css:842`, generic mobile flex rule at `:2370`, and JSX split at `apps/web/app/GlassesSimulator.tsx:282-283`.
- **Observed:** At 390px, “Live camera / Live view” aligns to the right while its helper remains left-aligned. Rendered copy joins `Who is this?checks` without a space.
- **Impact:** Small but visible polish regression in the primary experience.
- **Reproduction:** Open `/app` at 390px.
- **Smallest fix:** Override the mobile heading to `align-items: flex-start` and insert an explicit JSX space after `</strong>`.

### Expected prototype limitations / public-deployment blockers

These are not regressions against the stated local-demo scope, but they become blockers if Stage 9 introduces accounts, pilots, remote access, or real personal data.

| Severity in public use | Limitation | Evidence / impact | Smallest next decision or control |
|---|---|---|---|
| Blocker | Simulated identity, no authentication | Any caller can select a user/caregiver ID header; CORS is not an authorization boundary | Define account/session authentication, caregiver-patient authorization, consent, and audit requirements before public scope |
| Blocker | Unauthenticated global reset | `POST /api/demo/seed` deletes all application rows in the configured DB | Development-only route gating or exclusion from production |
| Blocker | Sensitive-data lifecycle absent | Uploaded first-person images persist on disk; face embeddings and context persist in SQLite; no user deletion, retention, encryption-at-rest, backup, or audit policy | Define data classification/consent/retention/deletion and threat model before real data |
| High | No medical/assistive reliability guarantees | No clinical validation, human-factors study, escalation behavior, offline behavior, or false-cue safety analysis | Keep explicit prototype disclaimer and define intended-use/risk process before any care claim |
| Medium | Relative DB/media paths | Starting from another working directory can silently select another database/media tree | Require explicit absolute paths outside disposable local demo use and log the resolved paths at startup |
| Medium | No security-header policy | Live frontend/API responses had no CSP, frame, content-type, referrer, permissions, or opener policy headers | Add a deployment-specific header baseline when a hosted environment exists |
| Medium | Server-local naive timestamps | Schedule, cue, and upload semantics assume server and user share a timezone | Define timezone storage/display rules before multi-device or remote deployment |

### Usability and engineering improvements

- Add frontend integration tests. Current regressions are concentrated in client effects, race handling, authenticated media rendering, and responsive composition—the areas not covered by the backend suite.
- Add a frontend lint script and a real automated accessibility check. Neither exists now.
- Add AbortController cleanup where requests can become stale; guards should still validate selected identity before applying results.
- Consolidate repeated CSS only as a bounded maintenance task after behavior has test coverage.
- Consider enlarging the intro index markers and adding keyboard repositioning or non-interactive semantics for draggable window title bars.

## Identity, permissions, privacy, and data-integrity findings

- API scoping is materially better than client-only filtering: ownership and caregiver access are checked in the database for every protected route.
- The app consistently labels Alex/Jordan and Maya/Sam/Taylor as simulated identities.
- Unauthorized media and unlinked caregiver records use 404, limiting cross-profile existence disclosure.
- Face API responses never expose embeddings.
- Enrollment photos, recognition frames, and vision-analysis images are temporary in those respective paths. Saved-memory images intentionally persist.
- The external vision request is explicit, uses strict instructions/schema, and asks the provider not to store the response. Real provider contractual/data-location behavior was not audited.
- A face embedding is sensitive derived biometric data even though the original photo is discarded. It is plain text in the local SQLite file.
- Caregiver profile fields and notes can contain sensitive context but currently have no field-level purpose/retention enforcement.
- The reset button’s UI warning is strong, but the API itself has no environment gate.

## Dependency and runtime results

| Check | Command / method | Result |
|---|---|---|
| Backend collection | `apps/api/.venv/Scripts/python.exe -m pytest --collect-only -q` | 74 tests collected |
| Backend suite | `apps/api/.venv/Scripts/python.exe -m pytest -q` | **74 passed** in 134.55s; 2 deprecation warnings |
| TypeScript | `apps/web/node_modules/.bin/tsc.cmd --noEmit` | Passed; generated `tsconfig.tsbuildinfo` removed afterward |
| Production build | `npm.cmd run build` | Passed; all four routes plus not-found statically generated. First sandboxed attempt compiled but hit `spawn EPERM`; permitted rerun completed |
| Frontend lint | Script inventory | Unavailable: no `lint` script or lint dependency |
| Frontend tests | Script/file inventory | Unavailable: no frontend test script or test suite |
| npm vulnerabilities | `npm.cmd audit --audit-level=low` | 0 vulnerabilities reported |
| Node dependency tree | `npm.cmd ls --depth=0` | Declared packages resolved; local `@emnapi/runtime` and `@img/sharp-wasm32` reported extraneous, not manifest dependencies |
| Python compatibility | `apps/api/.venv/Scripts/python.exe -m pip check` | No broken requirements |
| Python vulnerability scan | Tool inventory | Not run; `pip check` checks compatibility, not known vulnerabilities, and no audit tool is installed |
| Live API smoke | Isolated Uvicorn on temporary DB/media | Health, CORS, seed, list, query, upload, owned/cross-profile media, caregiver list, permission denial, unknown identity, and cue response passed |
| Route smoke | Running local Next app | `/`, `/app`, `/caregiver`, `/demo` returned/rendered successfully |
| Responsive render | Chrome device emulation | No document overflow at 1440/900/390 on all routes |
| Whitespace | `git diff --check` | Passed; only line-ending conversion warnings on pre-existing modified files |

Backend warnings:

- FastAPI’s TestClient compatibility layer warns that the current `httpx` path is deprecated in favor of `httpx2`.
- Starlette warns that the `anyio.abc.BlockingPortal` alias is deprecated.

These warnings do not fail current tests, but dependency upgrades should be tested rather than assumed safe.

## Existing prototype limitations

- Software-only browser simulation; no Meta glasses integration, wearable SDK, open-ear audio, or wearable display.
- Deterministic query matcher with a narrow phrase set, keys-specific object question, and Sarah-specific typed person question.
- No speech input/output.
- No continuous capture, background observation, continuous face scanning, or automatic memory creation.
- One local embedding per known person; no enrollment quality score, liveness, anti-spoofing, or accuracy calibration workflow.
- One local SQLite database and filesystem media store; no multi-process deployment design, backups, encryption, quotas, or retention.
- No real account, invitation, consent, revocation, emergency, clinical, analytics, or audit-log system.
- Profile bio/home/style and caregiver notes are stored but do not personalize answers.
- Cue preferences do not persist and cue rules use narrow configured windows/phrases.
- No frontend test suite, lint gate, formal accessibility scan, or cross-browser matrix.

## Unverified or blocked checks

| Check | Status | Reason |
|---|---|---|
| Real OpenAI image analysis | Unverified | No provider credentials/model were configured; only mocks and the manual fallback were exercised |
| AI factual quality on varied images | Unverified | Would require a configured provider and representative, consented image set |
| Real face recognition accuracy | Unverified | No suitable enrolled/matching real face images; mocks validate logic, not model accuracy |
| Multiple real faces/no-face camera conditions | Partially verified | Mocked tests and generated blank image only |
| Physical camera permission/device behavior | Unverified | Browser walkthrough used Chrome’s fake camera |
| Physical mobile/touch behavior | Source-reviewed only | No real phone/tablet used |
| Screen-reader behavior | Unverified | No NVDA/VoiceOver session |
| Formal contrast/accessibility score | Unverified | No axe/Lighthouse accessibility runner is installed |
| Safari/Firefox | Unverified | Chrome 152 only |
| Long-running polling, background tabs, reconnect, offline mode | Unverified | Short controlled sessions only |
| Performance with large memory/face/caregiver datasets | Unverified | Deterministic sample data only |
| Production security/privacy posture | Unverified and currently out of scope | No deployment/auth/data-governance design exists |

## Prioritized next actions

At most five immediate actions are recommended before treating this repository as the baseline for Stage 9:

1. **Fix cue delivery semantics (F-01).** Separate read/peek from presented acknowledgement, prevent duplicate mount consumption, and ensure `/demo` cannot suppress wearer delivery.
2. **Fix caregiver patient-switch isolation (F-02).** Abort/version all five detail requests by caregiver + patient and test the delayed-response case.
3. **Define the Stage 9 trust boundary before feature scope.** Decide whether Stage 9 remains synthetic/local. If it introduces hosting or real people, authentication, consent, reset gating, media/biometric lifecycle, and timezone rules precede new product capability.
4. **Repair the verification surfaces.** Fix authenticated demo thumbnails (F-03), distinct demo HTTP error/empty states (F-05), and permission-aware Taylor controls (F-04).
5. **Add a focused frontend quality gate.** Cover cue delivery, caregiver race, media rendering, profile clearing, intro Skip/reduced motion, and 390px layout; then include lint and automated accessibility checks. Fold F-07 into this small pass.

F-06, CSS consolidation, intro marker sizing, full cross-browser coverage, and keyboard window repositioning can wait unless Stage 9 directly depends on them.

## Readiness to define Stage 9

Stage 8 has enough implemented surface area to inform Stage 9 planning, but it should not be declared a clean reliability baseline yet. Fix F-01 and F-02 first, then rerun the focused Stage 8 acceptance paths. Stage 9 planning must explicitly choose between:

- a continued local/synthetic research prototype, where the current identity and storage limitations can remain clearly labeled; or
- a hosted or real-user system, where authentication, consent, privacy, retention, deletion, auditability, and safety become foundational work rather than later polish.

Adding more AI or wearable capability before that choice would make the system broader without making its current guarantees clearer.

## Six concise answers

1. **What can MemoryCue reliably demonstrate today?** A synthetic local flow from browser capture/upload through review/save to grounded activity, keys, Sarah, and schedule retrieval; caregiver-managed context; explicit known-person checks; and controlled optional cue rules.
2. **Which important capabilities remain unverified?** Real AI vision quality, real face-recognition accuracy, physical camera/mobile behavior, screen readers, non-Chrome browsers, long-running polling, scale, and any production security/privacy behavior.
3. **What are the most consequential current problems?** Cue delivery can suppress unseen cues, and delayed caregiver responses can cross patient presentation boundaries. Secure identity/data lifecycle is absent by design and blocks public or real-data use.
4. **Does the product feel coherent across its routes?** Yes. The visual system, navigation, tone, disclosures, and core vocabulary are cohesive; `/demo` appropriately feels more technical.
5. **What should be fixed before defining Stage 9?** F-01 and F-02, followed by demo media/error reliability and a small frontend regression suite. Also decide whether Stage 9 remains local/synthetic or requires production trust controls.
6. **What can reasonably wait?** Large CSS cleanup, broader question understanding, physical wearable integration, speech, persisted preferences, intro marker polish, and cross-browser expansion—unless one becomes an explicit Stage 9 objective.
