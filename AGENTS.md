# Instructions for Coding Agents

## Project Philosophy

This project is an assistive memory prototype.

The AI should help retrieve stored information rather than invent personal information.

## Development Rules

1. Read `docs/MVP.md` before implementing features.
2. Keep MVP scope small.
3. Do not implement real Meta hardware unless explicitly requested.
4. Do not add biometric face recognition unless explicitly requested.
5. Do not make medical or diagnostic claims.
6. Never commit API keys or secrets.
7. Prefer deterministic behavior for the demo.
8. Keep modules small and understandable.
9. Add tests as product functionality is implemented.
10. Do not expand scope without updating `docs/MVP.md`.

## Safety Principle

When the system does not know something about the user's life, it should say that it does not know rather than hallucinate an answer.
