/* A small representative graph for interface tests: two languages, an inbox word, a clip, an
   attestation with lineage, an image prompt and a study state. */

import type { VocabularyGraph } from "./domain";

const OWNER = "owner0000000001";
const stamp = (day: string) => `2026-${day}T12:00:00.000Z`;
const sync = (created: string, edited = created) => ({
  ownerId: OWNER, deleted: false, createdAt: stamp(created), editedAt: stamp(edited),
  editedBy: "device000000001", revision: 1
});

export const TEST_OWNER = OWNER;

export function testGraph(): VocabularyGraph {
  return {
    vocabularies: [
      {
        id: "vocabes00000001", language: "es", definitionLang: "es", glossLangs: ["en"], notesLang: "en",
        displayName: null, flag: null, order: 0, ...sync("01-05")
      },
      {
        id: "vocaben00000001", language: "en", definitionLang: "en", glossLangs: ["ru"], notesLang: "ru",
        displayName: null, flag: null, order: 1, ...sync("01-05")
      }
    ],
    topics: [
      { id: "topicfood000001", name: "Food", icon: "🍽️", order: 0, ...sync("01-05") },
      { id: "topictravel0001", name: "Travel", icon: "🧭", order: 1, ...sync("01-05") }
    ],
    lexemes: [
      {
        id: "lexemepicar0001", language: "es", headword: "picar", lemma: "picar", reading: null,
        ipa: "/piˈkaɾ/", pos: "verb", gender: null, register: "neutral", dialect: null, emoji: "🌶️",
        topicIds: ["topicfood000001"], status: "active", shortGloss: "to itch; to chop",
        notes: ["The sense is carried by the object, not the verb."],
        clipsSearchedAt: stamp("08-24"), ...sync("02-11", "08-24")
      },
      {
        id: "lexemebalsa0001", language: "es", headword: "la balsa", lemma: "balsa", reading: null,
        ipa: null, pos: "noun", gender: "feminine", register: "neutral", dialect: null, emoji: "🛶",
        topicIds: ["topictravel0001"], status: "active", shortGloss: null, notes: [],
        clipsSearchedAt: null, ...sync("01-22")
      },
      {
        id: "lexemeespolv001", language: "es", headword: "espolvorear", lemma: "espolvorear",
        reading: null, ipa: null, pos: "verb", gender: null, register: "neutral", dialect: null,
        emoji: "🧀", topicIds: ["topicfood000001"], status: "inbox", shortGloss: "to sprinkle",
        notes: [], clipsSearchedAt: null, ...sync("08-27")
      },
      {
        id: "lexemeturmoil01", language: "en", headword: "turmoil", lemma: "turmoil", reading: null,
        ipa: "/ˈtɜːmɔɪl/", pos: "noun", gender: null, register: "formal", dialect: null, emoji: "🌪️",
        topicIds: [], status: "active", shortGloss: null, notes: [], clipsSearchedAt: null,
        ...sync("02-25")
      }
    ],
    senses: [
      {
        id: "sensepicaritch0", lexemeId: "lexemepicar0001", definition: "Producir comezón.",
        definitionLang: "es", glosses: [{ lang: "en", terms: ["to itch"] }], domain: null, emoji: null, order: 0,
        ...sync("02-11")
      },
      {
        id: "sensepicarchop0", lexemeId: "lexemepicar0001", definition: "Cortar en trozos pequeños.",
        definitionLang: "es", glosses: [{ lang: "en", terms: ["to chop", "to dice"] }],
        domain: "cooking", emoji: "🔪", order: 1, ...sync("02-11")
      },
      {
        id: "sensebalsaraft0", lexemeId: "lexemebalsa0001", definition: "Embarcación plana.",
        definitionLang: "es", glosses: [{ lang: "en", terms: ["raft"] }], domain: null, emoji: null, order: 0,
        ...sync("01-22")
      },
      {
        id: "senseespolvor10", lexemeId: "lexemeespolv001", definition: "Esparcir polvo sobre algo.",
        definitionLang: "es", glosses: [{ lang: "en", terms: ["to sprinkle"] }], domain: "cooking", emoji: null,
        order: 0, ...sync("08-27")
      },
      {
        id: "senseturmoil010", lexemeId: "lexemeturmoil01", definition: "A state of great confusion.",
        definitionLang: "en", glosses: [{ lang: "ru", terms: ["суматоха", "смятение"] }], domain: null, emoji: null,
        order: 0, ...sync("02-25")
      }
    ],
    attestations: [
      {
        id: "attestpicar0010", lexemeId: "lexemepicar0001", text: "cuidado que esa salsa pica un monton",
        translation: null, sourceUrl: null, sourceTitle: "Course chat", sourceKind: "conversation",
        capturedAt: stamp("02-11"), ...sync("02-11")
      }
    ],
    examples: [
      {
        id: "examplepicar010", senseId: "sensepicaritch0", text: "Me pica la nariz.",
        textLang: "es", translation: "My nose itches.", translationLang: "en", origin: "attestation",
        sourceAttestationId: "attestpicar0010", modelId: null, videoRef: null, videoTitle: null,
        videoChannel: null, videoStart: null, videoEnd: null, clipRef: null,
        imageRef: null, emotion: "exasperated, scratching at the collar", note: null,
        matchedForm: "pica", matchedTranslationForm: "itches", ...sync("02-11")
      },
      {
        // A clip, so its id is derived from its sense and the segment it quotes rather than drawn
        // at random — `clipExampleId("sensepicarchop0", "seg_7c3d18e5b04a92f6de27")`.
        id: "osd6ieh00s2hxql", senseId: "sensepicarchop0", text: "Pica la cebolla bien fina.",
        textLang: "es", translation: "Chop the onion very finely.", translationLang: "en",
        origin: "subtitle", modelId: null, sourceAttestationId: null,
        // A real video URL, because that is what the clip pipeline writes: `videoRef` is the
        // corpus's `video.url`, and a fallback link opens it at `videoStart`.
        videoRef: "https://www.youtube.com/watch?v=ebJDiXbeHTY", videoTitle: "Comiendo en un mercado",
        videoChannel: "Easy Spanish", videoStart: 461, videoEnd: 468,
        clipRef: "seg_7c3d18e5b04a92f6de27",
        imageRef: null, emotion: null, note: null, matchedForm: "Pica",
        matchedTranslationForm: "Chop", ...sync("02-11")
      },
      {
        id: "examplebalsa010", senseId: "sensebalsaraft0", text: "Cruzaron el río en una balsa.",
        textLang: "es", translation: "They crossed the river on a raft.", translationLang: "en",
        origin: "llm", sourceAttestationId: null, modelId: "demo-model", videoRef: null,
        videoTitle: null, videoChannel: null, videoStart: null, videoEnd: null, clipRef: null,
        imageRef: null, emotion: null, note: null,
        matchedForm: null, matchedTranslationForm: null, ...sync("01-22")
      }
    ],
    imagePrompts: [
      {
        id: "imagepicar00010", lexemeId: "lexemepicar0001", senseId: "sensepicaritch0",
        prompt: "A hand hovering near an itchy nose, flat vector, no text.", styleId: "flat-vector",
        seed: 184521, modelId: "demo-prompt", promptVersion: "demo-v1",
        imageRef: "images/lexemepicar0001/imagepicar00010.webp", imageModelId: "demo-painter",
        exampleId: "examplepicar010", attempts: 1, failureReason: null, suppressed: false,
        ...sync("02-11")
      }
    ],
    pronunciations: [
      {
        id: "hl08nur0wl9h0n1", lexemeId: "lexemepicar0001", targetKind: "lexeme", targetId: "lexemepicar0001",
        text: "picar", lang: "es", emotion: null, audioRef: "audio/lexemepicar0001/hl08nur0wl9h0n1-1a2b3c4d.mp3",
        audioMime: "audio/mpeg", providerId: "google-tts", modelId: "wavenet", voice: "es-ES-Wavenet-F",
        ...sync("02-11")
      }
    ],
    studyStates: [
      {
        id: "studypicar00010", lexemeId: "lexemepicar0001", system: "anki", noteId: 12, cardIds: [1, 2],
        reps: 21, lapses: 4, stability: 18.3, difficulty: 8.4, retrievability: 0.71,
        lastReview: stamp("08-22"), syncedAt: null, ...sync("02-11")
      },
      {
        id: "studybalsa00010", lexemeId: "lexemebalsa0001", system: "anki", noteId: null, cardIds: [],
        reps: 11, lapses: 0, stability: 74.2, difficulty: 3.9, retrievability: 0.95,
        lastReview: stamp("08-08"), syncedAt: null, ...sync("01-22")
      }
    ]
  };
}
