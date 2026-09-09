# AI Dementia Glasses MVP

## MVP Goal

Build a software-only prototype of AI-assisted memory glasses.

No physical glasses are required.

The MVP proves this loop:

```text
Observe something
    -> turn it into a memory
    -> store it
    -> ask about it later
    -> return a grounded answer
```

The system should retrieve information that has been observed or explicitly provided. It should not invent personal information.

Stage 8 extends the reactive memory loop with a limited proactive loop:

```text
Evaluate stored patient context
    -> select one explainable cue
    -> show it calmly
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

## Proactive Context Cues

Stage 8 adds a small rule-based `CueEngine` behind `GET /api/cues`. The endpoint uses the current `X-MemoryCue-User-Id` and returns at most one current cue for that patient. Cues are normalized, explainable records with a source ID, priority, and optional expiration.

The current rules are deliberately narrow:

* `schedule_upcoming`: a same-day schedule item in the next 30 minutes by default;
* `recognized_person`: the latest successful explicit **Who is this?** event within a short window, using the stored `Person` name and relationship; and
* `important_object`: a caregiver-marked important object with a recent last-seen observation and a recent activity explicitly matching a leaving-related phrase.

Recognition cues have the highest priority, followed by schedule cues and then important-object cues. The endpoint presents one cue at a time. A patient-scoped cue state prevents the same cue from repeating during the configurable 20-minute cooldown, and a dismissal prevents that cue key from returning. The wearer can turn proactive polling off; manual questions, camera capture, and explicit face recognition remain available.

The cue engine never infers medical needs, medication compliance, emotion, confusion, distress, wandering, falls, or behavioral anomalies. It does not continuously inspect video or perform background face recognition. It evaluates stored context only.

## Development Identity and User Scoping

Stage 6A adds two deterministic local demo profiles, Alex and Jordan. The browser's development profile selector sends the selected user ID in the `X-MemoryCue-User-Id` header. Query answers, memory creation and listing, people, schedules, object observations, vision analysis, and media access are scoped to that user. Switching profiles clears visible answers and unsaved camera/form state.

This is explicit development identity only; it is not authentication or authorization. The demo seed resets both profiles and their data. Production identity, production caregiver authorization, consent, and permissions remain outside this MVP.

## Caregiver Profile Management

Stage 6B adds a small caregiver setup page at `/caregiver`. Development caregivers Maya, Sam, and Taylor are linked explicitly to patient users: Maya manages Alex, Sam manages Jordan, and Taylor can view Alex without modification permissions. The setup API supports patient profile preferences, text-only known people, important object definitions, schedule items, and short caregiver notes.

Caregiver requests use a separate `X-MemoryCue-Caregiver-Id` header and a centralized link/permission check. Caregivers can only view or modify data for linked patients, and mutations require the matching management permission. These records are the same `Person` and `ScheduleItem` data used by the wearer-facing retrieval system, so caregiver edits are visible in patient queries.

Important object definitions describe things a caregiver considers useful; they do not create `ObjectObservation` history. Caregiver notes are stored for setup context and are not automatically included in AI prompts. The caregiver identity mechanism is simulated and not production authentication; invitations, consent workflows, passwords, and production biometric security remain out of scope.

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
- Meta Quest;
- continuous video recording;
- production authentication;
- complex RAG infrastructure;
- multiple AI providers; or
- a mobile application.

These may be considered later. Stage 8 also does not include continuous autonomous monitoring, medical or medication reminders, push notifications, WebSockets, routine-learning models, or behavioral inference.
