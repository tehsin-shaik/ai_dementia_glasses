"""Deterministic demo data for local development."""

from datetime import date, datetime, time

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .models import (
    Caregiver,
    CaregiverNote,
    CaregiverPatientAccess,
    ImportantObject,
    Memory,
    ObjectObservation,
    PatientProfile,
    Person,
    PersonFaceEnrollment,
    ScheduleItem,
    User,
)


def seed_demo_data(db: Session) -> dict[str, int | list[int]]:
    """Reset application data and insert isolated patients and caregivers."""

    # Delete children first so this remains safe when foreign keys are enforced.
    for model in (
        CaregiverNote,
        CaregiverPatientAccess,
        ImportantObject,
        ScheduleItem,
        PersonFaceEnrollment,
        Person,
        ObjectObservation,
        Memory,
        PatientProfile,
        Caregiver,
        User,
    ):
        db.execute(delete(model))

    today = date.today()
    patient_definitions = [
        {
            "name": "Alex",
            "profile": {
                "preferred_name": "Alex",
                "short_bio": None,
                "home_context": "Lives at home",
                "response_style": "Short, calm reminders",
            },
            "memory_rows": [
                (time(10, 0), "Kitchen", "making tea", "Alex was making tea in the kitchen."),
                (time(10, 10), "Living room", "reading", "Alex was reading in the living room."),
                (
                    time(10, 18),
                    "Kitchen",
                    "keys visible on kitchen counter",
                    "Alex's keys were visible on the kitchen counter.",
                ),
                (time(10, 25), "Hallway", "preparing to leave", "Alex was preparing to leave."),
            ],
            "person": ("Sarah", "Daughter"),
            "schedule": [("Sarah visits", time(15, 30)), ("Dinner", time(18, 0))],
            "objects": [("keys", "Usually carried when leaving home"), ("wallet", None)],
            "key_location": "kitchen counter",
            "note": "Alex often asks about Sarah before visits.",
        },
        {
            "name": "Jordan",
            "profile": {
                "preferred_name": "Jordan",
                "short_bio": None,
                "home_context": None,
                "response_style": "Brief factual cues",
            },
            "memory_rows": [
                (time(10, 5), "Bedroom", "watering plants", "Jordan was watering plants in the bedroom."),
                (time(10, 15), "Bedroom", "packing a bag", "Jordan was packing a bag in the bedroom."),
                (
                    time(10, 24),
                    "Bedroom",
                    "keys visible on bedroom desk",
                    "Jordan's keys were visible on the bedroom desk.",
                ),
                (time(10, 32), "Hallway", "getting ready to leave", "Jordan was getting ready to leave."),
            ],
            "person": ("Sarah", "Neighbor"),
            "schedule": [("Michael calls", time(16, 0)), ("Dinner", time(18, 30))],
            "objects": [("keys", "Usually kept near the bedroom desk"), ("phone", None)],
            "key_location": "bedroom desk",
            "note": "Jordan prefers brief factual reminders.",
        },
    ]

    users: list[User] = []
    memories_by_user: list[list[Memory]] = []
    for patient in patient_definitions:
        user = User(name=patient["name"])
        db.add(user)
        db.flush()
        users.append(user)

        db.add(PatientProfile(user_id=user.id, **patient["profile"]))
        memories: list[Memory] = []
        for memory_time, location, activity, description in patient["memory_rows"]:
            memory = Memory(
                user_id=user.id,
                timestamp=datetime.combine(today, memory_time),
                location=location,
                activity=activity,
                description=description,
            )
            db.add(memory)
            db.flush()
            memories.append(memory)
        memories_by_user.append(memories)

        db.add(
            ObjectObservation(
                user_id=user.id,
                object_name="keys",
                location=patient["key_location"],
                observed_at=memories[2].timestamp,
                memory_id=memories[2].id,
            )
        )
        person_name, relationship = patient["person"]
        db.add(Person(user_id=user.id, name=person_name, relationship=relationship))
        db.add_all(
            [
                ScheduleItem(
                    user_id=user.id,
                    title=title,
                    scheduled_at=datetime.combine(today, schedule_time),
                )
                for title, schedule_time in patient["schedule"]
            ]
        )
        db.add_all(
            [ImportantObject(user_id=user.id, name=name, notes=notes) for name, notes in patient["objects"]]
        )

    db.flush()
    caregivers = [Caregiver(name="Maya"), Caregiver(name="Sam"), Caregiver(name="Taylor")]
    db.add_all(caregivers)
    db.flush()
    maya, sam, taylor = caregivers
    alex, jordan = users
    access_rows = [
        CaregiverPatientAccess(
            caregiver_id=maya.id,
            patient_user_id=alex.id,
            role="primary",
            can_manage_people=True,
            can_manage_schedule=True,
            can_manage_objects=True,
            can_manage_notes=True,
        ),
        CaregiverPatientAccess(
            caregiver_id=sam.id,
            patient_user_id=jordan.id,
            role="primary",
            can_manage_people=True,
            can_manage_schedule=True,
            can_manage_objects=True,
            can_manage_notes=True,
        ),
        CaregiverPatientAccess(
            caregiver_id=taylor.id,
            patient_user_id=alex.id,
            role="viewer",
        ),
    ]
    db.add_all(access_rows)
    db.add_all(
        [
            CaregiverNote(
                user_id=alex.id,
                caregiver_id=maya.id,
                note=patient_definitions[0]["note"],
                created_at=datetime.combine(today, time(9, 0)),
            ),
            CaregiverNote(
                user_id=jordan.id,
                caregiver_id=sam.id,
                note=patient_definitions[1]["note"],
                created_at=datetime.combine(today, time(9, 5)),
            ),
        ]
    )
    db.commit()

    return {
        "user_ids": [user.id for user in users],
        "user_count": len(users),
        "caregiver_ids": [caregiver.id for caregiver in caregivers],
        "caregiver_count": len(caregivers),
        "access_count": len(access_rows),
        "profile_count": len(users),
        "memory_count": sum(len(memories) for memories in memories_by_user),
        "observation_count": len(users),
        "person_count": len(users),
        "schedule_count": len(users) * 2,
        "important_object_count": len(users) * 2,
        "note_count": len(users),
    }
