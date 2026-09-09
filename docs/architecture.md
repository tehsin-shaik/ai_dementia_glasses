# Architecture Direction

The initial system is intentionally simple:

```text
Camera / Simulator
        |
        v
Capture
        |
        v
Optional image analysis
        |
        v
Review and edit
        |
        v
Memory storage
        |
        v
Normal question or manual HUD cue
        |
        v
Retrieval
        |
        v
Grounded answer / HUD overlay
```

Stored patient context also feeds a separate conservative path:

```text
Schedule / explicit recognition event / recent memory + important object
        |
        v
Patient-scoped CueEngine
        |
        v
GET /api/cues
        |
        v
One prioritized, dismissible HUD cue
```

## Hardware Abstraction

The input source should be replaceable without changing the memory, analysis, and question-answering flow:

```text
Uploaded image --------┐
                       |
Browser webcam --------+--> same vision analysis
                       |          |
Future Meta frame ----┘          v
                              review/edit
                                  |
                                  v
                              memory save
```

The backend should eventually be independent of the device producing the image/audio input.

## Frontend Surfaces

The web client is organized around the different people and tasks in the prototype:

```text
Product overview (/)
        |
        +--> Wearer app (/app) ------> camera, cues, capture, AI review
        |
        +--> Caregiver setup (/caregiver) -> patient context and approvals
        |
        +--> Demo workspace (/demo) ------> seed data and inspect responses
```

The product page is a public-facing introduction. The wearer route is the glasses-style interaction surface and keeps development diagnostics out of the primary experience. Caregiver setup remains a calm, form-oriented management surface. The demo workspace exposes local profile switching, deterministic seed data, recent memories, and raw query details for development. These routes share the existing API contracts and identity headers; the route separation is a presentation change, not a new authorization boundary.

The frontend uses two intentional type roles: editorial/display moments use an Apple Garamond-style serif with legal system fallbacks, while application UI uses an SF Pro/system sans-serif stack. The distinction is limited to presentation and does not introduce proprietary font files.

## Contextual HUD Query Flow

The live camera HUD is a presentation surface for the existing question-answering path. A manual quick cue or custom question is sent to `POST /api/query`, then the returned grounded answer is shown as a short overlay inside the live preview. The normal response panel continues to hold developer details such as source IDs; the wearer-facing HUD does not display them.

```text
Manual HUD trigger
        |
        v
POST /api/query
        |
        v
Existing retrieval and grounded answer
        |
        v
Dismissible HUD cue
```

There is no continuous camera analysis. Manual HUD queries still use `POST /api/query`; proactive polling checks only stored schedule, recognition-event, and memory/object context. Stage 7 adds a separate, explicit single-frame face-recognition path.

## Approved Known-Person Recognition Flow

Face recognition is deliberately bounded by the caregiver-managed patient profile:

```text
Existing Person record
        +
Caregiver-approved reference photo
        |
        v
Local face-recognition embedding
        |
        v
PersonFaceEnrollment(patient_user_id, person_id, embedding)
        ^
        |
Current patient + explicit "Who is this?" frame
        |
        v
Patient-scoped candidate comparison
        |
        v
Conservative threshold + ambiguity margin
        |
        +--> stored Person name/relationship in short HUD cue
        |
        +--> unknown when weak, ambiguous, or not enrolled
```

A successful explicit match updates the latest patient-scoped `RecognitionEvent`. The proactive cue engine may use that event for a short-lived relationship cue; no raw frame is stored and no continuous recognition loop is introduced.

The provider boundary lives under `app/face/`: `FaceRecognizer` exposes embedding extraction and similarity comparison, `provider.py` contains the local `dlib-bin` implementation, and `service.py` owns serialization plus threshold and margin decisions. Route handlers do not call a cloud service or perform a global search. The current provider uses dlib's HOG detector, five-point landmark predictor, and pretrained `face-recognition-models` 128-dimensional ResNet encoder on CPU; similarity is normalized to a larger-is-better value.

Only the derived embedding is stored. The caregiver reference image is read temporarily for validation and embedding extraction, then discarded. The recognition response exposes only `recognized`, the matched stored person fields when safe, and a bounded confidence value; it never returns embeddings or candidate lists. Confidence is intentionally withheld from the wearer HUD. This remains an opt-in research prototype and is not biometric authentication or production biometric security.

## Development Identity Boundary

Personal API operations resolve the selected local demo user from the `X-MemoryCue-User-Id` request header before reading or writing user data:

```text
Development profile selector
            |
            v
X-MemoryCue-User-Id
            |
            v
Current-user dependency
            |
            v
User-scoped query / memory / people / schedule / object / media / cue access
```

`GET /api/health` remains public, and `POST /api/demo/seed` is an intentionally unscoped local reset operation. Vision analysis requires a valid development identity even though it does not write a memory. Media access checks both the requested filename and ownership of the stored memory before returning a file. The header is a development boundary, not production authentication; caregiver permissions and consent are future work.

## Proactive Cue Engine

The cue engine lives under `app/cues/` and keeps rule evaluation out of route handlers. It evaluates three stored-context rules: same-day schedule items within the configurable lookahead window, the latest successful explicit recognition event, and an important object whose recent observation is paired with an explicitly recorded leaving-related activity.

Candidates are sorted by priority (`recognized_person`, `schedule_upcoming`, then `important_object`). `GET /api/cues` returns at most one candidate, records its presentation time, and applies the patient-scoped cooldown. `POST /api/cues/{cue_id}/dismiss` records dismissal for the same patient-scoped cue key. The wearer polls at a low frequency only while proactive cues are enabled.

The current defaults are `CUE_SCHEDULE_LOOKAHEAD_MINUTES=30`, `CUE_COOLDOWN_MINUTES=20`, `CUE_RECOGNITION_WINDOW_MINUTES=10`, and `CUE_OBJECT_LOOKBACK_MINUTES=30`. The rules prefer no cue when the stored context is insufficient. They do not infer emotion, confusion, medical needs, medication compliance, wandering, falls, or behavioral anomalies.

## Caregiver Management Boundary

Stage 6B adds a separate caregiver identity and authorization path. It never treats the patient identity header as caregiver identity:

```text
Development caregiver selector
            |
            v
X-MemoryCue-Caregiver-Id
            |
            v
Current caregiver dependency
            |
            v
Explicit caregiver-patient link
            |
            v
View or management permission
            |
            v
Patient-scoped profile / people / objects / schedule / notes
```

The authorization helper returns a privacy-preserving 404 when a caregiver is not linked to a patient, and a 403 when a linked caregiver lacks the requested management permission. Primary caregivers can manage the profile and the seeded management flags; viewer access is read-only. `ImportantObject` stores caregiver-defined object definitions separately from `ObjectObservation`, which remains observed history for wearer queries. `CaregiverNote` records the authoring caregiver and patient owner but is not automatically injected into AI prompts.

The `/caregiver` page is a development setup surface, not a healthcare portal. Production authentication, invitations, consent, and caregiver audit logging are not implemented.

## Timestamp Convention

The local prototype stores timestamps as naive local wall-clock datetimes. Seed data and schedule queries use the backend's local date, while browser `datetime-local` and camera capture values represent the browser's local wall-clock time. If an API client sends a timezone-aware timestamp, the API converts it to the backend's local time before removing the timezone for SQLite storage. This is intentionally simple and is not a multi-timezone production model.

## Optional Vision Analysis

Uploaded images and browser-captured frames can be sent to one configured vision provider through a provider-neutral interface:

```text
Temporary image upload
        |
        v
Vision provider
        |
        v
Strict normalized analysis
        |
        v
User review and edit
        |
        v
Explicit memory save
```

The analysis endpoint does not write to the database or permanent media storage. Provider output is validated against the internal `VisionAnalysis` schema before it is returned to the client. The client chooses which suggested object, if any, to include when saving a memory.

This document describes the intended direction only. It does not define a complete production architecture.
