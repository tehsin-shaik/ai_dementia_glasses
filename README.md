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

The initial prototype runs entirely as software using simulated camera input.

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
