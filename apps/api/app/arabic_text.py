"""Arabic wording for the English text that saved records usually contain.

Saved moments, people and schedule items are stored as entered (mostly
English). Arabic answers translate the phrases listed here and quote anything
else exactly as saved, so the answer never invents a translation.
"""

import re

PLACES = {
    "kitchen": "المطبخ",
    "kitchen counter": "طاولة المطبخ",
    "counter": "طاولة المطبخ",
    "living room": "غرفة المعيشة",
    "hallway": "الممر",
    "bedroom": "غرفة النوم",
    "bedroom desk": "مكتب غرفة النوم",
    "desk": "المكتب",
    "bathroom": "الحمّام",
    "dining table": "طاولة الطعام",
    "table": "الطاولة",
    "dark table": "الطاولة الداكنة",
    "front door": "الباب الأمامي",
    "entrance": "المدخل",
    "sofa": "الأريكة",
    "couch": "الأريكة",
    "nightstand": "الطاولة الجانبية",
    "garden": "الحديقة",
}

OBJECTS = {
    "keys": "المفاتيح",
    "key": "المفتاح",
    "wallet": "المحفظة",
    "phone": "الهاتف",
    "glasses": "النظارة",
    "bag": "الحقيبة",
    "book": "الكتاب",
    "kettle": "الإبريق",
    "remote": "جهاز التحكم",
    "watch": "الساعة",
    "umbrella": "المظلة",
}

YOUR_OBJECTS = {
    "keys": "مفاتيحك",
    "key": "مفتاحك",
    "wallet": "محفظتك",
    "phone": "هاتفك",
    "glasses": "نظارتك",
    "bag": "حقيبتك",
    "book": "كتابك",
    "remote": "جهاز التحكم",
    "watch": "ساعتك",
    "umbrella": "مظلتك",
}

ACTIVITIES = {
    "making tea": "تحضير الشاي",
    "reading": "القراءة",
    "preparing to leave": "الاستعداد للخروج",
    "getting ready to leave": "الاستعداد للخروج",
    "watering plants": "سقي النباتات",
    "packing a bag": "تجهيز حقيبة",
    "having breakfast": "تناول الفطور",
    "eating breakfast": "تناول الفطور",
    "having lunch": "تناول الغداء",
    "having dinner": "تناول العشاء",
    "watching tv": "مشاهدة التلفاز",
    "cooking": "الطبخ",
    "resting": "الاستراحة",
    "walking": "المشي",
}

NAMES = {
    "sarah": "سارة",
    "michael": "مايكل",
    "omar": "عمر",
    "maya": "مايا",
    "alex": "أليكس",
    "jordan": "جوردان",
    "sam": "سام",
    "taylor": "تايلور",
}

RELATIONSHIPS = {
    "daughter": "ابنتك",
    "son": "ابنك",
    "wife": "زوجتك",
    "husband": "زوجك",
    "mother": "والدتك",
    "father": "والدك",
    "sister": "أختك",
    "brother": "أخوك",
    "granddaughter": "حفيدتك",
    "grandson": "حفيدك",
    "friend": "صديقك",
    "neighbor": "جارك",
    "neighbour": "جارك",
    "caregiver": "مقدّم الرعاية",
    "doctor": "طبيبك",
}

SCHEDULE_TITLES = {
    "breakfast": "الفطور",
    "lunch": "الغداء",
    "dinner": "العشاء",
}

VISIBLE_ON = re.compile(r"^(?P<object>.+?) (?:visible|left|placed) on (?:the )?(?P<place>.+)$")
VISITS = re.compile(r"^(?P<name>\S+) visits$")
CALLS = re.compile(r"^(?P<name>\S+) calls$")


def _key(text: str) -> str:
    key = " ".join(text.casefold().strip().rstrip(".").split())
    return re.sub(r"^(?:the|your|my) ", "", key)


def quoted(text: str) -> str:
    """Saved text that has no known translation, marked as quoted."""

    return f"«{text.strip().rstrip('.')}»"


def place(text: str) -> str:
    return PLACES.get(_key(text)) or quoted(text)


def your_object(text: str) -> str:
    return YOUR_OBJECTS.get(_key(text)) or quoted(text)


def name(text: str) -> str:
    return NAMES.get(_key(text)) or text.strip()


def relationship(text: str) -> str:
    return RELATIONSHIPS.get(_key(text)) or quoted(text)


def activity(text: str) -> str:
    key = _key(text)
    if key in ACTIVITIES:
        return ACTIVITIES[key]
    match = VISIBLE_ON.match(key)
    if match and match["object"] in OBJECTS and match["place"] in PLACES:
        return f"{OBJECTS[match['object']]} على {PLACES[match['place']]}"
    return quoted(text)


def schedule_title(text: str) -> str:
    key = _key(text)
    if key in SCHEDULE_TITLES:
        return SCHEDULE_TITLES[key]
    for pattern, wording in ((VISITS, "زيارة {}"), (CALLS, "مكالمة من {}")):
        match = pattern.match(key)
        if match and match["name"] in NAMES:
            return wording.format(NAMES[match["name"]])
    return quoted(text)


SURFACES = {"kitchen counter", "counter", "bedroom desk", "desk", "dining table", "table", "dark table", "sofa", "couch", "nightstand"}


def at_place(text: str) -> str:
    """'على' for surfaces, 'في' for rooms and anything else."""

    preposition = "على" if _key(text) in SURFACES else "في"
    return f"{preposition} {place(text)}"
