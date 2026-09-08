# MemoryCue Stages 1–5 Audit

Audit date: 2026-09-08

## Executive Summary

**Status: Healthy with minor issues.**

Stages 1–5 form a coherent local MVP. The deterministic query service remains the single retrieval path for the normal question panel and the glasses-style HUD. Uploaded and camera-captured memories share the same vision-analysis and memory-save endpoints. The backend has clear enough boundaries between routes, storage, database access, seed data, query behavior, and the optional vision provider for this stage of the project.

The audit found and fixed several small correctness and hardening issues: SQLite foreign-key enforcement was disabled, environment-file ignores were incomplete, seed replacement was split across two transactions, media path handling was not explicitly cross-platform/extension-restricted, and several request/response edges lacked validation. No critical or high-severity issue remains for the current single-user local prototype.

The architecture is **not yet ready for personal profiles or caregiver setup as a security boundary**. Before that work, identity, user scoping, caregiver permissions, and protected media access need an explicit design. That is a deliberate future architectural step, not something introduced in this audit.

## What Was Reviewed

- Repository structure, commit history, tracked files, ignore rules, generated artifacts, environment templates, and credential scans.
- FastAPI routes and separation between database, models, schemas, seed logic, query service, media storage, and vision provider code.
- SQLAlchemy foreign keys, nullability, timestamp ordering, seed reset behavior, and coexistence of seeded and uploaded data.
- All supported query intents, safe unknown responses, deterministic ordering, and source identifiers.
- Memory upload validation, image storage, transaction failure cleanup, object observations, and media serving.
- Vision provider abstraction, OpenAI boundary, prompt constraints, normalized output validation, and failure handling.
- Next.js manual upload, AI-assisted upload, camera capture, normal query, and HUD query flows.
- Webcam permission constraints, capture conversion, stream cleanup, object URL cleanup, HUD state handling, and debug/source separation.
- Timestamp behavior across seed data, API inputs, browser forms, camera captures, schedules, and display.
- API response contracts, runtime frontend response guards, dependency manifests, documentation, and safety claims.

## Findings

### Critical

None.

### High

None remaining for the local MVP scope.

The audit did find that `.env.production` and similar files were not ignored before the fix. No credentials were tracked, and `.gitignore` now ignores `.env.*` while preserving `.env.example`.

### Medium

#### 1. User identity and data scoping are not implemented — remaining

`first_user()` selects the first database user for query, memory-list, and memory-creation flows. There is no authentication, profile selection, caregiver permission model, or per-user media authorization. This is acceptable for the explicitly single-user demo, but it must be resolved before personal profiles or caregiver setup are added.

#### 2. File storage and database writes are compensating, not crash-atomic — remaining

Memory creation now builds the response before committing and removes the generated file after normal database failures. This handles request-time insert/commit errors. A process crash between filesystem replacement and database commit could still leave an orphaned local file, and local SQLite/media storage has no durable cleanup job. This is an acceptable prototype limitation; production storage would require a deliberate lifecycle/transaction design.

### Low

#### 3. Image validation is allowlist-based, not content-decoding-based — remaining

Uploads require a supported extension and, when declared, a matching image MIME type. The prototype does not decode files to verify their binary signatures or scan them for malicious content. Stored names are randomized and media serving is restricted to image extensions, which is proportionate for local development but not production upload security.

#### 4. Frontend automated interaction tests are not configured — remaining

The frontend has no test runner or lint script. The production build, runtime contract guards, source inspection, and HTTP render smoke test provide useful checks, while camera permission/capture still needs a real browser and device. A heavyweight browser-test stack was intentionally not added for this audit.

#### 5. Time handling is intentionally local and naive — remaining

The app stores naive local wall-clock timestamps. This is now documented and consistent across the browser, backend, seed data, schedule queries, and display, but it is not suitable for users or services operating across time zones.

### Informational

- Backend modules are small enough for the MVP; route handlers contain request validation and orchestration, while query, seed, media, and vision responsibilities remain separate. No circular dependency or duplicate implementation was found.
- SQLAlchemy relationships are represented by foreign keys rather than ORM `relationship()` attributes. That is sufficient for the current direct-query code and should be revisited alongside a future profile/data-ownership model.
- `httpx`/Starlette test-client deprecation warnings remain in the existing test environment; they do not fail the suite.
- Backend requirements are version-ranged rather than lock-file-pinned. `pip check` is clean, `npm audit` reports no vulnerabilities, and no backend `pip-audit` tool is installed.

## Area-by-Area Results

### Backend and database

The API surface is compact and explicit: health, demo seed/reset behavior, query, memory creation/listing, media serving, and optional vision analysis. `apps/api/app/query_service.py`, `seed.py`, `media_storage.py`, and `vision/` keep the main responsibilities understandable. SQLite foreign keys are now enabled on every application/test engine connection, and seed deletion remains child-first and repeatable within one transaction.

### Query system

- Recent activity selects the newest non-empty activity, so a newer memory without activity does not hide an older meaningful activity.
- Keys use the newest matching object observation and answer with “I last saw...” wording.
- Sarah lookup returns only the stored relationship and now has deterministic ID ordering if duplicate demo records exist.
- Schedule results use the backend's local day, chronological timestamp ordering, and ID tie-breaking.
- Unknown questions return exactly `I don't know that yet.` with no source IDs.
- Returned source IDs identify the selected memory, object observation/memory, person, or schedule rows.

### Memory creation and media

Required text fields are trimmed and bounded, timestamp parsing is delegated to FastAPI/Pydantic, and optional object names are normalized before observation creation. Shared image reading enforces a 10 MB limit, extension allowlist, and matching declared MIME type. Stored filenames are UUID-based. Media paths reject traversal, absolute paths, encoded traversal, Windows drive/root syntax, symlink escapes, and unsupported extensions.

### Vision provider

The general application depends on the provider-neutral `VisionAnalyzer` interface. OpenAI-specific HTTP, authentication, request formatting, and response extraction remain in `vision/provider.py`. The key is read from environment configuration only. The prompt requires visible, concise evidence, forbids identifying people or inferring relationships/medical conditions, and prefers null for unclear fields. Provider output is validated through strict normalized Pydantic schemas, and analysis never saves a memory automatically.

### Frontend, camera, and HUD

The normal question panel and HUD call the same page-level query operation and `POST /api/query`. The HUD renders the backend answer directly, uses safe unknown/error states, excludes source IDs, and dismisses without touching the camera stream. Camera access requests `video` with `audio: false`; tracks stop on Stop Camera and unmount. Captures are bounded JPEG conversions that reject zero-size/unready video. Preview object URLs are revoked when replaced/unmounted, and broken previews now produce a recoverable user-facing error.

Runtime guards now reject malformed successful query, vision, save, and memory-list responses before they can reach fragile render paths. Existing manual upload, AI suggestion review, camera capture, retake, analyze, and save flows remain intact.

## Fixes Made

- Enabled SQLite `PRAGMA foreign_keys=ON` for every application/test connection and exposed one small engine factory for consistent test setup.
- Kept demo reset deletion and insertion in one transaction.
- Added explicit memory field length validation and moved response validation before the database commit.
- Made uploaded-file cleanup best effort so cleanup errors do not mask the original database failure.
- Added matching declared MIME checks and restricted media serving to supported image extensions.
- Hardened media paths against encoded, POSIX, Windows, absolute, drive-qualified, and symlink traversal cases.
- Made person lookup and schedule boundary behavior deterministic.
- Standardized aware API timestamps to backend-local naive wall-clock storage and documented the convention.
- Added frontend runtime contract guards for query, vision, save, and memory-list responses.
- Added recoverable image-preview error handling.
- Corrected `.gitignore` to protect all `.env.*` files except `.env.example`.
- Added focused regression coverage for foreign keys, upload limits/MIME/field bounds, traversal variants, provider failures, timestamp normalization, and failed-commit media cleanup.
- Clarified README/MVP/architecture language around demo-only person data, future caregiver support, local timestamps, and current HUD behavior.

## Remaining Known Limitations

These are intentional MVP boundaries, not audit regressions:

- local SQLite database;
- local media storage;
- no authentication or authorization;
- one demo user selected by `first_user()`;
- no caregiver dashboard or profile-management UI;
- manually triggered camera capture and HUD queries;
- optional external vision API dependency;
- no real wearable hardware or Meta SDK;
- no face recognition, continuous capture, background analysis, voice input, or text-to-speech;
- no production-grade binary image scanning, object-storage lifecycle, rate limiting, or observability;
- no frontend interaction-test harness or backend dependency lock file.

## Stage 6 Readiness

### Is the current architecture ready for personal profiles and caregiver setup?

**Not as-is.** It is a reasonable single-user prototype base, but the current `first_user()` assumption and unauthenticated media/API surface are not sufficient for private personal profiles or caregiver access.

Before that work begins, define and implement:

1. authenticated identity and explicit current-user resolution;
2. user scoping on every query, memory, schedule, person, and media operation;
3. caregiver roles, consent, and permission boundaries;
4. protected media authorization rather than publicly guessable local routes;
5. migration/ownership rules for existing demo data; and
6. tests proving cross-user records and media cannot be accessed or mixed.

No Stage 6 feature was added by this audit.

## Validation

- Backend tests: `apps/api/.venv\Scripts\python.exe -m pytest tests` — **37 passed**, 2 existing deprecation warnings.
- Frontend production build: `npm.cmd run build` — **passed** with Next.js 16.3.4 and TypeScript validation.
- Frontend dependency audit: `npm.cmd audit --audit-level=moderate` — **0 vulnerabilities**.
- Backend environment consistency: `python -m pip check` — **No broken requirements**. `pip-audit` was not installed.
- Backend health smoke: `GET /api/health` — `{"status":"ok"}`.
- Query smoke: unknown question — `I don't know that yet.`.
- API contract smoke: OpenAPI exposed the seven expected application operations across six paths.
- Frontend render smoke: `GET http://localhost:3000` — HTTP 200; HUD controls were present.
- Repository checks: no tracked media or credential-like values; generated databases, media, environments, caches, and build output remain ignored.

## Post-Audit Follow-Up

Stage 6A addressed the audit's profile-readiness follow-up items that were in scope for explicit identity and user scoping:

- added a central current-user dependency with consistent missing-identity (`401`) and unknown-identity (`404`) responses;
- replaced the runtime `first_user()` assumption with explicit user IDs on query, memory, people, schedule, object-observation, vision, and media paths;
- seeded isolated Alex and Jordan demo users with deterministic, intentionally different context;
- protected media by checking the stored memory owner before serving a file;
- added backend cross-user tests for query results, memory ownership/listing, same-name person relationships, schedules, object observations, media, invalid identity, and ignored client `user_id` payloads; and
- added the browser development profile selector and reset behavior for unsaved camera/form state.

The `X-MemoryCue-User-Id` header and profile selector are development conveniences, not production authentication. Caregiver roles, consent, and caregiver-specific permissions remain Stage 6B work.
