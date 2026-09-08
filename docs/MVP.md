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

## Memory Creation

The prototype supports manual memory creation from an uploaded image and metadata. A user can provide an image, timestamp, location, description, optional activity, and optional object name such as `keys`.

Uploaded images are stored locally with generated filenames. When an object name is provided, the system creates an object observation linked to the memory. Later object questions use the newest matching observation.

When configured, the Stage 3 vision flow analyzes an uploaded image and proposes normalized description, location, activity, and visible objects. The user must review or edit those suggestions and explicitly save the memory. Analysis alone does not create a memory and the manual workflow remains available without AI credentials.

The current prototype accepts `.jpg`, `.jpeg`, `.png`, and `.webp` images up to 10 MB.

## Glasses Simulator

Stage 4 adds a browser-only webcam simulator. The user can start the camera, capture one frame, send that frame through the existing vision-analysis endpoint, review or edit the suggestions, and explicitly save it through the existing memory endpoint. Captured frames use the same image and retrieval flow as uploaded images.

Camera access normally requires `localhost` or HTTPS. The simulator does not request microphone access, continuously analyze video, record in the background, or capture frames automatically. The user must trigger each capture and save.

## Questions the MVP Must Answer

### 1. What was I doing?

Recall the user's most recent activity.

### 2. Where are my keys?

Return the last observed location of the keys.

The assistant must say:

> "I last saw your keys..."

rather than claiming the keys are definitely still there.

### 3. Who is Sarah?

Retrieve a caregiver-defined person profile.

Example:

```text
Sarah
Relationship: Daughter
```

No automatic biometric face recognition is required for the MVP.

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
- automated face recognition;
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

These may be considered later.
