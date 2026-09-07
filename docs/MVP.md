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

## Manual Memory Creation

The prototype supports manual memory creation from an uploaded image and metadata. A user can provide an image, timestamp, location, and description, plus an optional object name such as `keys`.

Uploaded images are stored locally with generated filenames. When an object name is provided, the system creates an object observation linked to the memory. Later object questions use the newest matching observation. Image contents are not interpreted automatically yet.

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
