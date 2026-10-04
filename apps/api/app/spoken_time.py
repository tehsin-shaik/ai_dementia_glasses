"""Rewrite spoken clock times ("ten thirty AM", "الساعة العاشرة") into digit form.

The rewritten text is only used for clock-time parsing; a word hour is
rewritten only in an unambiguous time context, so stray number words such as
"at one point" are left alone.
"""

import re

_UNITS = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
_TEENS = [
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
]
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50}

HOUR_WORDS = {word: value for value, word in enumerate(_UNITS + _TEENS[:3], start=1)}

MINUTE_WORDS: dict[str, int] = {}
for _value, _word in enumerate(_UNITS, start=1):
    MINUTE_WORDS[f"oh {_word}"] = _value
    MINUTE_WORDS[f"o {_word}"] = _value
for _value, _word in enumerate(_TEENS, start=10):
    MINUTE_WORDS[_word] = _value
for _tens_word, _tens in _TENS.items():
    MINUTE_WORDS[_tens_word] = _tens
    for _value, _word in enumerate(_UNITS, start=1):
        MINUTE_WORDS[f"{_tens_word} {_word}"] = _tens + _value
OFFSET_WORDS = {**{word: value for value, word in enumerate(_UNITS, start=1)}, **MINUTE_WORDS}
OFFSET_WORDS.update({"half": 30, "quarter": 15})


def _alternation(words) -> str:
    return "|".join(re.escape(word) for word in sorted(words, key=len, reverse=True))


_HOUR = _alternation(HOUR_WORDS)
_MINUTE = _alternation(MINUTE_WORDS)
_OFFSET = _alternation(OFFSET_WORDS)
_MERIDIEM_EN = (
    r"a\.?\s?m\b\.?|p\.?\s?m\b\.?|in the morning|this morning|in the afternoon|this afternoon"
    r"|in the evening|this evening|at night|tonight"
)
_CLAUSE_END = r"(?=\s*(?:$|[?.!,]|today\b|yesterday\b|this\b|in the\b|tonight\b))"

EN_NOON = re.compile(r"\b(at|around|about)\s+(noon|midday|midnight)\b")
EN_OFFSET = re.compile(
    rf"\b(?:(at|around|about)\s+)?(?:a\s+)?({_OFFSET})(?:\s+minutes?)?\s+(past|after|to|till)\s+({_HOUR})\b"
    rf"(?:\s*({_MERIDIEM_EN}))?"
)
EN_DIGIT_OCLOCK = re.compile(r"(?<!\d)(\d{1,2})\s*oclock\b")
EN_HOUR = re.compile(
    rf"\b(?:(at|around|about)\s+)?({_HOUR})(?:\s+({_MINUTE}))?(\s+oclock)?(?:\s*({_MERIDIEM_EN}))?"
    rf"(?![\w:])"
)

AR_HOURS = {
    "الواحده": 1, "الثانيه": 2, "الثالثه": 3, "الرابعه": 4, "الخامسه": 5, "السادسه": 6,
    "السابعه": 7, "الثامنه": 8, "التاسعه": 9, "العاشره": 10,
    "الحاديه عشر": 11, "الحاديه عشره": 11, "الثانيه عشر": 12, "الثانيه عشره": 12,
}
AR_MINUTES = {
    "والنصف": 30, "و نصف": 30, "ونصف": 30,
    "والربع": 15, "و ربع": 15, "وربع": 15,
    "والثلث": 20, "و ثلث": 20, "وثلث": 20,
    "الا ربع": -15, "الا ربعا": -15, "الا الربع": -15,
    "الا ثلث": -20, "الا الثلث": -20,
}
AR_AM = {"صباحا", "صباح", "الصباح", "في الصباح", "فجرا"}
AR_PM = {"مساء", "المساء", "في المساء", "ظهرا", "الظهر", "بعد الظهر", "عصرا", "العصر", "ليلا", "الليل", "في الليل"}
_AR_HOUR = _alternation(AR_HOURS)
_AR_MINUTE = _alternation(AR_MINUTES)
_AR_MERIDIEM = _alternation(AR_AM | AR_PM)
AR_HOUR = re.compile(
    rf"(?:(الساعه)\s+)?({_AR_HOUR})(?:\s+({_AR_MINUTE}))?(?:\s+({_AR_MERIDIEM}))?(?!\w)"
)
AR_NOON = re.compile(r"(?:الساعه\s+)?(?:عند|وقت)\s+(الظهر|الظهيره|منتصف الليل)(?!\w)|منتصف الليل")

TIME_CUE = re.compile(
    rf"\boclock\b|\b(?:noon|midday|midnight)\b|\ba\.m\b|\bp\.m\b"
    rf"|(?:\d|\b(?:{_HOUR}|{_MINUTE}))\s*(?:a\.?\s?m|p\.?\s?m)\b"
    r"|الساعه",
)

_ARABIC_DIACRITICS = re.compile("[\u064b-\u0652\u0640]")


def normalize_arabic(text: str) -> str:
    text = _ARABIC_DIACRITICS.sub("", text)
    return text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").replace("ى", "ي")


def _clock(hour: int, minute: int, marker: str) -> str:
    return f"{hour}:{minute:02d}{' ' + marker if marker else ''}"


def _english_marker(meridiem: str | None) -> str:
    if not meridiem:
        return ""
    compact = meridiem.replace(".", "").replace(" ", "")
    if compact in {"am", "inthemorning", "thismorning"}:
        return "am"
    return "pm"


def _offset_time(match: re.Match) -> str:
    intro, offset, direction, hour_word, meridiem = match.groups()
    hour, minutes = HOUR_WORDS[hour_word], OFFSET_WORDS[offset]
    if minutes >= 60:
        return match.group(0)
    if direction in {"to", "till"}:
        hour, minutes = (hour - 2) % 12 + 1, 60 - minutes
    return f"{intro + ' ' if intro else ''}{_clock(hour, minutes, _english_marker(meridiem))}"


def _hour_time(match: re.Match) -> str:
    intro, hour_word, minute_word, oclock, meridiem = match.groups()
    if not (minute_word or oclock or meridiem):
        if not intro or re.match(_CLAUSE_END, match.string[match.end():]) is None:
            return match.group(0)
    minute = MINUTE_WORDS[minute_word] if minute_word else 0
    clock = _clock(HOUR_WORDS[hour_word], minute, _english_marker(meridiem))
    return f"{intro + ' ' if intro else ''}{clock}"


def _arabic_time(match: re.Match) -> str:
    intro, hour_word, minute_word, meridiem = match.groups()
    if not (intro or meridiem):
        return match.group(0)
    if not (minute_word and meridiem) and re.match(r"\s+(?:و|الا\b)", match.string[match.end():]):
        return match.group(0)
    hour, minute = AR_HOURS[hour_word], AR_MINUTES.get(minute_word or "", 0)
    if minute < 0:
        hour, minute = (hour - 2) % 12 + 1, 60 + minute
    marker = ""
    if meridiem in AR_AM:
        marker = "صباحا"
    elif meridiem in {"ليلا", "الليل", "في الليل"} and hour == 12:
        marker = "صباحا"
    elif meridiem:
        marker = "مساء"
    return f"الساعه {_clock(hour, minute, marker)}"


def _arabic_noon(match: re.Match) -> str:
    return "الساعه 12:00 صباحا" if "منتصف" in match.group(0) else "الساعه 12:00 مساء"


def rewrite_spoken_times(question: str) -> str:
    """Lower-case, normalize Arabic letters, and turn spoken clock times into H:MM."""

    text = normalize_arabic(question.casefold().replace("’", "'"))
    text = re.sub(r"\bo'?\s?clock\b", "oclock", text)
    text = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", text)
    text = EN_NOON.sub(lambda m: f"{m.group(1)} 12:00 {'am' if m.group(2) == 'midnight' else 'pm'}", text)
    text = EN_OFFSET.sub(_offset_time, text)
    text = EN_DIGIT_OCLOCK.sub(lambda m: f"{m.group(1)}:00", text)
    text = EN_HOUR.sub(_hour_time, text)
    text = AR_NOON.sub(_arabic_noon, text)
    return AR_HOUR.sub(_arabic_time, text)


def mentions_a_clock_time(text: str) -> bool:
    """Whether rewritten text still asks about a clock time, resolved or not."""

    return TIME_CUE.search(text) is not None
