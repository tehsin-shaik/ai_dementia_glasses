import pytest

from app.query_service import asks_about_a_clock_time, clock_time_mention, detect_intent


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What was I doing at 10 AM?", (10, 0)),
        ("what was I doing at 10:00 a.m.", (10, 0)),
        ("what was I doing at 10 o'clock", (10, 0)),
        ("what was I doing at ten AM", (10, 0)),
        ("what was I doing at ten a.m.?", (10, 0)),
        ("what was I doing at ten?", (10, 0)),
        ("what was I doing at ten o’clock", (10, 0)),
        ("What was I doing at ten thirty a.m.?", (10, 30)),
        ("what was I doing at ten oh five", (10, 5)),
        ("what was I doing at eleven forty-five pm", (23, 45)),
        ("what was I doing at half past ten", (10, 30)),
        ("what was I doing at quarter to eleven", (10, 45)),
        ("what was I doing at twenty past ten", (10, 20)),
        ("what was I doing at ten fifteen in the morning", (10, 15)),
        ("What was I doing at seven in the evening?", (19, 0)),
        ("what was I doing at noon", (12, 0)),
        ("what was I doing at midnight", (0, 0)),
        ("ماذا كنت أفعل الساعة 10 صباحًا؟", (10, 0)),
        ("ماذا كنت افعل الساعه 10:00 صباحا", (10, 0)),
        ("ماذا كنت افعل الساعة ١٠ صباحًا", (10, 0)),
        ("ماذا كنت افعل الساعة العاشرة صباحا", (10, 0)),
        ("ماذا كنت افعل الساعه العاشره", (10, 0)),
        ("ماذا كنت أفعل الساعة العاشرة والنصف؟", (10, 30)),
        ("ماذا كنت أفعل الساعة العاشرة والربع", (10, 15)),
        ("ماذا كنت افعل الساعة الحادية عشرة إلا ربع", (10, 45)),
        ("ماذا كنت افعل الساعة الثانية عشرة ظهرا", (12, 0)),
        ("ماذا كنت افعل الساعة الثالثة عصرا", (15, 0)),
        ("ماذا كنت افعل الساعة السابعة مساءً", (19, 0)),
    ],
)
def test_numeric_and_spoken_clock_times_resolve(question: str, expected: tuple[int, int]) -> None:
    assert clock_time_mention(question) == expected
    assert asks_about_a_clock_time(question)
    assert detect_intent(question) == "recent_activity"


@pytest.mark.parametrize(
    "question",
    [
        "what was I doing at ten-ish o'clock",
        "what was I doing at thirteen AM",
        "ماذا كنت افعل الساعة الخامسة والعشرين",
        "ماذا كنت افعل الساعة العاشرة و 15 دقيقة",
        "ماذا كنت افعل الساعة",
    ],
)
def test_a_time_that_cannot_be_resolved_is_still_recognized_as_a_time_question(question: str) -> None:
    assert clock_time_mention(question) is None
    assert asks_about_a_clock_time(question)
    assert detect_intent(question) == "recent_activity"


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("What was I doing?", "recent_activity"),
        ("what was I doing at one point", "recent_activity"),
        ("What am I doing today?", "schedule"),
        ("What did I do today?", "day_summary"),
        ("Where are my keys?", "object_location"),
        ("Where did I put my two keys at ten?", "object_location"),
        ("ماذا كنت افعل", "recent_activity"),
        ("ماذا كنت افعل منذ ساعة", "recent_activity"),
        ("أين مفاتيحي؟", "object_location"),
    ],
)
def test_questions_without_a_clock_time_are_unchanged(question: str, intent: str) -> None:
    if "ten" not in question:
        assert clock_time_mention(question) is None
        assert not asks_about_a_clock_time(question)
    assert detect_intent(question) == intent
