# MemoryCue

> A browser-based research prototype exploring AI-assisted memory support for people experiencing memory loss and the caregivers who support them.

MemoryCue is an experimental software prototype for capturing, saving, and retrieving everyday context. It explores how this experience could later extend to AI-assisted smart glasses; no physical MemoryCue glasses are available today.

In the current prototype, a person uploads an image or captures one with a browser camera, reviews or edits the details, and chooses what to save. MemoryCue can later retrieve short answers from those saved records and from caregiver-provided people and schedule information.

For example, a user could ask:

* **What was I doing?**
* **Where did I leave my keys?**
* **Who is Sarah?**
* **What am I doing today?**

Instead of relying on a general-purpose chatbot to guess, MemoryCue is designed to answer from information that was previously observed or explicitly added to the memory system.

## Explore MemoryCue

The prototype has four focused surfaces:

* [`/`](http://localhost:3000/) — the product and research overview;
* [`/app`](http://localhost:3000/app) — the wearer-facing browser camera simulator;
* [`/caregiver`](http://localhost:3000/caregiver) — setup for profiles linked to a simulated caregiver; and
* [`/demo`](http://localhost:3000/demo) — development tools for resetting sample data and inspecting responses.

The product page is the natural starting point. The wearer app brings the camera, optional AI suggestions, review-and-save flow, supported questions, and opt-in person checks together. The caregiver page stores linked-profile setup, while the demo workspace keeps profile switching and response diagnostics available for local development.

## The Idea

Memory loss can make ordinary daily situations unexpectedly difficult.

Someone may forget:

* what they were doing a few minutes ago;
* where they placed an important object;
* who someone is;
* what they planned to do that day.

MemoryCue explores whether an AI system connected to smart glasses could provide a lightweight layer of memory support.

The concept is:

```text
Capture a useful moment
                ↓
Review or confirm the context
                ↓
Save a structured record
                ↓
Retrieve them when needed
                ↓
Provide a short spoken or visual reminder
```

## Current MVP

The first version is a software-only prototype.

No physical smart glasses are required.

The MVP focuses on six core experiences:

### 1. Recent activity recall

The user can ask:

> What was I doing?

The system recalls a recent saved activity.

### 2. Last-seen object recall

The user can ask:

> Where are my keys?

The system returns the most recent place the keys were observed.

### 3. People and relationship context

The user can ask:

> Who is Sarah?

The demo retrieves the stored profile record for that person. The caregiver-facing setup page can maintain the trusted person record used by this lookup.

### 4. Daily schedule support

The user can ask:

> What am I doing today?

The system returns a simple schedule of upcoming activities.

### 5. Approved known-person recognition

Caregivers can optionally enroll a face for an existing person in a patient profile. When the patient chooses **Who is this?** in the live camera simulator, MemoryCue compares that single frame only with that patient's caregiver-approved enrollments. Strong, unambiguous matches show the stored person name and relationship; weak or ambiguous matches return an unknown response. A successful explicit recognition records only the latest patient-scoped recognition event so the cue engine can optionally provide relationship context.

### 6. Proactive context cues

The prototype includes a small rule-based cue engine that can surface one useful reminder without waiting for a typed question. The wearer app polls the profile-scoped `/api/cues` endpoint every 45 seconds while **Optional cues** is turned on.

The cue engine currently considers only:

* same-day schedule items within a configurable lookahead window, defaulting to 30 minutes;
* a stored relationship after the wearer explicitly uses **Who is this?**; and
* an important object with a recent observation and an explicitly recorded leaving-related activity.

Recognition cues take priority over schedule cues, which take priority over object cues. Only one cue is shown at a time. A presented cue has a 20-minute cooldown by default, and the wearer can dismiss it or turn proactive cues off. Manual questions, camera capture, and explicit recognition continue to work independently.

These are conservative, explainable reminders based on stored patient context. MemoryCue does not continuously analyze video, scan faces in the background, infer emotion or confusion, or create medical or medication reminders.

## Creating Memories

The prototype supports creating a memory from an uploaded image. Select an image, enter its time, location, description, and optional activity, then optionally provide an object name such as `keys`.

Uploaded images are stored locally with generated filenames. When an object is provided, MemoryCue records the observation so later questions use the newest matching memory. The current prototype accepts `.jpg`, `.jpeg`, `.png`, and `.webp` images up to 10 MB.

### AI-assisted image understanding

When the optional external vision provider is configured, select an image and choose **Analyze with AI**. The image is sent to that provider, and MemoryCue returns concise suggestions for the description, location, activity, and visible objects. The suggestions are placed into the editable form for review; no MemoryCue memory record is created until the user chooses **Save memory**.

To enable the OpenAI provider locally, set these variables in a `.env` file and start the API with that file:

```dotenv
VISION_PROVIDER=openai
VISION_MODEL=<a vision-capable model available to your account>
VISION_API_KEY=<your API key>
```

```powershell
Copy-Item .env.example .env
uvicorn --env-file ../../.env app.main:app --reload
```

The API key is read only by the backend and must never be committed or exposed to the browser. If these variables are blank or missing, image analysis is disabled with a clear response and manual memory creation continues to work.

AI-generated metadata is a suggestion, not a fact. Review and edit it before saving.

## Glasses Simulator

The browser-based Glasses Simulator uses the laptop webcam as a stand-in for a future wearable camera. Camera access normally requires `localhost` or HTTPS; no microphone permission is requested.

1. Open the app locally and choose **Start camera**.
2. Point the camera at a useful moment and choose **Capture image**.
3. Choose **Analyze with AI**, then review or edit the suggested fields.
4. Choose **Save memory** to store the captured image through the normal memory flow.
5. Ask a supported question such as **Where are my keys?** to retrieve the saved context.

Use **Retake** to replace the captured image and **Stop camera** when finished. Capture and analysis are always user-triggered in this milestone. MemoryCue does not continuously record, analyze frames, or create memories in the background.

### Glasses-style memory HUD

While the webcam is active, the simulator also provides a compact glasses-style HUD over the live camera view. Choose one of the quick cues or type a question under **Ask MemoryCue**, then choose **Ask**. The HUD sends that question to the same grounded `/api/query` endpoint used by the normal question panel.

The cue shows the existing answer directly, including a clear unknown state when MemoryCue has no matching context. Choose **Dismiss** to clear it without stopping the camera. MemoryCue does not continuously analyze video or run background queries. Face recognition is a separate, manually triggered action described below.

### Approved known-person recognition

Known-person recognition is opt-in and begins in the existing caregiver **People** section. A caregiver chooses an existing person, uploads a reference photo containing exactly one face, and selects **Enroll reference**. The upload does not create a person automatically. **Replace reference** updates the enrollment and **Remove reference** deletes it.

The backend uses the local `dlib-bin` runtime with the pretrained `face-recognition-models` dlib ResNet encoder and five-point landmark predictor. Embeddings are generated on the local API process using CPU and only the derived 128-dimensional embedding is stored; the reference photo is not retained by this feature. The configurable similarity threshold defaults to `0.65` and `FACE_MATCH_MARGIN` defaults to `0.08`. Similarity is normalized so larger values are better. A match must clear the threshold and exceed the next candidate by the margin; otherwise the result is unknown.

While the webcam is active, choose **Who is this?** to capture and send one current frame to `POST /api/face/recognize`. The wearer sees only a short cue such as:

```text
Sarah
Your daughter
```

or:

```text
I couldn't match this person to an enrolled face.
```

There is no global face database, public-figure or stranger search, internet identity lookup, automatic enrollment, continuous scanning, relationship inference, or biometric authentication. Names and relationships come from the caregiver-managed `Person` record. This is a research prototype, not production biometric security.

## Development Profiles

The local prototype includes a clearly labeled **Demo profile** selector for two deterministic users: Alex and Jordan. Choose a profile to view its isolated memories, people, schedule, object observations, and camera-cue answers. Changing profiles clears the current question result and any unsaved camera memory so captured information cannot be saved under the wrong profile.

This selector is a development convenience, not authentication. The browser sends the selected profile ID in the `X-MemoryCue-User-Id` request header, and the API uses it to scope personal data. The demo seed is a local reset operation that recreates both profiles. The caregiver page uses a separate simulated identity and explicit patient links for this prototype; production identity, consent, and audit controls remain future work.

## Example

A simulated day might contain:

```text
10:00 AM — Making tea in the kitchen
10:10 AM — Reading in the living room
10:18 AM — Keys seen on the kitchen counter
10:25 AM — Preparing to leave for a walk
```

Later, the user asks:

> Where are my keys?

MemoryCue responds:

> I last saw your keys on the kitchen counter at 10:18 AM.

The distinction matters: the system reports what it remembers seeing rather than pretending it knows where the keys are now.

## Caregiver Setup

The `/caregiver` page is a small development prototype for trusted patient context. Select a simulated caregiver, choose one of the patients explicitly linked to that caregiver, and manage:

* patient profile details and response preferences;
* known people and relationships;
* important object definitions;
* schedule items; and
* short caregiver notes.

Maya is linked to Alex, while Sam is linked to Jordan. The API checks that relationship and the requested permission on every caregiver operation, so the setup page does not expose unlinked patients. Important object definitions are separate from observed object history, and caregiver notes are stored for setup context but are not automatically sent to the vision provider or query prompt. Face enrollment uses the same `manage_people` permission.

The caregiver selector is development-only and not secure authentication. There is no caregiver invitation, consent workflow, password login, or production healthcare portal. Taylor is included as a read-only demo caregiver for permission testing.

Example patient context:

```text
Sarah
Relationship: Daughter
Response style: Short, calm reminders
```

The example person and schedule are loaded by the deterministic demo seed, which resets Alex, Jordan, Maya, Sam, and Taylor. After a caregiver changes a person or schedule item, the wearer-facing patient experience reads the same stored record.

## Future Smart Glasses Integration

The initial prototype runs entirely as software. The Glasses Simulator uses a laptop webcam to approximate a first-person wearable camera, while uploaded images remain supported as a separate input.

The architecture is intended to later support wearable devices such as Meta AI glasses.

A future version could use:

* first-person camera input;
* microphone input;
* open-ear audio responses;
* wearable display prompts where supported.

The software prototype allows the memory system to be developed and tested before physical hardware is required.

## Project Structure

```text
.
├── apps/
│   ├── web/
│   └── api/
├── wearable/
│   ├── browser-simulator/
│   └── meta/
├── fixtures/
├── docs/
├── AGENTS.md
└── README.md
```

## Project Status

**Current stage:** Stage 8 proactive context cues prototype

The project is currently focused on building the core memory loop:

```text
observe → remember → retrieve → assist
```

See:

* [MVP definition](docs/MVP.md)
* [Architecture](docs/architecture.md)
* [Frontend audit](docs/AUDIT_FRONTEND.md)

## Run Locally

Start the backend from `apps/api`:

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The local face-recognition dependencies include a prebuilt `dlib-bin` runtime and roughly 100 MB of pretrained model data. It runs on CPU and avoids a Visual C++ build on supported Windows/Python combinations; no GPU or cloud face API is required. If it is not installed or cannot be configured, ordinary memory features still work and face enrollment reports a clear configuration error.

On Windows PowerShell, activate the environment with:

```powershell
.\.venv\Scripts\Activate.ps1
```

In a second terminal, start the frontend:

```bash
cd apps/web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) for the product page. Choose **Try the simulator** or open [http://localhost:3000/app](http://localhost:3000/app) for the wearer experience. Use [http://localhost:3000/demo](http://localhost:3000/demo) to choose **Alex** or **Jordan**, select **Reset all data and load demo**, and inspect saved answers. That reset replaces all prototype data before loading samples for both profiles. Open [http://localhost:3000/caregiver](http://localhost:3000/caregiver) for the caregiver setup page, select Maya, Sam, or Taylor, and manage only the linked profile information. The backend uses a local SQLite database by default. AI image understanding is optional and uses an external vision provider when configured; follow the configuration above when you want to enable it.

The local prototype stores timestamps as naive local wall-clock values. The browser and backend use their local time for manual/camera entries and the demo schedule; timezone-aware API timestamps are converted to the backend's local time before storage.

To try optional cues locally, reset and load the demo data, then use `/caregiver` to add a schedule item within the next 30 minutes for Alex or Jordan. Open `/app`, select the same profile, start the camera, and leave **Optional cues** turned on. The cue appears over the camera preview, can be dismissed, and will not immediately repeat. `/demo` includes a **Current cue** panel for inspecting the profile-scoped result without using the camera.

## Safety and Scope

MemoryCue is an experimental assistive technology prototype.

It is **not**:

* a medical device;
* a diagnostic system;
* a replacement for caregivers;
* a replacement for medical professionals; or
* a medical or medication reminder system.

The project focuses on memory retrieval and everyday support rather than diagnosis or treatment.

## Vision

The goal is to explore whether AI can provide a quiet, respectful form of memory assistance that helps people stay more independent and connected to the people and routines around them.
