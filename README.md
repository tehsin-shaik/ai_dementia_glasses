# MemoryCue

> AI-assisted memory support designed for people experiencing memory loss and the caregivers who support them.

MemoryCue is an experimental software project exploring how AI-powered smart glasses could act as an external memory aid in everyday life.

The idea is simple: the system observes important moments, remembers useful context, and helps the user recall that information later through short, calm prompts.

For example, a user could ask:

* **What was I doing?**
* **Where did I leave my keys?**
* **Who is Sarah?**
* **What am I doing today?**

Instead of relying on a general-purpose chatbot to guess, MemoryCue is designed to answer from information that was previously observed or provided by a caregiver.

## The Idea

Memory loss can make ordinary daily situations unexpectedly difficult.

Someone may forget:

* what they were doing a few minutes ago;
* where they placed an important object;
* who someone is;
* what they planned to do that day.

MemoryCue explores whether an AI system connected to smart glasses could provide a lightweight layer of memory support.

The long-term concept is:

```text
See and hear what the user experiences
                ↓
Identify useful moments
                ↓
Store structured memories
                ↓
Retrieve them when needed
                ↓
Provide a short spoken or visual reminder
```

## Current MVP

The first version is a software-only prototype.

No physical smart glasses are required.

The MVP focuses on four core experiences:

### 1. Recent activity recall

The user can ask:

> What was I doing?

The system recalls a recent observed activity.

### 2. Last-seen object recall

The user can ask:

> Where are my keys?

The system returns the most recent place the keys were observed.

### 3. People and relationship context

The user can ask:

> Who is Sarah?

The system retrieves caregiver-provided information about that person.

### 4. Daily schedule support

The user can ask:

> What am I doing today?

The system returns a simple schedule of upcoming activities.

## Creating Memories

The prototype supports creating a memory from an uploaded image. Select an image, enter its time, location, description, and optional activity, then optionally provide an object name such as `keys`.

Uploaded images are stored locally with generated filenames. When an object is provided, MemoryCue records the observation so later questions use the newest matching memory. The current prototype accepts `.jpg`, `.jpeg`, `.png`, and `.webp` images up to 10 MB.

### AI-assisted image understanding

When the optional vision provider is configured, select an image and choose **Analyze with AI**. MemoryCue returns concise suggestions for the description, location, activity, and visible objects. The suggestions are placed into the editable form for review; nothing is stored until the user chooses **Save memory**.

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
2. Point the camera at a useful moment and choose **Capture what I see**.
3. Choose **Analyze with AI**, then review or edit the suggested fields.
4. Choose **Save memory** to store the captured frame through the normal memory flow.
5. Ask a supported question such as **Where are my keys?** to retrieve the saved context.

Use **Retake** to replace the captured frame and **Stop camera** when finished. Capture and analysis are always user-triggered in this milestone. MemoryCue does not continuously record, analyze frames, or create memories in the background.

### Glasses-style memory HUD

While the webcam is active, the simulator also provides a compact glasses-style HUD over the live camera view. Choose one of the quick cues or type a question under **Ask MemoryCue**, then choose **Show cue**. The HUD sends that question to the same grounded `/api/query` endpoint used by the normal question panel.

The cue shows the existing answer directly, including a clear unknown state when MemoryCue has no matching context. Choose **Dismiss** to clear it without stopping the camera. All cues are manually triggered: the simulator does not identify faces, continuously analyze video, or run background queries.

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

## Caregiver Support

The project also explores a caregiver interface where trusted people can provide useful context such as:

* names and relationships;
* daily routines;
* appointments;
* important places;
* reminders.

Example:

```text
Sarah
Relationship: Daughter
Visiting today at 3:30 PM
```

This information can then be used to answer simple questions in a familiar and consistent way.

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

**Current stage:** MVP development

The project is currently focused on building the core memory loop:

```text
observe → remember → retrieve → assist
```

See:

* [MVP definition](docs/MVP.md)
* [Architecture](docs/architecture.md)

## Run Locally

Start the backend from `apps/api`:

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

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

Open [http://localhost:3000](http://localhost:3000), load the demo data, and ask one of the four suggested questions. To create a memory, use the **Add a memory** form below the question controls. The backend uses a local SQLite database by default. AI image understanding is optional; follow the configuration above when you want to enable it.

## Safety and Scope

MemoryCue is an experimental assistive technology prototype.

It is **not**:

* a medical device;
* a diagnostic system;
* a replacement for caregivers;
* a replacement for medical professionals.

The project focuses on memory retrieval and everyday support rather than diagnosis or treatment.

## Vision

The goal is to explore whether AI can provide a quiet, respectful form of memory assistance that helps people stay more independent and connected to the people and routines around them.
