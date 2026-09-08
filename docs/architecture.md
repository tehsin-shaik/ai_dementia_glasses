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
