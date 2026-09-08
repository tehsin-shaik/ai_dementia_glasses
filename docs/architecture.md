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

There is no continuous camera analysis, background querying, or face-recognition path in this prototype.

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
User-scoped query / memory / people / schedule / object / media access
```

`GET /api/health` remains public, and `POST /api/demo/seed` is an intentionally unscoped local reset operation. Vision analysis requires a valid development identity even though it does not write a memory. Media access checks both the requested filename and ownership of the stored memory before returning a file. The header is a development boundary, not production authentication; caregiver permissions and consent are future work.

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
