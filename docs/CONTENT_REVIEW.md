# MemoryCue Content Review

## Scope

This pass reviewed the visible copy for `/`, `/app`, `/caregiver`, and `/demo`, along with page metadata, the README introduction and local-use instructions, and the current MVP description. It intentionally did not change API routes, request payloads, query strings, retrieval behavior, visual structure, or responsive styling.

## Problems found

* The homepage introduced MemoryCue as delivered AI glasses instead of a browser-based research prototype exploring a possible future wearable experience.
* Capture, optional AI analysis, review, and save were sometimes described as one automatic “memory” action.
* Person recognition copy did not consistently distinguish stored relationship lookup from the explicit **Who is this?** camera check or explain that only enrolled reference faces are compared.
* Optional context cues were described with internal terms such as “HUD,” “proactive,” and “grounded,” without enough explanation of their controls and limits.
* The wearer profile selector implied a private account even though it is a simulated local identity boundary.
* Caregiver profile preferences, object definitions, and notes could be read as if all fields directly changed wearer answers.
* The demo reset action looked profile-specific even though it deletes and reloads all prototype data for both Alex and Jordan.
* The demo page presented vision analysis as available without checking whether an external provider was configured.
* Several headings and empty states were vague, overly sentimental, or written in development shorthand.

## Representative changes

| Before | After |
| --- | --- |
| “AI-assisted glasses designed to bring everyday context back into view.” | “MemoryCue is a browser prototype for people experiencing memory loss and their caregivers. It saves and retrieves everyday context while exploring how the same experience could work through future smart glasses.” |
| “Useful moments become retrievable personal memories.” | “Capture or upload an image, review the details, and save it as a memory you can ask about later.” |
| “Capture memory” | “Capture image” |
| “Alex's private context” | “Simulated profile — not a secure account” |
| “Known-person recognition stays inside caregiver-approved contacts.” | The page now separates saved person records from a user-triggered **Who is this?** check against enrolled reference faces for the selected demo profile. |
| “Managing Alex” | “Alex's setup” |
| “Load demo data” | “Reset all data and load demo” |
| “Vision analysis — Available through the wearer app” | “Vision analysis — Not verified here; requires a configured backend provider” |
| “Review them before they become part of someone's memory.” | “No MemoryCue record is saved until a person reviews the fields and chooses Save memory.” |

## Claims corrected or qualified

* MemoryCue is described as a browser-based software prototype, not available smart-glasses hardware.
* Images are captured or uploaded only after user action. AI image analysis is optional, uses an external provider when configured, and does not save a memory.
* A memory becomes a saved software record only after review and an explicit save action.
* Last-seen answers come from the latest saved object observation and do not claim an object's current location.
* **Who is this?** checks one image against face references enrolled for the selected demo profile; it is not continuous recognition or a global identity search.
* Optional cues use saved schedule and recent context, can be dismissed, and can be turned off.
* Demo profile and caregiver selectors are simulated local identities, not secure accounts or production authentication.
* Important-object definitions do not create last-seen history. A matching saved observation is required.
* Profile response style, short bio, home context, and caregiver notes are stored but do not currently change wearer answers or cues.
* The demo reset replaces all prototype data and loads samples for both demo profiles.
* The interface no longer treats the presence of an analysis button as proof that a vision provider is configured.

## Factual uncertainties retained as limits

* The interface cannot verify from the browser whether the optional vision provider is configured until an analysis request is made.
* The prototype does not provide production authentication, consent management, invitations, audit controls, or a medical-records system.
* The project explores assistive use, but it has not established clinical effectiveness, safety, independence outcomes, or suitability as a medical device.
* Historical stage-audit documents retain terminology from the interface at the time of those audits; current product and MVP documentation now use the revised labels.

## Validation record

* `npm.cmd run build` in `apps/web`: passed. Next.js compiled and prerendered `/`, `/app`, `/caregiver`, and `/demo` successfully.
* `.\node_modules\.bin\tsc.cmd --noEmit` in `apps/web`: passed.
* `python -m pytest` through the API virtual environment: 74 tests passed. Two dependency deprecation warnings remain in the existing FastAPI/Starlette test stack.
* The web package does not define a separate lint script, so no lint command was available to run.
* `git diff --check`: passed after the final edits.
* The edited strings were reviewed against the existing responsive markup and mobile CSS constraints. Interactive browser inspection was not available in this environment, so no claim of visual browser verification is made.
