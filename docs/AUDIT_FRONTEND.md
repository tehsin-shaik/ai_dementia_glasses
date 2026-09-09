# MemoryCue Frontend Audit

## Executive Summary

**Status: Polished with minor issues**

MemoryCue now reads as one coherent product across its public product page, wearer experience, caregiver workspace, and development tools. The product page establishes the observe → remember → retrieve → assist story; `/app` makes the camera and short memory cue the primary interaction; `/caregiver` presents setup work in a calmer workspace; and `/demo` keeps inspection-oriented controls separate from the wearer experience.

The About section also fits the product direction. Its layered field-note composition includes the project origin, current capabilities, prototype and medical disclaimer, creator credit, and GitHub link. The reusable draggable-window implementation supports pointer and touch dragging, grab/grabbing cursors, front-most stacking, selection suppression, no-jump offsets, bounds clamping, and compact responsive positions.

The original frontend audit did not change backend product behavior, API contracts, model behavior, identity logic, media handling, or permissions enforcement. The remaining frontend issues are primarily polish and future-product limitations rather than blockers for continuing product work.

## What Was Reviewed

- **Homepage and product narrative:** hero, memory-support examples, caregiver story, final call to action, footer, and the About section.
- **Wearer app (`/app`):** camera-first hierarchy, start/capture/retake/analyze/save states, question input, suggested questions, answer presentation, HUD overlay, loading/error/success states, and separation of wearer-facing content from developer details.
- **Cognitive simplicity:** short labels, familiar questions, progressive disclosure for memory review, calm cue language, and the distinction between last-seen information and current certainty.
- **HUD and camera interaction:** live preview, camera permission errors, captured-frame flow, manual cue controls, HUD `aria-live` announcements, dismissal, and disabled states before camera activation.
- **Caregiver app (`/caregiver`):** simulated identity notice, linked-patient boundary, patient selection, profile/people/object/schedule/note tabs, face-enrollment affordances, status/error feedback, and the calmer visual treatment.
- **Development tools (`/demo`):** deterministic profile seeding, query testing, recent-memory inspection, source IDs, raw-response disclosure, API configuration display, and navigation back to the product surfaces.
- **Navigation and responsive behavior:** shared navigation, route separation, active-route semantics, and CSS behavior at the requested desktop/tablet/mobile breakpoint ranges, including the About composition.
- **Visual system and accessibility:** typography hierarchy, palette, contrast intent, focus-visible rules, reduced-motion rules, semantic headings/labels, form labels, status/error roles, external-link behavior, and drag interaction semantics.
- **Implementation health:** route/component structure, state transitions, CSS cascade, production build, route smoke checks, backend regression tests, dependency checks, and working-tree/diff review.

The responsive review was performed from the route source and CSS breakpoints for 1440px, 1024px, 768px, and 390px layouts. There is no browser automation or visual snapshot harness in the repository, so those dimensions were not rendered into automated screenshots during this audit.

## Findings

### Critical

None found.

### High

None found.

### Medium

#### Caregiver editing affordances do not expose per-patient capabilities

The backend enforces explicit caregiver permissions and returns `403 Caregiver permission required` for disallowed mutations. The frontend patient summary response contains identity fields but no capability flags, so `/caregiver` cannot proactively disable or hide editing controls for a linked viewer. A viewer may see an enabled control and only discover the restriction after submitting it.

This is an affordance limitation, not an authorization bypass. Resolving it cleanly would require a future API response change, which was outside this audit scope.

Evidence: `apps/web/app/caregiver/page.tsx`, `apps/api/app/caregiver.py`, and `apps/api/app/authorization.py`.

#### The global stylesheet has a fragile override cascade

`apps/web/app/globals.css` is 3,142 lines and contains legacy prototype rules alongside repeated route-specific blocks and later override sections. The current build is valid, but the cascade makes future visual changes harder to reason about and increases the chance of regressions when a selector is edited in the wrong section.

This is a maintainability risk rather than a current route failure. A dedicated CSS cleanup pass should preserve the current visual output while consolidating duplicate rules.

### Low

#### Visual QA remains manual

The responsive layout is covered by route source, CSS breakpoints, production builds, and route smoke checks, but the repository does not include a browser screenshot or interaction harness. Pixel-level review and physical touch testing remain manual.

#### The caregiver surface remains intrinsically data-dense

The refactor substantially reduces visual weight and separates setup tasks into tabs, but profile, people, objects, schedule, notes, and face-enrollment workflows still require a sizeable amount of form interaction. This is consistent with the current MVP scope; reducing it further would require product decisions about defaults, permissions, or workflow grouping.

### Informational

- The demo page intentionally exposes source IDs, API configuration, identity-header details, and raw responses. These remain isolated from the wearer-facing `/app` route.
- Identity is explicitly simulated in the caregiver surface. The current UI does not claim production authentication, consent workflows, medical records, or secure account management.
- The camera experience is a browser/laptop simulator. Camera access depends on localhost or HTTPS and does not represent physical glasses hardware.
- The HUD provides a clear dismiss action and live status, but cues persist until dismissed; there is no automatic timeout or voice-triggered dismissal in this prototype.
- No frontend lint, unit-test, end-to-end, automated accessibility, or visual-regression script is defined in `apps/web/package.json`. TypeScript validation is covered by the production build.
- The backend suite continues to emit two dependency deprecation warnings from the installed Starlette/AnyIO test stack; they did not fail the suite.

## Fixes Made

- Reset demo-loaded state, query text, result, loading state, error state, and memory list when changing the active demo profile.
- Added profile-version guards so late memory, seed, or query responses cannot overwrite the newly selected profile’s state.
- Added `aria-current="page"` and matching visual treatment to the shared navigation so the current route is understandable visually and to assistive technology.
- Added an explicit, keyboard-accessible mobile navigation menu with labeled links, Escape-to-close behavior, and focus return to the menu trigger.
- Prevented keyboard activation of the draggable About window title bar from scrolling the page while bringing that window to the front.
- Verified the reusable About drag implementation against the requested interaction requirements: pointer/mouse and touch input through pointer events, grab/grabbing feedback, front-most stacking, pointer-offset tracking without a grab jump, selection suppression, resize-aware bounds clamping, and responsive compact positions.

## Remaining UX Limitations

The current prototype is ready for continued frontend work, but it should not be presented as a production care or medical product. It still has simulated identity, browser camera input, no physical glasses integration, and no production authentication or consent workflow. Viewer-specific caregiver affordances will remain optimistic until the API exposes the relevant capabilities. The stylesheet consolidation remains a worthwhile maintainability follow-up.

Because this repository does not include browser automation, final confidence in pixel-level responsive composition, contrast under every rendered font/platform combination, keyboard-only traversal, touch behavior on physical devices, and reduced-motion playback still requires a manual browser QA pass or a future visual/accessibility test harness.

## Readiness

**Stage 8 frontend integration and the responsive visual maturity pass are complete and ready for manual product verification.**

The current surfaces form a coherent product experience, the requested frontend audit is documented, and the remaining findings are known and bounded. Before a production-oriented release, address caregiver capability affordances, add browser-level accessibility/visual checks, and complete the CSS consolidation pass.

## Stage 8 Follow-up

The wearer app now polls patient-scoped proactive cues every 45 seconds while the **Proactive cues** toggle is on. The active profile and request generation protect against late responses rendering another patient’s cue. A proactive cue uses the existing HUD with a subtle `MemoryCue · Proactive cue` label, one cue at a time, and the same dismiss action used for manual HUD output. Manual query, camera, and explicit recognition flows remain separate. The `/demo` route exposes the current patient-scoped cue and a dismiss action for local verification.

The browser build verifies the integration, but there is still no automated browser harness for polling, toggle, touch/camera interaction, or profile-switch rendering. Those behaviors remain part of the manual verification checklist for this stage. The Stage 8 backend suite covers 74 tests, including cue rules, cooldown, dismissal, recognition-event context, patient scoping, and the identity requirement.

## Validation

| Check | Result |
| --- | --- |
| `npm.cmd run build` in `apps/web` | Passed; Next.js compiled, TypeScript completed, and `/`, `/app`, `/caregiver`, `/demo` were generated. |
| Production route smoke test | Passed; `/`, `/app`, `/caregiver`, and `/demo` each returned HTTP 200 from a local `next start` server. |
| `npm.cmd audit --audit-level=high` | Passed; 0 vulnerabilities. |
| `.venv\Scripts\python.exe -m pytest` in `apps/api` | Passed; 64 tests. |
| `.venv\Scripts\python.exe -m pip check` in `apps/api` | Passed; no broken requirements. |
| Frontend lint/test scripts | Not available; `apps/web/package.json` defines only `dev`, `build`, and `start`. |
| `git diff --check` | Passed with no whitespace errors. |
