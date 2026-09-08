"""Deterministic demo data for local development."""

from datetime import date, datetime, time

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .models import Memory, ObjectObservation, Person, ScheduleItem, User


def seed_demo_data(db: Session) -> dict[str, int]:
    """Reset application data and insert one repeatable demo user."""

    # Delete children first so this remains safe when foreign keys are enforced.
    for model in (ScheduleItem, Person, ObjectObservation, Memory, User):
        db.execute(delete(model))

    user = User(name="Demo User")
    db.add(user)
    db.flush()

    today = date.today()
    memory_rows = [
        (time(10, 0), "Kitchen", "making tea", "The user was making tea in the kitchen."),
        (time(10, 10), "Living room", "reading", "The user was reading in the living room."),
        (
            time(10, 18),
            "Kitchen",
            "keys visible on kitchen counter",
            "The user's keys were visible on the kitchen counter.",
        ),
        (time(10, 25), "Hallway", "preparing to leave", "The user was preparing to leave."),
    ]

    memories: list[Memory] = []
    for memory_time, location, activity, description in memory_rows:
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

    db.add(
        ObjectObservation(
            user_id=user.id,
            object_name="keys",
            location="kitchen counter",
            observed_at=memories[2].timestamp,
            memory_id=memories[2].id,
        )
    )
    db.add(Person(user_id=user.id, name="Sarah", relationship="Daughter"))
    db.add_all(
        [
            ScheduleItem(
                user_id=user.id,
                title="Sarah visits",
                scheduled_at=datetime.combine(today, time(15, 30)),
            ),
            ScheduleItem(
                user_id=user.id,
                title="Dinner",
                scheduled_at=datetime.combine(today, time(18, 0)),
            ),
        ]
    )
    db.commit()

    return {
        "user_id": user.id,
        "memory_count": len(memories),
        "observation_count": 1,
        "person_count": 1,
        "schedule_count": 2,
    }
