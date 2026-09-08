"use client";

import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";

import {
  caregiverFetch,
} from "../api";
import SiteNav from "../SiteNav";

type Tab = "profile" | "people" | "objects" | "schedule" | "notes";

type PatientSummary = {
  user_id: number;
  name: string;
  preferred_name: string | null;
};

type PatientProfile = {
  user_id: number;
  preferred_name: string;
  short_bio: string | null;
  home_context: string | null;
  response_style: string | null;
};

type Person = {
  id: number;
  name: string;
  relationship: string;
  face_enrolled: boolean;
};

type ImportantObject = {
  id: number;
  name: string;
  notes: string | null;
};

type ScheduleItem = {
  id: number;
  title: string;
  scheduled_at: string;
};

type CaregiverNote = {
  id: number;
  caregiver_id: number;
  note: string;
  created_at: string;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const CAREGIVERS = [
  { id: 1, name: "Maya" },
  { id: 2, name: "Sam" },
  { id: 3, name: "Taylor" },
] as const;
const TABS: Array<{ id: Tab; label: string }> = [
  { id: "profile", label: "Profile" },
  { id: "people", label: "People" },
  { id: "objects", label: "Important objects" },
  { id: "schedule", label: "Schedule" },
  { id: "notes", label: "Notes" },
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object";
}

async function errorMessage(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
  return typeof payload?.detail === "string" ? payload.detail : fallback;
}

function parsePatients(payload: unknown): PatientSummary[] {
  if (!Array.isArray(payload)) {
    throw new Error("The patient list returned an invalid response.");
  }
  if (
    !payload.every(
      (patient) =>
        isRecord(patient) &&
        typeof patient.user_id === "number" &&
        typeof patient.name === "string" &&
        (patient.preferred_name === null || typeof patient.preferred_name === "string"),
    )
  ) {
    throw new Error("The patient list returned an invalid response.");
  }
  return payload as PatientSummary[];
}

function parseProfile(payload: unknown): PatientProfile {
  if (
    !isRecord(payload) ||
    typeof payload.user_id !== "number" ||
    typeof payload.preferred_name !== "string" ||
    (payload.short_bio !== null && typeof payload.short_bio !== "string") ||
    (payload.home_context !== null && typeof payload.home_context !== "string") ||
    (payload.response_style !== null && typeof payload.response_style !== "string")
  ) {
    throw new Error("The patient profile returned an invalid response.");
  }
  return payload as PatientProfile;
}

function parsePeople(payload: unknown): Person[] {
  if (
    !Array.isArray(payload) ||
    !payload.every(
      (person) =>
        isRecord(person) &&
        typeof person.id === "number" &&
        typeof person.name === "string" &&
        typeof person.relationship === "string" &&
        typeof person.face_enrolled === "boolean",
    )
  ) {
    throw new Error("The people list returned an invalid response.");
  }
  return payload as Person[];
}

function parseObjects(payload: unknown): ImportantObject[] {
  if (
    !Array.isArray(payload) ||
    !payload.every(
      (item) =>
        isRecord(item) &&
        typeof item.id === "number" &&
        typeof item.name === "string" &&
        (item.notes === null || typeof item.notes === "string"),
    )
  ) {
    throw new Error("The important-object list returned an invalid response.");
  }
  return payload as ImportantObject[];
}

function parseSchedule(payload: unknown): ScheduleItem[] {
  if (
    !Array.isArray(payload) ||
    !payload.every(
      (item) =>
        isRecord(item) &&
        typeof item.id === "number" &&
        typeof item.title === "string" &&
        typeof item.scheduled_at === "string",
    )
  ) {
    throw new Error("The schedule returned an invalid response.");
  }
  return payload as ScheduleItem[];
}

function parseNotes(payload: unknown): CaregiverNote[] {
  if (
    !Array.isArray(payload) ||
    !payload.every(
      (note) =>
        isRecord(note) &&
        typeof note.id === "number" &&
        typeof note.caregiver_id === "number" &&
        typeof note.note === "string" &&
        typeof note.created_at === "string",
    )
  ) {
    throw new Error("The notes list returned an invalid response.");
  }
  return payload as CaregiverNote[];
}

function localDateTimeValue(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

function dateTimeInputValue(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value.slice(0, 16) : localDateTimeValue(date);
}

function displayDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export default function CaregiverPage() {
  const [activeCaregiverId, setActiveCaregiverId] = useState<number>(CAREGIVERS[0].id);
  const [patients, setPatients] = useState<PatientSummary[]>([]);
  const [selectedPatientId, setSelectedPatientId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("profile");
  const [profile, setProfile] = useState<PatientProfile | null>(null);
  const [profileForm, setProfileForm] = useState({
    preferred_name: "",
    short_bio: "",
    home_context: "",
    response_style: "",
  });
  const [people, setPeople] = useState<Person[]>([]);
  const [objects, setObjects] = useState<ImportantObject[]>([]);
  const [schedule, setSchedule] = useState<ScheduleItem[]>([]);
  const [notes, setNotes] = useState<CaregiverNote[]>([]);
  const [faceFiles, setFaceFiles] = useState<Record<number, File | null>>({});
  const [personName, setPersonName] = useState("");
  const [personRelationship, setPersonRelationship] = useState("");
  const [objectName, setObjectName] = useState("");
  const [objectNotes, setObjectNotes] = useState("");
  const [scheduleTitle, setScheduleTitle] = useState("");
  const [scheduleAt, setScheduleAt] = useState(localDateTimeValue(new Date()));
  const [noteText, setNoteText] = useState("");
  const [isLoadingPatients, setIsLoadingPatients] = useState(false);
  const [isLoadingPatient, setIsLoadingPatient] = useState(false);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [patientRefreshToken, setPatientRefreshToken] = useState(0);
  const requestVersionRef = useRef(0);

  const activeCaregiver =
    CAREGIVERS.find((caregiver) => caregiver.id === activeCaregiverId) ?? CAREGIVERS[0];
  const selectedPatient = patients.find((patient) => patient.user_id === selectedPatientId) ?? null;

  useEffect(() => {
    requestVersionRef.current += 1;
    const requestVersion = requestVersionRef.current;
    setIsLoadingPatients(true);
    setError(null);
    void (async () => {
      try {
        const response = await caregiverFetch(`${API_URL}/api/caregiver/patients`, activeCaregiverId);
        if (!response.ok) {
          throw new Error(await errorMessage(response, "The linked patients could not be loaded."));
        }
        const nextPatients = parsePatients(await response.json());
        if (requestVersionRef.current !== requestVersion) {
          return;
        }
        setPatients(nextPatients);
        setSelectedPatientId(nextPatients[0]?.user_id ?? null);
      } catch (requestError) {
        if (requestVersionRef.current === requestVersion) {
          setPatients([]);
          setSelectedPatientId(null);
          setError(requestError instanceof Error ? requestError.message : "Something went wrong.");
        }
      } finally {
        if (requestVersionRef.current === requestVersion) {
          setIsLoadingPatients(false);
        }
      }
    })();
  }, [activeCaregiverId]);

  useEffect(() => {
    if (selectedPatientId === null) {
      setProfile(null);
      setPeople([]);
      setObjects([]);
      setSchedule([]);
      setNotes([]);
      setFaceFiles({});
      return;
    }
    setFaceFiles({});
    const requestVersion = requestVersionRef.current;
    setIsLoadingPatient(true);
    setError(null);
    void (async () => {
      try {
        const baseUrl = `${API_URL}/api/caregiver/patients/${selectedPatientId}`;
        const responses = await Promise.all([
          caregiverFetch(`${baseUrl}/profile`, activeCaregiverId),
          caregiverFetch(`${baseUrl}/people`, activeCaregiverId),
          caregiverFetch(`${baseUrl}/objects`, activeCaregiverId),
          caregiverFetch(`${baseUrl}/schedule`, activeCaregiverId),
          caregiverFetch(`${baseUrl}/notes`, activeCaregiverId),
        ]);
        const failedResponse = responses.find((response) => !response.ok);
        if (failedResponse) {
          throw new Error(await errorMessage(failedResponse, "The patient profile could not be loaded."));
        }
        const [nextProfile, nextPeople, nextObjects, nextSchedule, nextNotes] = await Promise.all([
          responses[0].json(),
          responses[1].json(),
          responses[2].json(),
          responses[3].json(),
          responses[4].json(),
        ]);
        if (requestVersionRef.current !== requestVersion) {
          return;
        }
        const parsedProfile = parseProfile(nextProfile);
        setProfile(parsedProfile);
        setProfileForm({
          preferred_name: parsedProfile.preferred_name,
          short_bio: parsedProfile.short_bio ?? "",
          home_context: parsedProfile.home_context ?? "",
          response_style: parsedProfile.response_style ?? "",
        });
        setPeople(parsePeople(nextPeople));
        setObjects(parseObjects(nextObjects));
        setSchedule(parseSchedule(nextSchedule));
        setNotes(parseNotes(nextNotes));
      } catch (requestError) {
        if (requestVersionRef.current === requestVersion) {
          setError(requestError instanceof Error ? requestError.message : "Something went wrong.");
        }
      } finally {
        if (requestVersionRef.current === requestVersion) {
          setIsLoadingPatient(false);
        }
      }
    })();
  }, [activeCaregiverId, selectedPatientId, patientRefreshToken]);

  function clearFeedback() {
    setMessage(null);
    setError(null);
  }

  function handleCaregiverChange(event: ChangeEvent<HTMLSelectElement>) {
    const nextCaregiverId = Number(event.target.value);
    if (!CAREGIVERS.some((caregiver) => caregiver.id === nextCaregiverId)) {
      return;
    }
    requestVersionRef.current += 1;
    setActiveCaregiverId(nextCaregiverId);
    setPatients([]);
    setSelectedPatientId(null);
    setProfile(null);
    setActiveTab("profile");
    clearFeedback();
  }

  function patientBaseUrl(): string | null {
    return selectedPatientId === null
      ? null
      : `${API_URL}/api/caregiver/patients/${selectedPatientId}`;
  }

  async function sendMutation(
    key: string,
    path: string,
    init: RequestInit,
    successMessage: string,
  ): Promise<boolean> {
    setSavingKey(key);
    clearFeedback();
    try {
      const response = await caregiverFetch(path, activeCaregiverId, init);
      if (!response.ok) {
        throw new Error(await errorMessage(response, "The change could not be saved."));
      }
      setMessage(successMessage);
      return true;
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Something went wrong.");
      return false;
    } finally {
      setSavingKey(null);
    }
  }

  function reloadPatient() {
    setPatientRefreshToken((token) => token + 1);
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const baseUrl = patientBaseUrl();
    if (!baseUrl) return;
    const saved = await sendMutation(
      "profile",
      `${baseUrl}/profile`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          preferred_name: profileForm.preferred_name,
          short_bio: profileForm.short_bio || null,
          home_context: profileForm.home_context || null,
          response_style: profileForm.response_style || null,
        }),
      },
      "Patient profile saved.",
    );
    if (saved) {
      const response = await caregiverFetch(`${baseUrl}/profile`, activeCaregiverId);
      if (response.ok) {
        const nextProfile = parseProfile(await response.json());
        setProfile(nextProfile);
      }
    }
  }

  async function addPerson(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const baseUrl = patientBaseUrl();
    if (!baseUrl) return;
    const saved = await sendMutation(
      "person-add",
      `${baseUrl}/people`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: personName, relationship: personRelationship }),
      },
      "Person added.",
    );
    if (saved) {
      setPersonName("");
      setPersonRelationship("");
      await reloadPatient();
    }
  }

  async function savePerson(person: Person) {
    const baseUrl = patientBaseUrl();
    if (!baseUrl) return;
    const saved = await sendMutation(
      `person-${person.id}`,
      `${baseUrl}/people/${person.id}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: person.name, relationship: person.relationship }),
      },
      "Person updated.",
    );
    if (saved) await reloadPatient();
  }

  async function deletePerson(person: Person) {
    const baseUrl = patientBaseUrl();
    if (!baseUrl) return;
    const deleted = await sendMutation(
      `person-delete-${person.id}`,
      `${baseUrl}/people/${person.id}`,
      { method: "DELETE" },
      "Person deleted.",
    );
    if (deleted) await reloadPatient();
  }

  async function enrollFace(person: Person) {
    const baseUrl = patientBaseUrl();
    const file = faceFiles[person.id];
    if (!baseUrl) return;
    if (!file) {
      clearFeedback();
      setError("Choose a face photo before enrolling.");
      return;
    }
    const formData = new FormData();
    formData.append("image", file);
    const saved = await sendMutation(
      `face-${person.id}`,
      `${baseUrl}/people/${person.id}/face`,
      { method: "POST", body: formData },
      person.face_enrolled ? "Face enrollment replaced." : "Face enrolled.",
    );
    if (saved) {
      setFaceFiles((files) => ({ ...files, [person.id]: null }));
      await reloadPatient();
    }
  }

  async function removeFace(person: Person) {
    const baseUrl = patientBaseUrl();
    if (!baseUrl) return;
    const deleted = await sendMutation(
      `face-remove-${person.id}`,
      `${baseUrl}/people/${person.id}/face`,
      { method: "DELETE" },
      "Face enrollment removed.",
    );
    if (deleted) {
      setFaceFiles((files) => ({ ...files, [person.id]: null }));
      await reloadPatient();
    }
  }

  async function addObject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const baseUrl = patientBaseUrl();
    if (!baseUrl) return;
    const saved = await sendMutation(
      "object-add",
      `${baseUrl}/objects`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: objectName, notes: objectNotes || null }),
      },
      "Important object added.",
    );
    if (saved) {
      setObjectName("");
      setObjectNotes("");
      await reloadPatient();
    }
  }

  async function saveObject(item: ImportantObject) {
    const baseUrl = patientBaseUrl();
    if (!baseUrl) return;
    const saved = await sendMutation(
      `object-${item.id}`,
      `${baseUrl}/objects/${item.id}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: item.name, notes: item.notes }),
      },
      "Important object updated.",
    );
    if (saved) await reloadPatient();
  }

  async function deleteObject(item: ImportantObject) {
    const baseUrl = patientBaseUrl();
    if (!baseUrl) return;
    const deleted = await sendMutation(
      `object-delete-${item.id}`,
      `${baseUrl}/objects/${item.id}`,
      { method: "DELETE" },
      "Important object deleted.",
    );
    if (deleted) await reloadPatient();
  }

  async function addScheduleItem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const baseUrl = patientBaseUrl();
    if (!baseUrl) return;
    const saved = await sendMutation(
      "schedule-add",
      `${baseUrl}/schedule`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: scheduleTitle, scheduled_at: scheduleAt }),
      },
      "Schedule item added.",
    );
    if (saved) {
      setScheduleTitle("");
      await reloadPatient();
    }
  }

  async function saveScheduleItem(item: ScheduleItem) {
    const baseUrl = patientBaseUrl();
    if (!baseUrl) return;
    const saved = await sendMutation(
      `schedule-${item.id}`,
      `${baseUrl}/schedule/${item.id}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: item.title, scheduled_at: item.scheduled_at }),
      },
      "Schedule item updated.",
    );
    if (saved) await reloadPatient();
  }

  async function deleteScheduleItem(item: ScheduleItem) {
    const baseUrl = patientBaseUrl();
    if (!baseUrl) return;
    const deleted = await sendMutation(
      `schedule-delete-${item.id}`,
      `${baseUrl}/schedule/${item.id}`,
      { method: "DELETE" },
      "Schedule item deleted.",
    );
    if (deleted) await reloadPatient();
  }

  async function addNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const baseUrl = patientBaseUrl();
    if (!baseUrl) return;
    const saved = await sendMutation(
      "note-add",
      `${baseUrl}/notes`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: noteText }),
      },
      "Caregiver note added.",
    );
    if (saved) {
      setNoteText("");
      await reloadPatient();
    }
  }

  async function deleteNote(note: CaregiverNote) {
    const baseUrl = patientBaseUrl();
    if (!baseUrl) return;
    const deleted = await sendMutation(
      `note-delete-${note.id}`,
      `${baseUrl}/notes/${note.id}`,
      { method: "DELETE" },
      "Caregiver note deleted.",
    );
    if (deleted) await reloadPatient();
  }

  function renderProfile() {
    if (!profile) return null;
    return (
      <form className="caregiver-form" onSubmit={saveProfile}>
        <div className="caregiver-form-grid">
          <label>
            <span>Preferred name</span>
            <input
              type="text"
              value={profileForm.preferred_name}
              onChange={(event) => setProfileForm({ ...profileForm, preferred_name: event.target.value })}
            />
          </label>
          <label>
            <span>Response style</span>
            <input
              type="text"
              value={profileForm.response_style}
              placeholder="e.g. short, calm"
              onChange={(event) => setProfileForm({ ...profileForm, response_style: event.target.value })}
            />
          </label>
        </div>
        <label>
          <span>Short bio <em>(optional)</em></span>
          <textarea
            value={profileForm.short_bio}
            rows={2}
            onChange={(event) => setProfileForm({ ...profileForm, short_bio: event.target.value })}
          />
        </label>
        <label>
          <span>Home context <em>(optional)</em></span>
          <textarea
            value={profileForm.home_context}
            rows={2}
            onChange={(event) => setProfileForm({ ...profileForm, home_context: event.target.value })}
          />
        </label>
        <button className="primary-button" type="submit" disabled={savingKey === "profile"}>
          {savingKey === "profile" ? "Saving..." : "Save profile"}
        </button>
      </form>
    );
  }

  function renderPeople() {
    return (
      <div className="caregiver-section-stack">
        <form className="caregiver-inline-form" onSubmit={addPerson}>
          <label>
            <span>Name</span>
            <input value={personName} onChange={(event) => setPersonName(event.target.value)} placeholder="Sarah" />
          </label>
          <label>
            <span>Relationship</span>
            <input
              value={personRelationship}
              onChange={(event) => setPersonRelationship(event.target.value)}
              placeholder="Daughter"
            />
          </label>
          <button className="secondary-button" type="submit" disabled={savingKey === "person-add"}>
            Add person
          </button>
        </form>
        <div className="caregiver-record-list">
          {people.map((person) => (
            <article className="caregiver-record" key={person.id}>
              <div className="caregiver-record-fields">
                <input
                  aria-label="Person name"
                  value={person.name}
                  onChange={(event) =>
                    setPeople(people.map((item) => (item.id === person.id ? { ...item, name: event.target.value } : item)))
                  }
                />
                <input
                  aria-label="Relationship"
                  value={person.relationship}
                  onChange={(event) =>
                    setPeople(
                      people.map((item) =>
                        item.id === person.id ? { ...item, relationship: event.target.value } : item,
                      ),
                    )
                  }
                />
              </div>
              <div className="caregiver-record-actions">
                <button className="text-button" type="button" onClick={() => void savePerson(person)} disabled={savingKey !== null}>
                  Save
                </button>
                <button className="danger-button" type="button" onClick={() => void deletePerson(person)} disabled={savingKey !== null}>
                  Delete
                </button>
              </div>
              <div className="face-enrollment" aria-label={`${person.name} face enrollment`}>
                <div>
                  <span className="record-meta">Face enrollment</span>
                  <strong>{person.face_enrolled ? "Enrolled" : "Not enrolled"}</strong>
                </div>
                <label className="face-file-picker">
                  <span>{person.face_enrolled ? "Replace photo" : "Upload face photo"}</span>
                  <input
                    type="file"
                    accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
                    onChange={(event) =>
                      setFaceFiles((files) => ({ ...files, [person.id]: event.target.files?.[0] ?? null }))
                    }
                  />
                </label>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => void enrollFace(person)}
                  disabled={savingKey !== null || !faceFiles[person.id]}
                >
                  {person.face_enrolled ? "Replace" : "Enroll face"}
                </button>
                {person.face_enrolled && (
                  <button
                    className="danger-button"
                    type="button"
                    onClick={() => void removeFace(person)}
                    disabled={savingKey !== null}
                  >
                    Remove
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      </div>
    );
  }

  function renderObjects() {
    return (
      <div className="caregiver-section-stack">
        <form className="caregiver-inline-form" onSubmit={addObject}>
          <label>
            <span>Object name</span>
            <input value={objectName} onChange={(event) => setObjectName(event.target.value)} placeholder="Keys" />
          </label>
          <label>
            <span>Notes <em>(optional)</em></span>
            <input
              value={objectNotes}
              onChange={(event) => setObjectNotes(event.target.value)}
              placeholder="Usually carried when leaving"
            />
          </label>
          <button className="secondary-button" type="submit" disabled={savingKey === "object-add"}>
            Add object
          </button>
        </form>
        <div className="caregiver-record-list">
          {objects.map((item) => (
            <article className="caregiver-record" key={item.id}>
              <div className="caregiver-record-fields">
                <input
                  aria-label="Important object name"
                  value={item.name}
                  onChange={(event) =>
                    setObjects(objects.map((object) => (object.id === item.id ? { ...object, name: event.target.value } : object)))
                  }
                />
                <input
                  aria-label="Important object notes"
                  value={item.notes ?? ""}
                  onChange={(event) =>
                    setObjects(
                      objects.map((object) =>
                        object.id === item.id ? { ...object, notes: event.target.value || null } : object,
                      ),
                    )
                  }
                />
              </div>
              <div className="caregiver-record-actions">
                <button className="text-button" type="button" onClick={() => void saveObject(item)} disabled={savingKey !== null}>
                  Save
                </button>
                <button className="danger-button" type="button" onClick={() => void deleteObject(item)} disabled={savingKey !== null}>
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      </div>
    );
  }

  function renderSchedule() {
    return (
      <div className="caregiver-section-stack">
        <form className="caregiver-inline-form" onSubmit={addScheduleItem}>
          <label>
            <span>Title</span>
            <input value={scheduleTitle} onChange={(event) => setScheduleTitle(event.target.value)} placeholder="Sarah visits" />
          </label>
          <label>
            <span>Date and time</span>
            <input type="datetime-local" value={scheduleAt} onChange={(event) => setScheduleAt(event.target.value)} />
          </label>
          <button className="secondary-button" type="submit" disabled={savingKey === "schedule-add"}>
            Add schedule item
          </button>
        </form>
        <div className="caregiver-record-list">
          {schedule.map((item) => (
            <article className="caregiver-record" key={item.id}>
              <div className="caregiver-record-fields">
                <input
                  aria-label="Schedule title"
                  value={item.title}
                  onChange={(event) =>
                    setSchedule(schedule.map((entry) => (entry.id === item.id ? { ...entry, title: event.target.value } : entry)))
                  }
                />
                <input
                  aria-label="Schedule date and time"
                  type="datetime-local"
                  value={dateTimeInputValue(item.scheduled_at)}
                  onChange={(event) =>
                    setSchedule(
                      schedule.map((entry) =>
                        entry.id === item.id ? { ...entry, scheduled_at: event.target.value } : entry,
                      ),
                    )
                  }
                />
              </div>
              <div className="caregiver-record-actions">
                <span className="record-meta">{displayDateTime(item.scheduled_at)}</span>
                <button className="text-button" type="button" onClick={() => void saveScheduleItem(item)} disabled={savingKey !== null}>
                  Save
                </button>
                <button className="danger-button" type="button" onClick={() => void deleteScheduleItem(item)} disabled={savingKey !== null}>
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      </div>
    );
  }

  function renderNotes() {
    return (
      <div className="caregiver-section-stack">
        <form className="caregiver-note-form" onSubmit={addNote}>
          <label>
            <span>Caregiver note</span>
            <textarea value={noteText} onChange={(event) => setNoteText(event.target.value)} rows={3} placeholder="A short trusted note about this patient" />
          </label>
          <button className="secondary-button" type="submit" disabled={savingKey === "note-add"}>
            Add note
          </button>
        </form>
        <div className="caregiver-note-list">
          {notes.map((note) => (
            <article className="caregiver-note" key={note.id}>
              <div>
                <p>{note.note}</p>
                <small>{displayDateTime(note.created_at)} · caregiver {note.caregiver_id}</small>
              </div>
              <button className="danger-button" type="button" onClick={() => void deleteNote(note)} disabled={savingKey !== null}>
                Delete
              </button>
            </article>
          ))}
        </div>
      </div>
    );
  }

  return (
    <main className="caregiver-page-shell">
      <SiteNav />
      <section className="caregiver-card" aria-labelledby="caregiver-title">
        <header className="caregiver-header">
          <div>
            <p className="eyebrow">MemoryCue</p>
            <h1 id="caregiver-title">Caregiver Setup</h1>
            <p className="subtitle">Development prototype for trusted patient context</p>
          </div>
          <div className="caregiver-identity">
            <label>
              <span>Active caregiver</span>
              <select value={activeCaregiverId} onChange={handleCaregiverChange}>
                {CAREGIVERS.map((caregiver) => (
                  <option key={caregiver.id} value={caregiver.id}>
                    {caregiver.name}
                  </option>
                ))}
              </select>
              <small>Development prototype — identity is simulated and not secure authentication.</small>
            </label>
          </div>
        </header>

        <div className="caregiver-notice" role="note">
          Caregiver changes are limited to explicitly linked patients. This prototype stores setup data locally and does not implement production authentication, invitations, consent workflows, or medical records.
        </div>

        <div className="caregiver-layout">
          <aside className="patient-list-panel" aria-labelledby="patient-list-title">
            <p className="section-kicker">Linked patients</p>
            <h2 id="patient-list-title">{activeCaregiver.name}&apos;s patients</h2>
            {isLoadingPatients ? (
              <p className="caregiver-muted">Loading linked patients...</p>
            ) : patients.length > 0 ? (
              <div className="patient-list">
                {patients.map((patient) => (
                  <button
                    className={`patient-button ${selectedPatientId === patient.user_id ? "is-selected" : ""}`}
                    key={patient.user_id}
                    type="button"
                    onClick={() => {
                      setSelectedPatientId(patient.user_id);
                      clearFeedback();
                    }}
                  >
                    <strong>{patient.preferred_name ?? patient.name}</strong>
                    <span>{patient.name}</span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="caregiver-muted">No patients are linked to this caregiver.</p>
            )}
          </aside>

          <section className="management-panel" aria-labelledby="management-title">
            {selectedPatient ? (
              <>
                <div className="management-heading">
                  <div>
                    <p className="section-kicker">Patient profile data</p>
                    <h2 id="management-title">Managing {selectedPatient.preferred_name ?? selectedPatient.name}</h2>
                  </div>
                  <span className="access-badge">{activeCaregiver.name} · linked access</span>
                </div>
                <nav className="management-tabs" aria-label="Patient setup sections">
                  {TABS.map((tab) => (
                    <button
                      className={`management-tab ${activeTab === tab.id ? "is-active" : ""}`}
                      key={tab.id}
                      type="button"
                      onClick={() => {
                        setActiveTab(tab.id);
                        clearFeedback();
                      }}
                    >
                      {tab.label}
                    </button>
                  ))}
                </nav>
                {isLoadingPatient ? (
                  <p className="caregiver-muted management-loading">Loading patient data...</p>
                ) : (
                  <div className="management-section">
                    {activeTab === "profile" && renderProfile()}
                    {activeTab === "people" && renderPeople()}
                    {activeTab === "objects" && renderObjects()}
                    {activeTab === "schedule" && renderSchedule()}
                    {activeTab === "notes" && renderNotes()}
                  </div>
                )}
              </>
            ) : (
              <div className="management-empty">
                <p className="section-kicker">Choose a patient</p>
                <h2>Patient-specific setup stays behind the caregiver link.</h2>
                <p>Select one of the linked patients to view or manage their approved profile data.</p>
              </div>
            )}
          </section>
        </div>

        {message && <p className="caregiver-status" role="status">{message}</p>}
        {error && <p className="caregiver-error" role="alert">{error}</p>}
      </section>
    </main>
  );
}
