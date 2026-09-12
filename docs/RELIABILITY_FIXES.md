# Reliability Fixes After the Current-State Audit

**Date:** 2026-09-12

**Baseline audited:** `27aac14298a60225b1989aeca8ed868ea1f43ca7`

**Historical audit:** [`AUDIT_CURRENT_STATE.md`](AUDIT_CURRENT_STATE.md)

This follow-up records the bounded reliability pass requested before Stage 9. The original audit remains unchanged as the evidence of what was observed at that baseline.

## Findings addressed

| Finding | Root cause | Correction | Regression evidence |
|---|---|---|---|
| F-01: unseen cues were consumed | `GET /api/cues` recorded `last_shown_at`, so development effect replay, the demo inspector, or an inactive camera could start cooldown | GET is now observational. The wearer acknowledges a cue only after it is rendered in an active camera HUD on a visible page. A UUID presentation token makes retry idempotent | Backend tests cover repeated GET, acknowledgement, duplicate token, cooldown, wrong-patient, and unknown-cue behavior. Browser tests cover inactive/hidden states, development duplicate reads, one acknowledgement, an empty later poll, and exact expiry |
| F-02: caregiver detail crossed profile selection | Detail responses were not guarded by a generation tied to both caregiver and patient | List, detail, and mutation work now use separate generations, captured identities, and abort controllers. Profile changes clear old detail immediately, and stale completions cannot update the new selection | Browser tests delay Alex detail and mutation responses, switch to Jordan, then verify Jordan remains intact |
| F-03: protected thumbnails broke | A direct `<img>` request could not send the required user identity header | The demo fetches media with the scoped API helper, renders an object URL, and revokes it on replacement or unmount | Browser tests verify the identity header, stale-profile rejection, successful rendering, and object-URL cleanup |
| F-04: viewer controls appeared editable | Linked-profile summaries omitted existing access capabilities | The API returns role and per-section capabilities. The caregiver UI remains readable but disables every unsupported mutation control | Browser tests verify Taylor's read-only profile, people, face, object, schedule, and note controls; a synthetic mutation still receives 403 |
| F-05: demo failures looked empty | Non-success HTTP responses were returned without entering an error state | Memories and cues now have separate loading, failed/retry, successful-empty, and result states, with API details retained for development | Browser tests exercise 500/401 responses, retry, successful empty responses, and recovery |
| F-07: mobile presentation defects | A higher-specificity desktop alignment survived the mobile rule, and JSX joined adjacent text | A scoped 390px alignment override and explicit text spacing correct the two defects | Browser test verifies computed alignment, readable sentence spacing, and no horizontal overflow at 390px |

F-06, server-side image-content decoding, was intentionally left unchanged because it was outside this bounded reliability pass.

## Cue presentation contract

1. `GET /api/cues` evaluates the selected patient's stored context and returns at most one eligible cue without writing presentation state.
2. The wearer may poll while optional cues are enabled, but an acknowledgement is attempted only when the camera is active, the document is visible, the manual HUD is idle, and the unexpired cue is actually rendered.
3. `POST /api/cues/present` re-evaluates eligibility server-side, records the visible presentation, and starts cooldown.
4. The request includes a UUID `presentation_id`. Repeating the same token for the same patient and cue returns the original presentation time and does not extend cooldown. Reusing it for another cue, or acknowledging a currently ineligible cue, returns 409.
5. The client retries a network or 5xx acknowledgement once with the same token. A 4xx response is terminal for that presentation attempt.
6. Dismissal remains patient- and cue-key-scoped. Demo inspection uses only the read-only GET.

The local SQLite implementation provides durable sequential idempotency for one presentation token. It is not a claim of distributed exactly-once delivery across future multi-process deployments.

## Caregiver request boundaries

Changing caregiver or patient invalidates and aborts outstanding detail and mutation requests, clears drafts and feedback, and prevents editing until the selected profile has loaded completely. Every completion checks the caregiver ID, patient ID, and request generation before updating UI state.

Aborting a request does not undo a save that the server may already have committed. The guarantee here is that a late result or message cannot be applied to another selected profile; it is not transaction cancellation.

## Automated regression coverage

The new Playwright suite runs in installed Chrome and does not download browser binaries. It starts a test-only Next.js server on port 3100 with an isolated `.next-playwright` output directory, so it can run without interrupting a normal development server. All API calls in the browser regressions are intercepted with deterministic fixtures; no normal database or media directory is modified.

Commands and results for this pass:

| Check | Result |
|---|---|
| `apps/api/.venv/Scripts/python.exe -m pytest -q` | 76 passed; 2 existing dependency deprecation warnings |
| `npm.cmd run test:e2e` | 7 passed in installed Chrome |
| `apps/web/node_modules/.bin/tsc.cmd --noEmit` | Passed |
| `npm.cmd run build` | Passed; `/`, `/app`, `/caregiver`, `/demo`, and not-found generated successfully |
| `npm.cmd audit --audit-level=low` | 0 vulnerabilities |
| `npm.cmd ls --depth=0` | Declared dependencies resolved; the two previously observed optional Sharp runtime packages remain extraneous |
| `apps/api/.venv/Scripts/python.exe -m pip check` | No broken requirements |
| `git diff --check` | Passed |

## Remaining boundaries

This remains a local, synthetic-data research prototype and is not ready for public deployment or real patient data. The audit's production blockers remain: simulated header identity, unauthenticated global reset, no sensitive-data lifecycle or production security model, no clinical validation, relative local storage paths, and server-local timestamp assumptions.

Additional verification still not performed includes real vision-provider quality, real face-recognition accuracy, physical camera and mobile devices, screen readers, formal accessibility scanning, Safari/Firefox, long-running offline/reconnect behavior, and scale testing. There is still no frontend lint gate. These are not claimed as resolved by this pass.
