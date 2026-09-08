"""Deterministic demo data for local development."""

from datetime import date, datetime, time

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .models import Memory, ObjectObservation, Person, ScheduleItem, User


def seed_demo_data(db: Session) -> dict[str, int | list[int]]:
    """Reset application data and insert two repeatable isolated demo users."""

    # Delete children first so this remains safe when foreign keys are enforced.
    for model in (ScheduleItem, Person, ObjectObservation, Memory, User):
        db.execute(delete(model))

    today = date.today()
    demo_users = [
        {
            "name": "Alex",
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
            "key_location": "kitchen counter",
        },
        {
            "name": "Jordan",
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
            "key_location": "bedroom desk",
        },
    ]

    users: list[User] = []
    for demo_user in demo_users:
        user = User(name=demo_user["name"])
        db.add(user)
        db.flush()
        users.append(user)

        memories: list[Memory] = []
        for memory_time, location, activity, description in demo_user["memory_rows"]:
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
                location=demo_user["key_location"],
                observed_at=memories[2].timestamp,
                memory_id=memories[2].id,
            )
        )
        person_name, relationship = demo_user["person"]
        db.add(Person(user_id=user.id, name=person_name, relationship=relationship))
        db.add_all(
            [
                ScheduleItem(
                    user_id=user.id,
                    title=title,
                    scheduled_at=datetime.combine(today, schedule_time),
                )
                for title, schedule_time in demo_user["schedule"]
            ]
        )
    db.commit()

    return {
        "user_ids": [user.id for user in users],
        "user_count": len(users),
        "memory_count": len(demo_users) * 4,
        "observation_count": len(demo_users),
        "person_count": len(demo_users),
        "schedule_count": len(demo_users) * 2,
    }
