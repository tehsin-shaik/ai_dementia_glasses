# Architecture Direction

The initial system is intentionally simple:

```text
Camera / Simulator
        |
        v
Capture
        |
        v
Memory extraction / image analysis
        |
        v
Memory storage
        |
        v
User question
        |
        v
Retrieval
        |
        v
Grounded answer
```

## Hardware Abstraction

The input source should be replaceable without changing the memory and question-answering flow:

```text
Browser simulator
        |
        |
Meta simulator ------> Wearable interface
        |
        |
Real Meta glasses
```

The backend should eventually be independent of the device producing the image/audio input.

## Optional Vision Analysis

Uploaded images can be sent to one configured vision provider through a provider-neutral interface:

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
