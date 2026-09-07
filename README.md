# MemoryCue

> A software prototype exploring AI-assisted memory glasses for people experiencing memory loss and their caregivers.

MemoryCue is an experimental prototype exploring privacy-first, AI-assisted memory support for everyday activities and objects. It is intended to help retrieve observed context through calm, grounded cues.

## Important Notice

This project is an experimental prototype. It is not a medical device and it is not a diagnostic system. It does not diagnose, treat, or replace professional or caregiver support.

The first MVP is software-only and does not require physical smart glasses.

## Development Status

Current stage: MVP planning / repository bootstrap

This initial repository setup establishes the project structure and documents the MVP boundary. No frameworks, physical hardware integrations, or production services are included yet.

## MVP Direction

The prototype will demonstrate a small, privacy-conscious memory loop:

```text
Observe something
    -> turn it into a memory
    -> store it
    -> ask about it later
    -> return a grounded answer
```

The first demo is intended to answer four simple questions:

- What was I doing?
- Where are my keys?
- Who is Sarah?
- What am I doing today?

Answers should be based on observed or explicitly provided information. When information is unknown, the system should say so rather than inventing a personal answer.

See the [MVP definition](docs/MVP.md) and [architecture direction](docs/architecture.md) for the current scope.

## Privacy and Safety Principles

MemoryCue is designed around privacy and dignity. The intended prototype direction is local-first, with no continuous cloud video upload, no remote video streaming, and no biometric face recognition in the MVP. Prompts should be gentle, transparent about uncertainty, and supportive rather than judgmental.

## Repository Layout

```text
.
├── README.md
├── AGENTS.md
├── .env.example
├── apps/
│   ├── web/
│   └── api/
├── wearable/
│   ├── browser-simulator/
│   └── meta/
├── fixtures/
└── docs/
    ├── MVP.md
    └── architecture.md
```

## Contributing Direction

Keep the MVP small and deterministic. Read `docs/MVP.md` before implementing features, and update it before expanding the product scope. Never commit API keys, secrets, local data, or generated media.
