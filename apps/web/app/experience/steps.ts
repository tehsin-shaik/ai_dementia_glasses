import type { VoiceLanguage } from "../voice";

export type Vec3 = [number, number, number];

export type Viewpoint = {
  position: Vec3;
  target: Vec3;
};

type Localized = Record<VoiceLanguage, string>;

export type MomentStep = {
  kind: "moment";
  id: string;
  sceneTime: string;
  view: Viewpoint;
  title: Localized;
  narration: Localized;
  location: Localized;
  capture: Localized;
};

export type QuestionStep = {
  kind: "question";
  id: string;
  sceneTime: string;
  view: Viewpoint;
  title: Localized;
  narration: Localized;
  question: Localized;
  revealView?: Viewpoint;
  /** The reveal only applies when the answer names one of these places. */
  revealPlaces?: string[];
};

export type OpenStep = {
  kind: "open";
  id: string;
  sceneTime: string;
  view: Viewpoint;
  title: Localized;
  narration: Localized;
  suggestions: Localized[];
};

export type ExperienceStep = MomentStep | QuestionStep | OpenStep;

/** Position of Alex's keys on the kitchen counter in the 3D scene. */
export const KEYS_POSITION: Vec3 = [-2.6, 0.93, -3.45];

/**
 * The walk-through replays Alex's seeded demo morning (see apps/api/app/seed.py),
 * so every answer the glasses show comes from records that already exist.
 */
export const EXPERIENCE_STEPS: ExperienceStep[] = [
  {
    kind: "moment",
    id: "tea",
    sceneTime: "10:00 AM",
    view: { position: [-3.1, 1.6, -1.3], target: [-3.8, 1.0, -3.5] },
    title: { en: "Making tea", ar: "تحضير الشاي" },
    narration: {
      en: "Alex is making tea. The glasses capture one frame, but nothing is kept until Alex reviews it and presses Save.",
      ar: "أليكس يحضّر الشاي. تلتقط النظارة صورة واحدة، ولا يُحفظ شيء حتى يراجعها أليكس ويضغط حفظ.",
    },
    location: { en: "Kitchen", ar: "المطبخ" },
    capture: { en: "Making tea", ar: "تحضير الشاي" },
  },
  {
    kind: "moment",
    id: "reading",
    sceneTime: "10:10 AM",
    view: { position: [-3.4, 1.2, 3.1], target: [-3.4, 0.45, 1.9] },
    title: { en: "Reading", ar: "القراءة" },
    narration: {
      en: "Ten minutes later Alex sits down to read. Each moment is a deliberate, reviewed save, not continuous recording.",
      ar: "بعد عشر دقائق يجلس أليكس للقراءة. كل لحظة تُحفظ عن قصد بعد المراجعة، وليس تسجيلًا متواصلًا.",
    },
    location: { en: "Living room", ar: "غرفة المعيشة" },
    capture: { en: "Reading", ar: "القراءة" },
  },
  {
    kind: "moment",
    id: "keys",
    sceneTime: "10:18 AM",
    view: { position: [-2.4, 1.6, -2.1], target: KEYS_POSITION },
    title: { en: "Keys on the counter", ar: "المفاتيح على الطاولة" },
    narration: {
      en: "Back in the kitchen, Alex puts the keys down on the counter and saves the moment.",
      ar: "في المطبخ يضع أليكس المفاتيح على الطاولة ويحفظ اللحظة.",
    },
    location: { en: "Kitchen", ar: "المطبخ" },
    capture: { en: "Keys visible on kitchen counter", ar: "المفاتيح ظاهرة على طاولة المطبخ" },
  },
  {
    kind: "moment",
    id: "leaving",
    sceneTime: "10:25 AM",
    view: { position: [3.2, 1.6, 0.2], target: [6, 1.2, 0] },
    title: { en: "Preparing to leave", ar: "الاستعداد للخروج" },
    narration: {
      en: "Alex heads to the front door to go out.",
      ar: "يتجه أليكس إلى الباب الأمامي للخروج.",
    },
    location: { en: "Hallway", ar: "الممر" },
    capture: { en: "Preparing to leave", ar: "الاستعداد للخروج" },
  },
  {
    kind: "question",
    id: "ask-keys",
    sceneTime: "10:30 AM",
    view: { position: [4.9, 1.6, 0.1], target: [6, 1.35, 0] },
    revealView: { position: [0.2, 1.6, -0.8], target: KEYS_POSITION },
    revealPlaces: ["counter", "طاولة المطبخ"],
    title: { en: "Where are my keys?", ar: "أين مفاتيحي؟" },
    narration: {
      en: "At the door Alex can't find the keys and asks. The answer comes from the live MemoryCue API, using only saved moments.",
      ar: "عند الباب لا يجد أليكس المفاتيح فيسأل. تأتي الإجابة من واجهة MemoryCue الحقيقية، من اللحظات المحفوظة فقط.",
    },
    question: { en: "Where are my keys?", ar: "أين مفاتيحي؟" },
  },
  {
    kind: "question",
    id: "ask-wallet",
    sceneTime: "10:31 AM",
    view: { position: [4.9, 1.6, 0.1], target: [5.55, 0.85, 1.05] },
    title: { en: "Where is my wallet?", ar: "أين محفظتي؟" },
    narration: {
      en: "The wallet was never saved in any moment. MemoryCue says it doesn't know instead of guessing.",
      ar: "لم تُحفظ المحفظة في أي لحظة. يقول MemoryCue إنه لا يعرف بدلًا من التخمين.",
    },
    question: { en: "Where is my wallet?", ar: "أين محفظتي؟" },
  },
  {
    kind: "open",
    id: "ask-anything",
    sceneTime: "10:32 AM",
    view: { position: [3.6, 1.6, 0.4], target: [-3, 1.1, 1.5] },
    title: { en: "Ask anything", ar: "اسأل أي سؤال" },
    narration: {
      en: "Try your own question, typed or spoken. Answers use Alex's saved demo data.",
      ar: "جرّب سؤالك الخاص كتابةً أو صوتًا. تستخدم الإجابات بيانات أليكس التجريبية المحفوظة.",
    },
    suggestions: [
      { en: "What am I doing today?", ar: "ما هو جدولي اليوم؟" },
      { en: "What was I doing at 10 AM?", ar: "ماذا كنت أفعل الساعة العاشرة صباحا؟" },
      { en: "Who is Sarah?", ar: "من هي Sarah؟" },
      { en: "What did I do today?", ar: "ماذا فعلت اليوم؟" },
      { en: "What did my doctor say?", ar: "ماذا قال طبيبي؟" },
    ],
  },
];
