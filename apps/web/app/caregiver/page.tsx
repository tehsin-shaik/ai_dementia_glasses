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
  role: string;
  can_manage_profile: boolean;
  can_manage_people: boolean;
  can_manage_schedule: boolean;
  can_manage_objects: boolean;
  can_manage_notes: boolean;
};

type PatientScope = {
  caregiverId: number;
  patientId: number;
  generation: number;
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
        (patient.preferred_name === null || typeof patient.preferred_name === "string") &&
        typeof patient.role === "string" &&
        typeof patient.can_manage_profile === "boolean" &&
        typeof patient.can_manage_people === "boolean" &&
        typeof patient.can_manage_schedule === "boolean" &&
        typeof patient.can_manage_objects === "boolean" &&
        typeof patient.can_manage_notes === "boolean",
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
  const [patientListError, setPatientListError] = useState<string | null>(null);
  const [patientListRefreshToken, setPatientListRefreshToken] = useState(0);
  const [patientRefreshToken, setPatientRefreshToken] = useState(0);
  const patientListGenerationRef = useRef(0);
  const detailGenerationRef = useRef(0);
  const activeCaregiverIdRef = useRef(activeCaregiverId);
  const selectedPatientIdRef = useRef(selectedPatientId);
  const patientListAbortRef = useRef<AbortController | null>(null);
  const detailAbortRef = useRef<AbortController | null>(null);
  const mutationAbortRefs = useRef<Set<AbortController>>(new Set());

  activeCaregiverIdRef.current = activeCaregiverId;
  selectedPatientIdRef.current = selectedPatientId;

  const activeCaregiver =
    CAREGIVERS.find((caregiver) => caregiver.id === activeCaregiverId) ?? CAREGIVERS[0];
  const selectedPatient = patients.find((patient) => patient.user_id === selectedPatientId) ?? null;
  const canManageProfile = selectedPatient?.can_manage_profile === true;
  const canManagePeople = selectedPatient?.can_manage_people === true;
  const canManageObjects = selectedPatient?.can_manage_objects === true;
  const canManageSchedule = selectedPatient?.can_manage_schedule === true;
  const canManageNotes = selectedPatient?.can_manage_notes === true;
  const activeTabCanManage = selectedPatient
    ? {
        profile: canManageProfile,
        people: canManagePeople,
        objects: canManageObjects,
        schedule: canManageSchedule,
        notes: canManageNotes,
      }[activeTab]
    : false;

  function clearPatientContext(nextPatientId: number | null) {
    detailGenerationRef.current += 1;
    detailAbortRef.current?.abort();
    detailAbortRef.current = null;
    mutationAbortRefs.current.forEach((controller) => controller.abort());
    mutationAbortRefs.current.clear();
    selectedPatientIdRef.current = nextPatientId;
    setProfile(null);
    setProfileForm({ preferred_name: "", short_bio: "", home_context: "", response_style: "" });
    setPeople([]);
    setObjects([]);
    setSchedule([]);
    setNotes([]);
    setFaceFiles({});
    setPersonName("");
    setPersonRelationship("");
    setObjectName("");
    setObjectNotes("");
    setScheduleTitle("");
    setScheduleAt(localDateTimeValue(new Date()));
    setNoteText("");
    setSavingKey(null);
    setMessage(null);
    setError(null);
    setIsLoadingPatient(nextPatientId !== null);
  }

  function selectPatient(patientId: number | null) {
    const selectionIsUnchanged = selectedPatientIdRef.current === patientId;
    clearPatientContext(patientId);
    setSelectedPatientId(patientId);
    if (selectionIsUnchanged && patientId !== null) {
      setPatientRefreshToken((token) => token + 1);
    }
  }

  function scopeIsCurrent(scope: PatientScope): boolean {
    return (
      activeCaregiverIdRef.current === scope.caregiverId &&
      selectedPatientIdRef.current === scope.patientId &&
      detailGenerationRef.current === scope.generation
    );
  }

  function currentPatientScope(): PatientScope | null {
    const patientId = selectedPatientIdRef.current;
    if (patientId === null || !profile || isLoadingPatient) {
      return null;
    }
    return {
      caregiverId: activeCaregiverIdRef.current,
      patientId,
      generation: detailGenerationRef.current,
    };
  }

  useEffect(() => {
    return () => {
      patientListGenerationRef.current += 1;
      detailGenerationRef.current += 1;
      patientListAbortRef.current?.abort();
      detailAbortRef.current?.abort();
      mutationAbortRefs.current.forEach((controller) => controller.abort());
      mutationAbortRefs.current.clear();
    };
  }, []);

  useEffect(() => {
    patientListGenerationRef.current += 1;
    const requestGeneration = patientListGenerationRef.current;
    const requestCaregiverId = activeCaregiverId;
    const controller = new AbortController();
    patientListAbortRef.current?.abort();
    patientListAbortRef.current = controller;
    setIsLoadingPatients(true);
    setPatientListError(null);
    setError(null);
    void (async () => {
      try {
        const response = await caregiverFetch(`${API_URL}/api/caregiver/patients`, requestCaregiverId, {
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(await errorMessage(response, "The linked profiles could not be loaded."));
        }
        const nextPatients = parsePatients(await response.json());
        if (
          patientListGenerationRef.current !== requestGeneration ||
          activeCaregiverIdRef.current !== requestCaregiverId
        ) {
          return;
        }
        setPatients(nextPatients);
        selectPatient(nextPatients[0]?.user_id ?? null);
      } catch (requestError) {
        if (
          !(requestError instanceof DOMException && requestError.name === "AbortError") &&
          patientListGenerationRef.current === requestGeneration &&
          activeCaregiverIdRef.current === requestCaregiverId
        ) {
          setPatients([]);
          selectPatient(null);
          setPatientListError(
            requestError instanceof Error ? requestError.message : "The linked profiles could not be loaded.",
          );
        }
      } finally {
        if (
          patientListGenerationRef.current === requestGeneration &&
          activeCaregiverIdRef.current === requestCaregiverId
        ) {
          setIsLoadingPatients(false);
        }
      }
    })();
    return () => controller.abort();
  }, [activeCaregiverId, patientListRefreshToken]);

  useEffect(() => {
    if (selectedPatientId === null) {
      setIsLoadingPatient(false);
      return;
    }
    detailGenerationRef.current += 1;
    const requestGeneration = detailGenerationRef.current;
    const requestCaregiverId = activeCaregiverId;
    const requestPatientId = selectedPatientId;
    const controller = new AbortController();
    detailAbortRef.current?.abort();
    detailAbortRef.current = controller;
    setProfile(null);
    setProfileForm({ preferred_name: "", short_bio: "", home_context: "", response_style: "" });
    setPeople([]);
    setObjects([]);
    setSchedule([]);
    setNotes([]);
    setFaceFiles({});
    setIsLoadingPatient(true);
    setError(null);
    void (async () => {
      try {
        const baseUrl = `${API_URL}/api/caregiver/patients/${requestPatientId}`;
        const responses = await Promise.all([
          caregiverFetch(`${baseUrl}/profile`, requestCaregiverId, { signal: controller.signal }),
          caregiverFetch(`${baseUrl}/people`, requestCaregiverId, { signal: controller.signal }),
          caregiverFetch(`${baseUrl}/objects`, requestCaregiverId, { signal: controller.signal }),
          caregiverFetch(`${baseUrl}/schedule`, requestCaregiverId, { signal: controller.signal }),
          caregiverFetch(`${baseUrl}/notes`, requestCaregiverId, { signal: controller.signal }),
        ]);
        const failedResponse = responses.find((response) => !response.ok);
        if (failedResponse) {
          throw new Error(await errorMessage(failedResponse, "The selected profile could not be loaded."));
        }
        const [nextProfile, nextPeople, nextObjects, nextSchedule, nextNotes] = await Promise.all([
          responses[0].json(),
          responses[1].json(),
          responses[2].json(),
          responses[3].json(),
          responses[4].json(),
        ]);
        const scope = { caregiverId: requestCaregiverId, patientId: requestPatientId, generation: requestGeneration };
        if (!scopeIsCurrent(scope)) {
          return;
        }
        const parsedProfile = parseProfile(nextProfile);
        const parsedPeople = parsePeople(nextPeople);
        const parsedObjects = parseObjects(nextObjects);
        const parsedSchedule = parseSchedule(nextSchedule);
        const parsedNotes = parseNotes(nextNotes);
        setProfile(parsedProfile);
        setProfileForm({
          preferred_name: parsedProfile.preferred_name,
          short_bio: parsedProfile.short_bio ?? "",
          home_context: parsedProfile.home_context ?? "",
          response_style: parsedProfile.response_style ?? "",
        });
        setPeople(parsedPeople);
        setObjects(parsedObjects);
        setSchedule(parsedSchedule);
        setNotes(parsedNotes);
      } catch (requestError) {
        const scope = { caregiverId: requestCaregiverId, patientId: requestPatientId, generation: requestGeneration };
        if (
          !(requestError instanceof DOMException && requestError.name === "AbortError") &&
          scopeIsCurrent(scope)
        ) {
          setError(requestError instanceof Error ? requestError.message : "Something went wrong.");
        }
      } finally {
        const scope = { caregiverId: requestCaregiverId, patientId: requestPatientId, generation: requestGeneration };
        if (scopeIsCurrent(scope)) {
          setIsLoadingPatient(false);
        }
      }
    })();
    return () => controller.abort();
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
    patientListGenerationRef.current += 1;
    patientListAbortRef.current?.abort();
    activeCaregiverIdRef.current = nextCaregiverId;
    setActiveCaregiverId(nextCaregiverId);
    setIsLoadingPatients(true);
    setPatientListError(null);
    setPatients([]);
    selectPatient(null);
    setActiveTab("profile");
  }

  function retryPatientList() {
    setIsLoadingPatients(true);
    setPatientListError(null);
    setPatientListRefreshToken((token) => token + 1);
  }

  async function sendMutation(
    scope: PatientScope,
    key: string,
    path: string,
    init: RequestInit,
    successMessage: string,
  ): Promise<boolean> {
    if (!scopeIsCurrent(scope)) {
      return false;
    }
    const controller = new AbortController();
    mutationAbortRefs.current.add(controller);
    setSavingKey(key);
    clearFeedback();
    try {
      const response = await caregiverFetch(path, scope.caregiverId, {
        ...init,
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(await errorMessage(response, "The change could not be saved."));
      }
      if (!scopeIsCurrent(scope)) {
        return false;
      }
      setMessage(successMessage);
      return true;
    } catch (requestError) {
      if (
        !(requestError instanceof DOMException && requestError.name === "AbortError") &&
        scopeIsCurrent(scope)
      ) {
        setError(requestError instanceof Error ? requestError.message : "Something went wrong.");
      }
      return false;
    } finally {
      mutationAbortRefs.current.delete(controller);
      if (scopeIsCurrent(scope)) {
        setSavingKey(null);
      }
    }
  }

  function reloadPatient(scope: PatientScope) {
    if (scopeIsCurrent(scope)) {
      setPatientRefreshToken((token) => token + 1);
    }
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const scope = currentPatientScope();
    if (!scope) return;
    const baseUrl = `${API_URL}/api/caregiver/patients/${scope.patientId}`;
    const saved = await sendMutation(
      scope,
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
      "Profile information saved.",
    );
    if (saved) {
      reloadPatient(scope);
    }
  }

  async function addPerson(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const scope = currentPatientScope();
    if (!scope) return;
    const baseUrl = `${API_URL}/api/caregiver/patients/${scope.patientId}`;
    const saved = await sendMutation(
      scope,
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
      reloadPatient(scope);
    }
  }

  async function savePerson(person: Person) {
    const scope = currentPatientScope();
    if (!scope) return;
    const baseUrl = `${API_URL}/api/caregiver/patients/${scope.patientId}`;
    const saved = await sendMutation(
      scope,
      `person-${person.id}`,
      `${baseUrl}/people/${person.id}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: person.name, relationship: person.relationship }),
      },
      "Person updated.",
    );
    if (saved) reloadPatient(scope);
  }

  async function deletePerson(person: Person) {
    const scope = currentPatientScope();
    if (!scope) return;
    const baseUrl = `${API_URL}/api/caregiver/patients/${scope.patientId}`;
    const deleted = await sendMutation(
      scope,
      `person-delete-${person.id}`,
      `${baseUrl}/people/${person.id}`,
      { method: "DELETE" },
      "Person deleted.",
    );
    if (deleted) reloadPatient(scope);
  }

  async function enrollFace(person: Person) {
    const scope = currentPatientScope();
    if (!scope) return;
    const baseUrl = `${API_URL}/api/caregiver/patients/${scope.patientId}`;
    const file = faceFiles[person.id];
    if (!file) {
      clearFeedback();
      setError("Choose a reference photo before enrolling a face.");
      return;
    }
    const formData = new FormData();
    formData.append("image", file);
    const saved = await sendMutation(
      scope,
      `face-${person.id}`,
      `${baseUrl}/people/${person.id}/face`,
      { method: "POST", body: formData },
      person.face_enrolled ? "Face reference replaced." : "Face reference enrolled.",
    );
    if (saved) {
      setFaceFiles((files) => ({ ...files, [person.id]: null }));
      reloadPatient(scope);
    }
  }

  async function removeFace(person: Person) {
    const scope = currentPatientScope();
    if (!scope) return;
    const baseUrl = `${API_URL}/api/caregiver/patients/${scope.patientId}`;
    const deleted = await sendMutation(
      scope,
      `face-remove-${person.id}`,
      `${baseUrl}/people/${person.id}/face`,
      { method: "DELETE" },
      "Face reference removed.",
    );
    if (deleted) {
      setFaceFiles((files) => ({ ...files, [person.id]: null }));
      reloadPatient(scope);
    }
  }

  async function addObject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const scope = currentPatientScope();
    if (!scope) return;
    const baseUrl = `${API_URL}/api/caregiver/patients/${scope.patientId}`;
    const saved = await sendMutation(
      scope,
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
      reloadPatient(scope);
    }
  }

  async function saveObject(item: ImportantObject) {
    const scope = currentPatientScope();
    if (!scope) return;
    const baseUrl = `${API_URL}/api/caregiver/patients/${scope.patientId}`;
    const saved = await sendMutation(
      scope,
      `object-${item.id}`,
      `${baseUrl}/objects/${item.id}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: item.name, notes: item.notes }),
      },
      "Important object updated.",
    );
    if (saved) reloadPatient(scope);
  }

  async function deleteObject(item: ImportantObject) {
    const scope = currentPatientScope();
    if (!scope) return;
    const baseUrl = `${API_URL}/api/caregiver/patients/${scope.patientId}`;
    const deleted = await sendMutation(
      scope,
      `object-delete-${item.id}`,
      `${baseUrl}/objects/${item.id}`,
      { method: "DELETE" },
      "Important object deleted.",
    );
    if (deleted) reloadPatient(scope);
  }

  async function addScheduleItem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const scope = currentPatientScope();
    if (!scope) return;
    const baseUrl = `${API_URL}/api/caregiver/patients/${scope.patientId}`;
    const saved = await sendMutation(
      scope,
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
      reloadPatient(scope);
    }
  }

  async function saveScheduleItem(item: ScheduleItem) {
    const scope = currentPatientScope();
    if (!scope) return;
    const baseUrl = `${API_URL}/api/caregiver/patients/${scope.patientId}`;
    const saved = await sendMutation(
      scope,
      `schedule-${item.id}`,
      `${baseUrl}/schedule/${item.id}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: item.title, scheduled_at: item.scheduled_at }),
      },
      "Schedule item updated.",
    );
    if (saved) reloadPatient(scope);
  }

  async function deleteScheduleItem(item: ScheduleItem) {
    const scope = currentPatientScope();
    if (!scope) return;
    const baseUrl = `${API_URL}/api/caregiver/patients/${scope.patientId}`;
    const deleted = await sendMutation(
      scope,
      `schedule-delete-${item.id}`,
      `${baseUrl}/schedule/${item.id}`,
      { method: "DELETE" },
      "Schedule item deleted.",
    );
    if (deleted) reloadPatient(scope);
  }

  async function addNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const scope = currentPatientScope();
    if (!scope) return;
    const baseUrl = `${API_URL}/api/caregiver/patients/${scope.patientId}`;
    const saved = await sendMutation(
      scope,
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
      reloadPatient(scope);
    }
  }

  async function deleteNote(note: CaregiverNote) {
    const scope = currentPatientScope();
    if (!scope) return;
    const baseUrl = `${API_URL}/api/caregiver/patients/${scope.patientId}`;
    const deleted = await sendMutation(
      scope,
      `note-delete-${note.id}`,
      `${baseUrl}/notes/${note.id}`,
      { method: "DELETE" },
      "Caregiver note deleted.",
    );
    if (deleted) reloadPatient(scope);
  }

  function renderProfile() {
    if (!profile) return null;
    return (
      <form className="caregiver-form" onSubmit={saveProfile}>
        <p className="caregiver-muted">
          These fields are stored with the demo profile. Response style, bio, and home context do not currently change
          wearer answers or cues.
        </p>
        <div className="caregiver-form-grid">
          <label>
            <span>Preferred name</span>
            <input
              type="text"
              value={profileForm.preferred_name}
              disabled={!canManageProfile || savingKey !== null}
              onChange={(event) => setProfileForm({ ...profileForm, preferred_name: event.target.value })}
            />
          </label>
          <label>
            <span>Response style <em>(not applied yet)</em></span>
            <input
              type="text"
              value={profileForm.response_style}
              placeholder="e.g. short, calm"
              disabled={!canManageProfile || savingKey !== null}
              onChange={(event) => setProfileForm({ ...profileForm, response_style: event.target.value })}
            />
          </label>
        </div>
        <label>
          <span>Short bio <em>(optional, stored only)</em></span>
          <textarea
            value={profileForm.short_bio}
            rows={2}
            disabled={!canManageProfile || savingKey !== null}
            onChange={(event) => setProfileForm({ ...profileForm, short_bio: event.target.value })}
          />
        </label>
        <label>
          <span>Home context <em>(optional, stored only)</em></span>
          <textarea
            value={profileForm.home_context}
            rows={2}
            disabled={!canManageProfile || savingKey !== null}
            onChange={(event) => setProfileForm({ ...profileForm, home_context: event.target.value })}
          />
        </label>
        <button className="primary-button" type="submit" disabled={!canManageProfile || savingKey !== null}>
          {savingKey === "profile" ? "Saving..." : "Save profile"}
        </button>
      </form>
    );
  }

  function renderPeople() {
    return (
      <div className="caregiver-section-stack">
        <p className="caregiver-muted">
          A person&apos;s saved name and relationship can answer questions such as “Who is Sarah?” Camera matching is
          optional and works only after a separate reference photo is enrolled.
        </p>
        <form className="caregiver-inline-form" onSubmit={addPerson}>
          <label>
            <span>Name</span>
            <input value={personName} onChange={(event) => setPersonName(event.target.value)} placeholder="Sarah" disabled={!canManagePeople || savingKey !== null} />
          </label>
          <label>
            <span>Relationship</span>
            <input
              value={personRelationship}
              onChange={(event) => setPersonRelationship(event.target.value)}
              placeholder="Daughter"
              disabled={!canManagePeople || savingKey !== null}
            />
          </label>
          <button className="secondary-button" type="submit" disabled={!canManagePeople || savingKey !== null}>
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
                  disabled={!canManagePeople || savingKey !== null}
                  onChange={(event) =>
                    setPeople(people.map((item) => (item.id === person.id ? { ...item, name: event.target.value } : item)))
                  }
                />
                <input
                  aria-label="Relationship"
                  value={person.relationship}
                  disabled={!canManagePeople || savingKey !== null}
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
                <button className="text-button" type="button" onClick={() => void savePerson(person)} disabled={!canManagePeople || savingKey !== null}>
                  Save
                </button>
                <button className="danger-button" type="button" onClick={() => void deletePerson(person)} disabled={!canManagePeople || savingKey !== null}>
                  Delete
                </button>
              </div>
              <div className="face-enrollment" aria-label={`${person.name} optional face enrollment`}>
                <div className="face-enrollment-status">
                  <span className="record-meta">Optional face check</span>
                  <strong>{person.face_enrolled ? "Reference enrolled" : "No reference enrolled"}</strong>
                </div>
                <label className="face-file-picker">
                  <span>{person.face_enrolled ? "Replace reference photo" : "Choose reference photo"}</span>
                  <input
                    type="file"
                    accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
                    disabled={!canManagePeople || savingKey !== null}
                    onChange={(event) =>
                      setFaceFiles((files) => ({ ...files, [person.id]: event.target.files?.[0] ?? null }))
                    }
                  />
                </label>
                <div className="face-enrollment-actions">
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => void enrollFace(person)}
                    disabled={!canManagePeople || savingKey !== null || !faceFiles[person.id]}
                  >
                    {person.face_enrolled ? "Replace reference" : "Enroll reference"}
                  </button>
                  {person.face_enrolled && (
                    <button
                      className="danger-button"
                      type="button"
                      onClick={() => void removeFace(person)}
                      disabled={!canManagePeople || savingKey !== null}
                    >
                      Remove reference
                    </button>
                  )}
                </div>
              </div>
            </article>
          ))}
          {people.length === 0 && <p className="caregiver-muted">No people have been added to this profile.</p>}
        </div>
      </div>
    );
  }

  function renderObjects() {
    return (
      <div className="caregiver-section-stack">
        <p className="caregiver-muted">
          An important-object entry marks what may matter for optional cues. It is not a last-seen record; that requires
          a saved memory containing the object.
        </p>
        <form className="caregiver-inline-form" onSubmit={addObject}>
          <label>
            <span>Object name</span>
            <input value={objectName} onChange={(event) => setObjectName(event.target.value)} placeholder="Keys" disabled={!canManageObjects || savingKey !== null} />
          </label>
          <label>
            <span>Notes <em>(optional)</em></span>
            <input
              value={objectNotes}
              onChange={(event) => setObjectNotes(event.target.value)}
              placeholder="Optional description for caregivers"
              disabled={!canManageObjects || savingKey !== null}
            />
          </label>
          <button className="secondary-button" type="submit" disabled={!canManageObjects || savingKey !== null}>
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
                  disabled={!canManageObjects || savingKey !== null}
                  onChange={(event) =>
                    setObjects(objects.map((object) => (object.id === item.id ? { ...object, name: event.target.value } : object)))
                  }
                />
                <input
                  aria-label="Important object notes"
                  value={item.notes ?? ""}
                  disabled={!canManageObjects || savingKey !== null}
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
                <button className="text-button" type="button" onClick={() => void saveObject(item)} disabled={!canManageObjects || savingKey !== null}>
                  Save
                </button>
                <button className="danger-button" type="button" onClick={() => void deleteObject(item)} disabled={!canManageObjects || savingKey !== null}>
                  Delete
                </button>
              </div>
            </article>
          ))}
          {objects.length === 0 && <p className="caregiver-muted">No important objects have been added.</p>}
        </div>
      </div>
    );
  }

  function renderSchedule() {
    return (
      <div className="caregiver-section-stack">
        <p className="caregiver-muted">
          Saved schedule items can answer today questions and may appear as optional upcoming cues.
        </p>
        <form className="caregiver-inline-form" onSubmit={addScheduleItem}>
          <label>
            <span>Title</span>
            <input value={scheduleTitle} onChange={(event) => setScheduleTitle(event.target.value)} placeholder="Sarah visits" disabled={!canManageSchedule || savingKey !== null} />
          </label>
          <label>
            <span>Date and time</span>
            <input type="datetime-local" value={scheduleAt} onChange={(event) => setScheduleAt(event.target.value)} disabled={!canManageSchedule || savingKey !== null} />
          </label>
          <button className="secondary-button" type="submit" disabled={!canManageSchedule || savingKey !== null}>
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
                  disabled={!canManageSchedule || savingKey !== null}
                  onChange={(event) =>
                    setSchedule(schedule.map((entry) => (entry.id === item.id ? { ...entry, title: event.target.value } : entry)))
                  }
                />
                <input
                  aria-label="Schedule date and time"
                  type="datetime-local"
                  value={dateTimeInputValue(item.scheduled_at)}
                  disabled={!canManageSchedule || savingKey !== null}
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
                <button className="text-button" type="button" onClick={() => void saveScheduleItem(item)} disabled={!canManageSchedule || savingKey !== null}>
                  Save
                </button>
                <button className="danger-button" type="button" onClick={() => void deleteScheduleItem(item)} disabled={!canManageSchedule || savingKey !== null}>
                  Delete
                </button>
              </div>
            </article>
          ))}
          {schedule.length === 0 && <p className="caregiver-muted">No schedule items have been added.</p>}
        </div>
      </div>
    );
  }

  function renderNotes() {
    return (
      <div className="caregiver-section-stack">
        <p className="caregiver-muted">
          Notes are stored for caregiver reference. They are not currently included in wearer answers or cues.
        </p>
        <form className="caregiver-note-form" onSubmit={addNote}>
          <label>
            <span>Caregiver note</span>
            <textarea value={noteText} onChange={(event) => setNoteText(event.target.value)} rows={3} placeholder="A short note for other caregivers" disabled={!canManageNotes || savingKey !== null} />
          </label>
          <button className="secondary-button" type="submit" disabled={!canManageNotes || savingKey !== null}>
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
              <button className="danger-button" type="button" onClick={() => void deleteNote(note)} disabled={!canManageNotes || savingKey !== null}>
                Delete
              </button>
            </article>
          ))}
          {notes.length === 0 && <p className="caregiver-muted">No caregiver notes have been added.</p>}
        </div>
      </div>
    );
  }

  return (
    <main className="caregiver-page-shell caregiver-experience">
      <SiteNav />
      <section className="caregiver-card" aria-labelledby="caregiver-title">
        <header className="caregiver-header">
          <div>
            <p className="eyebrow">Caregiver space</p>
            <h1 id="caregiver-title">Caregiver setup</h1>
            <p className="subtitle">Review setup information for a linked demo profile.</p>
          </div>
          <div className="caregiver-identity">
            <label>
              <span>Demo caregiver</span>
              <select value={activeCaregiverId} onChange={handleCaregiverChange}>
                {CAREGIVERS.map((caregiver) => (
                  <option key={caregiver.id} value={caregiver.id}>
                    {caregiver.name}
                  </option>
                ))}
              </select>
              <small>Simulated identity for local testing — not a secure account.</small>
            </label>
          </div>
        </header>

        <div className="caregiver-notice" role="note">
          Only profiles linked to the selected demo caregiver appear here. Production authentication, consent workflows,
          invitations, and medical records are not included.
        </div>

        <div className="caregiver-layout">
          <aside className="patient-list-panel" aria-labelledby="patient-list-title">
            <p className="section-kicker">Linked profiles</p>
            <h2 id="patient-list-title">Profiles available to {activeCaregiver.name}</h2>
            {isLoadingPatients ? (
              <p className="caregiver-muted">Loading profiles…</p>
            ) : patientListError ? (
              <div role="alert">
                <p className="caregiver-muted">Couldn’t load profiles. Try again.</p>
                <button className="text-button" type="button" onClick={retryPatientList}>
                  Retry
                </button>
                <details className="debug-details caregiver-list-debug">
                  <summary>Development details</summary>
                  <p>{patientListError}</p>
                </details>
              </div>
            ) : patients.length > 0 ? (
              <div className="patient-list">
                {patients.map((patient) => (
                  <button
                    className={`patient-button ${selectedPatientId === patient.user_id ? "is-selected" : ""}`}
                    key={patient.user_id}
                    type="button"
                    onClick={() => selectPatient(patient.user_id)}
                  >
                    <strong>{patient.preferred_name ?? patient.name}</strong>
                    <span>{patient.name}</span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="caregiver-muted">No profiles are linked to this demo caregiver.</p>
            )}
          </aside>

          <section className="management-panel" aria-labelledby="management-title">
            {isLoadingPatients || patientListError ? (
              <div className="management-empty">
                <p className="section-kicker">{patientListError ? "Profiles unavailable" : "Linked profiles"}</p>
                <h2 id="management-title">{patientListError ? "Couldn’t load profiles." : "Loading profiles…"}</h2>
                {patientListError && <p>Use Retry in the profile list to try the request again.</p>}
              </div>
            ) : selectedPatient ? (
              <>
                <div className="management-heading">
                  <div>
                    <p className="section-kicker">Selected profile</p>
                    <h2 id="management-title">{selectedPatient.preferred_name ?? selectedPatient.name}&apos;s setup</h2>
                  </div>
                  <span className="access-badge">
                    {activeCaregiver.name} · {selectedPatient.role === "primary" ? "linked demo access" : "read-only demo access"}
                  </span>
                </div>
                <nav className="management-tabs" aria-label="Profile setup sections">
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
                  <p className="caregiver-muted management-loading">Loading profile information...</p>
                ) : !profile ? (
                  <p className="caregiver-muted management-loading">
                    Profile information is unavailable. Select the profile again to retry.
                  </p>
                ) : (
                  <div className="management-section">
                    {!activeTabCanManage && (
                      <p className="caregiver-read-only" role="note">
                        This caregiver can view this section but cannot make changes.
                      </p>
                    )}
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
                <p className="section-kicker">Choose a profile</p>
                <h2>Select a linked profile to begin.</h2>
                <p>Choose a profile to review the information available to this demo caregiver.</p>
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
