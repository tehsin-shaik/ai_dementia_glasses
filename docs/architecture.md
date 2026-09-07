# Architecture Direction

The initial system is intentionally simple:

```text
Camera / Simulator
        |
        v
Capture
        |
        v
Memory extraction
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

This document describes the intended direction only. It does not define a complete production architecture.
