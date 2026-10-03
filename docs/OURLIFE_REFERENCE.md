# OurLife reference review

MemoryCue was compared against OurLife
(https://github.com/VictorChenCA/RealityHacks26-OurLife, reviewed at commit
`49128421760856bbbd5c7b7ca6cdc8c637591d84`) to find functionality worth bringing
into this project. This document records what was reviewed, what was adopted,
and the licensing basis for each decision.

## Licensing

* The repository's only `LICENSE` file is the MIT License,
  `Copyright (c) 2026 Team OurLife`. MIT permits reuse provided the copyright
  and permission notice is included with copies or substantial portions.
* About 30 files in the iOS app (`Patient App (Raybans)/CameraAccess/...`,
  including `SpeechRecognizer.swift`, `TTSManager.swift`, and
  `StreamSessionViewModel.swift`) carry a `Copyright (c) Meta Platforms, Inc.`
  header pointing to "the license found in the LICENSE file in the root
  directory of this source tree". That Meta license file is not in the
  repository, so OurLife's MIT license cannot be assumed to cover those files.
  They were treated as not reusable.
* The caregiver app's `src/Attributions.md` notes shadcn/ui components (MIT) and
  Unsplash photos (Unsplash license). None were used.

**No OurLife source code, prompts, schemas, or assets were copied or adapted
into MemoryCue.** OurLife was used only as an architectural reference, and every
change below is an independent implementation written against MemoryCue's own
modules. Because nothing was copied, the MIT notice obligation does not apply;
OurLife is acknowledged here as a courtesy. If OurLife code is copied in the
future, its MIT notice must be added alongside it, and Meta-headed files must
not be copied without the applicable Meta license.

## What was adopted

| MemoryCue change | OurLife reference | Why MemoryCue needs it | How it fits MemoryCue | Status |
| --- | --- | --- | --- | --- |
| Time-anchored recall: "What was I doing at 10 AM?" (`apps/api/app/query_service.py`: `clock_time_mention`, `requested_clock_time`, the `recent_activity` branch of `answer_question`) | Temporal memory retrieval: date-range filters on queries (`Backend (GCP)/query_data.md`) and timestamped capture history in `Backend (GCP)/main.py` | MemoryCue could only answer "most recent activity". Asking about a specific time is the core of temporal recall and was missing. | Deterministic parsing and a SQL window over saved `Memory` rows. Picks the latest saved moment at or up to 30 minutes before the asked time; otherwise the standard unknown answer. Reuses existing evidence and correction attribution. No LLM, no generated summaries. | Independently reimplemented |
| Gemini vision provider (`apps/api/app/vision/provider.py`: `GeminiVisionAnalyzer`, `extract_gemini_text`, `VISION_ANALYZERS`) | Gemini integration via `google.generativeai` in `Backend (GCP)/main.py` | The configured OpenAI account has no quota; Gemini has a free tier, so arbitrary-photo analysis can work for the demo. | A second `VisionAnalyzer` behind the existing `get_vision_analyzer()` switch. Calls the documented `generateContent` REST endpoint with `httpx` (no new dependency), reusing MemoryCue's own instructions, JSON schema, and Pydantic validation. Bundled demo scenes still never call a provider. | Independently reimplemented (different API style, SDK, prompts, and output schema from OurLife) |
| Durable hosted photos (`MEDIA_STORAGE=database`; `MediaBlob` model, `apps/api/app/main.py` upload and `/api/media` handlers) | Separating media storage from compute: OurLife uploads captures to Google Cloud Storage and keeps metadata in Firestore (`GCPUploader.swift`, `Backend (GCP)/send_data.md`) | Hosted photos lived in Vercel `/tmp` and disappeared after reload, the one failure seen in the recorded production demo. | Stores image bytes in the already-configured Postgres database in the same transaction as the memory, so no new cloud account or credentials are needed. Media access keeps the existing per-user ownership check. Local file storage stays the default. | Independently reimplemented (database rows rather than an object store) |

## What was reviewed and not adopted

| OurLife area | Decision | Reason |
| --- | --- | --- |
| Meta Wearables SDK / Ray-Ban camera capture (`StreamSessionViewModel.swift`, `MWDATCamera`) | Not adopted | Requires the physical glasses and a native iOS app; real Meta hardware is out of scope per `AGENTS.md`. The files carry Meta copyright headers with an absent license. MemoryCue's browser camera remains the wearable stand-in. |
| iPhone companion architecture (`MemoryCaptureManager.swift`, WebSocket clients) | Not adopted | A mobile app is an MVP non-goal. Its capture flow (capture → upload → send metadata) already matches MemoryCue's capture → review → save flow, which adds the review step OurLife lacks. |
| Speech recognition (`SFSpeechRecognizer`) | Not adopted | MemoryCue already does one explicit Web Speech dictation turn in English and Arabic (`apps/web/app/voice.ts`). OurLife's pattern of stopping speech output before listening is already present (`stopSpeaking()` before `startListening`). |
| Text-to-speech (`AVSpeechSynthesizer`, Google Cloud TTS, ElevenLabs) | Not adopted | Browser speech synthesis already speaks English and Arabic answers. Cloud TTS would add paid keys and latency for no demo benefit. |
| Camera/image upload (GCS signed upload) | Pattern adopted as durable photos above | See the table above. |
| Contextual memory: LLM capture analysis, contact updates, hourly/daily summaries | Not adopted | Model-written summaries and automatic contact updates conflict with MemoryCue's rule that answers come only from reviewed, saved, or caregiver-entered records. |
| WebSocket communication (`/ws/ios`, `/ws/query`, `/ws/unity`) | Not adopted | MemoryCue queries are single request/response turns, so HTTP is simpler and needs no reconnect handling. Vercel now offers WebSockets in beta, but there is no streaming need, and WebSockets are an MVP non-goal. |
| Caregiver UI (Next.js `PeopleManager`, `Memories`, `Reminders`, `LocationReminders`, `RayBanScheduler`) | Not adopted | MemoryCue's caregiver portal already covers people, schedules, objects, notes, saved moments, permissions, and attributed corrections. Location reminders and geofencing are non-goals. |
| Quest / Meta XR memory visualizer (Unity project) | Not adopted | Meta Quest is an MVP non-goal and would be a separate application. |
