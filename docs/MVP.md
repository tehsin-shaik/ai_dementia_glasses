# MemoryCue MVP

## MVP Goal

Build a browser-based software prototype that explores how reviewed, saved context could support a future smart-glasses experience.

No physical glasses are required.

The MVP proves this loop:

```text
Capture an image
    -> review or edit the details
    -> save a structured record
    -> ask about it later
    -> return a grounded answer
```

The system should retrieve information that has been observed or explicitly provided. It should not invent personal information.

Stage 8 extends the reactive memory loop with a limited proactive loop:

```text
Evaluate stored patient context
    -> select one explainable cue
    -> show it only in an active, visible HUD
    -> acknowledge that presentation
    -> let the wearer dismiss or disable it
```

## Memory Creation

The prototype supports manual memory creation from an uploaded image and metadata. A user can provide an image, timestamp, location, description, optional activity, and optional object name such as `keys`.

Uploaded images are stored locally with generated filenames. When an object name is provided, the system creates an object observation linked to the memory. Later object questions use the newest matching observation.

When configured, the Stage 3 vision flow analyzes an uploaded image and proposes normalized description, location, activity, and visible objects. The user must review or edit those suggestions and explicitly save the memory. Analysis alone does not create a memory and the manual workflow remains available without AI credentials.

The current prototype accepts `.jpg`, `.jpeg`, `.png`, and `.webp` images up to 10 MB.

## Glasses Simulator

Stage 4 adds a browser-only webcam simulator. The user can start the camera, capture one frame, send that frame through the existing vision-analysis endpoint, review or edit the suggestions, and explicitly save it through the existing memory endpoint. Captured frames use the same image and retrieval flow as uploaded images.

Camera access normally requires `localhost` or HTTPS. The simulator does not request microphone access, continuously analyze video, record in the background, or capture frames automatically. The user must trigger each capture and save.

## Glasses-style Memory HUD

Stage 5 adds a wearer-facing HUD to the live camera view. While the webcam is active, the user can manually ask a custom question or choose one of three quick cues: recent activity, last-seen keys, or today's schedule. The HUD reuses the existing `/api/query` endpoint and displays its grounded answer without exposing source IDs in the wearer view.

The HUD supports idle, querying, result, unknown, and error states. A cue can be dismissed without stopping the camera. The manual HUD does not analyze video; Stage 8 adds a separate, low-frequency poll of stored context for proactive cues. Stage 7 adds a separate explicit face-recognition action.

## Voice, Answer Language, and Provenance

Stage 9 makes the HUD usable hands-free and makes grounding visible.

* **Voice in and out.** The wearer can press **Speak** to dictate one question through the browser Web Speech API, and answers are read aloud through speech synthesis. Dictation is a single explicit turn: there is no wake word, no background listening, and no audio is uploaded or stored. Browsers without Web Speech support keep the typed HUD and hide the voice controls.
* **Answer language.** An English/Arabic toggle sets the request language. Arabic answers are assembled from the same stored records with Arabic templates, so switching language never changes what the system claims to know. Arabic object words such as `مفاتيحي` map to the stored object names.
* **Provenance.** A result shows the records behind it: a human-readable label, the stored detail, and when it was recorded. An unknown result shows no sources and states that MemoryCue does not guess.

## Rewind Recent Moments

Stage 10 adds `GET /api/rewind` and a saved-moments strip on the wearer screen.

* **Saved moments only.** The strip shows the latest saved memories for the selected profile with their photo, description, full observation date and time, and where its photo came from, read from the source of the observation behind the memory: **Live capture** (`browser_camera`, `iphone_camera`, `meta_glasses`), **Uploaded photo** (`uploaded_image`, including the bundled demo scenes), **Saved photo** (`other` or unclear, such as migrated memories), or **Sample record** (no photo, the seeded demo rows). Nothing enters the strip before the wearer reviews and saves it.
* **Ten-minute recap.** **Rewind recent moments** summarizes at most three saved moments from the last ten minutes in chronological order. The recap names how many moments it covers and states that it is not continuous recording.
* **Empty window.** When nothing was saved in the window, the recap says so and offers **Show earlier saved moments**. Earlier moments are labelled as earlier, never described as recent.
* **Evidence.** Object answers carry the saved photo alongside the stored detail and observation time, and last-seen answers say `Last recorded` so they never imply an object is still there.

Rewind does not add background recording, continuous capture, or any new inference: it re-reads rows the wearer already saved.

## Caregiver Correction of Saved Details

Stage 11 lets a linked caregiver correct one saved detail and have the wearer's next answer reflect it.

* **Scope.** A **Saved moments** tab lists the profile's saved moments. A caregiver with `manage_objects` can correct a recorded object location or name; a caregiver with `manage_notes` can correct a short reviewed description. Viewer-only caregivers see the same records with every control disabled, and the backend rejects their corrections.
* **The original is kept.** A correction never rewrites the capture, its photo, or the time it was observed. Each change is stored as its own row with the caregiver, the correction time, and the old and new values, and is shown as **Caregiver corrected** beside the untouched observation time.
* **Corrections flow forward.** Object answers, provenance, and rewind recaps read the corrected value. A moved object is still recorded as a new observation, and retrieval picks the newest observation, so history is never rewritten to hide a move.

Correction is caregiver-initiated only. There is no automatic learning, no inference of what a record "should" say, and no deletion of saved moments.

## Time-anchored Recall, Second Vision Provider, and Durable Photos

Stage 12 adds three small capabilities identified while reviewing the OurLife reference project (see `docs/OURLIFE_REFERENCE.md`). All three are independent implementations inside MemoryCue's existing modules.

* **Time-anchored recall.** "What was I doing at 10 AM?" (or `ماذا كنت أفعل الساعة 10 صباحًا؟`) answers with the saved moment in progress at that time today: the latest saved moment at or up to 30 minutes before it. The answer states the saved moment's own time. No saved moment in that window, or an impossible time, returns the standard unknown answer.
* **Gemini as an alternative vision provider.** `VISION_PROVIDER` accepts `openai` or `gemini`. Exactly one provider is configured at a time, both use the same instructions, schema, and validation, and suggestions still require review before saving. Bundled demo scenes never call either provider.
* **Durable hosted photos.** With `MEDIA_STORAGE=database`, uploaded images are stored as rows in the configured database in the same transaction as the memory, so hosted photos survive serverless instance recycling. The default remains local files under `MEDIA_DIR`.

These do not add summaries generated by a model, background capture, wearable hardware, or WebSockets.

## Layered Memory: Observations, Events, and Episodes

Stage 13 places three layers beneath saved memories so the system can later accept continuous captures from any device. See `docs/MEMORY_ARCHITECTURE.md`.

* Every capture becomes an **Observation** tagged with its `source` (`browser_camera`, `iphone_camera`, `meta_glasses`, `uploaded_image`, or `other`). `POST /api/observations` accepts captures without review; `POST /api/memories` still saves reviewed moments, now through the same ingestion service.
* Deterministic rules turn observations into confidence-scored **Events** only when explicit evidence supports them; an observation may have none.
* Nearby events are grouped into **Episodes** after capture, never during it.
* Saved **Memories** keep their ids and behavior and link to the observations, events, and episode behind them.
* Existing memories are backfilled at startup without inventing end times, people, coordinates, or source hardware.
* "What did I do today?" lists today's saved moments in order.
* The browser camera is the first **CaptureSource**: each user-triggered capture is stored as an unreviewed `browser_camera` Observation with its capture time, and Save memory reviews that capture instead of uploading the photo again. Captures are never analyzed or saved as memories automatically.
* An unsaved capture is deleted with its photo once it is older than `OBSERVATION_RETENTION_HOURS` (default 168) and nothing saved depends on it. Reviewed data never expires. Cleanup runs for the capturing user after each capture; there is no cleanup endpoint or scheduler.

Spoken answers still use only reviewed records. Unreviewed observations and rule-inferred events are visible through `GET /api/observations`, `/api/events`, and `/api/episodes` with their confidence, but are never spoken as facts. Episode titles and summaries are templated from stored fields, not generated by a model. This stage adds no continuous recording, wearable hardware, vector database, or behavioral prediction.

## Proactive Context Cues

Stage 8 adds a small rule-based `CueEngine` behind `GET /api/cues`. The endpoint uses the current `X-MemoryCue-User-Id` and returns at most one current cue for that patient. Cues are normalized, explainable records with a source ID, priority, and optional expiration.

The current rules are deliberately narrow:

* `schedule_upcoming`: a same-day schedule item in the next 30 minutes by default;
* `recognized_person`: the latest successful explicit **Who is this?** event within a short window, using the stored `Person` name and relationship; and
* `important_object`: a caregiver-marked important object with a recent last-seen observation and a recent activity explicitly matching a leaving-related phrase.

Recognition cues have the highest priority, followed by schedule cues and then important-object cues. `GET /api/cues` evaluates and returns at most one cue without changing presentation state, so repeated polls and the demo inspector cannot consume it. Once the wearer HUD is active, visible, idle, and actually showing the cue, the client acknowledges it through `POST /api/cues/present`. That acknowledgement starts the patient-scoped configurable 20-minute cooldown. Repeating the same presentation ID is idempotent and does not extend the cooldown; a dismissal prevents that cue key from returning. The wearer can turn proactive polling off; manual questions, camera capture, and explicit face recognition remain available.

The cue engine never infers medical needs, medication compliance, emotion, confusion, distress, wandering, falls, or behavioral anomalies. It does not continuously inspect video or perform background face recognition. It evaluates stored context only.

## Development Identity and User Scoping

Stage 6A adds two deterministic local demo profiles, Alex and Jordan. The browser's **Demo profile** selector sends the selected user ID in the `X-MemoryCue-User-Id` header. Query answers, memory creation and listing, people, schedules, object observations, vision analysis, and media access are scoped to that user. Switching profiles clears visible answers and unsaved camera/form state.

This is explicit development identity only; it is not authentication or authorization. The demo seed resets both profiles and their data. Production identity, production caregiver authorization, consent, and permissions remain outside this MVP.

## Caregiver Profile Management

Stage 6B adds a small caregiver setup page at `/caregiver`. Development caregivers Maya, Sam, and Taylor are linked explicitly to patient users: Maya manages Alex, Sam manages Jordan, and Taylor can view Alex without modification permissions. The setup API supports patient profile preferences, text-only known people, important object definitions, schedule items, and short caregiver notes.

Caregiver requests use a separate `X-MemoryCue-Caregiver-Id` header and a centralized link/permission check. Caregivers can only view or modify data for linked patients, and mutations require the matching management permission. These records are the same `Person` and `ScheduleItem` data used by the wearer-facing retrieval system, so caregiver edits are visible in patient queries.

Important object definitions describe things a caregiver considers useful; they do not create `ObjectObservation` history. Profile bio, home context, and response style are stored but do not currently alter wearer answers or cues. Caregiver notes are stored for setup context and are not automatically included in answers, cues, or AI prompts. The caregiver identity mechanism is simulated and not production authentication; invitations, consent workflows, passwords, and production biometric security remain out of scope.

## Approved Known-Person Recognition

Stage 7 adds opt-in recognition for people already present in a patient's caregiver-managed `Person` records. A caregiver with `manage_people` permission uploads a reference image containing exactly one face. The local API converts it to a pretrained dlib 128-dimensional ResNet embedding through the `dlib-bin` runtime and `face-recognition-models` package, then stores only that derived embedding in a patient-scoped enrollment row.

The patient can then start the webcam and choose **Who is this?**. The simulator captures one frame and compares it only with enrolled people belonging to the selected patient. A configurable similarity threshold (`FACE_MATCH_THRESHOLD`, default `0.65`) and ambiguity margin (`FACE_MATCH_MARGIN`, default `0.08`) make larger-is-better scores conservative: weak or close matches return unknown. The name and relationship in a recognized cue are read from the stored `Person` record; they are never inferred from appearance.

This prototype has no global search, stranger or public-figure identification, internet lookup, auto-enrollment, continuous scanning, raw embedding API, cloud face provider, biometric authentication, or production security guarantees. No reference image is retained by the enrollment feature.

## Questions the MVP Must Answer

### 1. What was I doing?

Recall the user's most recent activity.

### 2. Where are my keys?

Return the last observed location of the keys.

The assistant must say:

> "I last saw your keys..."

rather than claiming the keys are definitely still there.

### 3. Who is Sarah?

Retrieve the deterministic demo's stored person record. A linked caregiver can update that text-only relationship through the setup page.

Example:

```text
Sarah
Relationship: Daughter
```

Camera-based **Who is this?** recognition is a separate Stage 7 flow and does not replace this text lookup.

### 4. What am I doing today?

Return the user's simple daily schedule.

### 5. What did I do today?

List today's saved moments in order, citing the episodes they belong to, or say it does not know when nothing was saved.

## MVP Demo Data

Eventually the demo should support scenes similar to:

```text
10:00 - Kitchen - making tea
10:10 - Living room - reading
10:18 - Kitchen - keys visible on counter
10:25 - Hallway - preparing to leave
```

Known person:

```text
Sarah
Relationship: daughter
```

Example schedule:

```text
10:30 - Walk
15:30 - Sarah visits
18:00 - Dinner
```

## Explicit MVP Non-Goals

The first MVP does not include:

- real Meta glasses integration;
- global or continuous face recognition;
- geofencing;
- emergency dispatch;
- medication confirmation;
- medical diagnosis;
- dementia diagnosis;
- voice cloning;
- wake words, background listening, or stored audio;
- machine translation of stored records;
- Meta Quest;
- continuous video recording;
- production authentication;
- complex RAG infrastructure;
- more than one simultaneously active AI provider, or AI-generated summaries of a day; or
- a mobile application.

These may be considered later. Stage 8 also does not include continuous autonomous monitoring, medical or medication reminders, push notifications, WebSockets, routine-learning models, or behavioral inference.
