import { describe, expect, it } from "vitest";
import { effectiveShortGloss, validateGraph, type Lexeme, type Sense, type Topic, type VocabularyGraph } from "./domain";
import { newId } from "./ids";

const sync = {
  ownerId: "owner0000000001", deleted: false, createdAt: "2026-08-28T12:00:00.000Z",
  editedAt: "2026-08-28T12:00:00.000Z", editedBy: "device000000001", revision: 0
};

function graph(): VocabularyGraph {
  const topic: Topic = { id: "topic0000000001", name: "Travel", icon: "🧭", order: 0, ...sync };
  const lexeme: Lexeme = {
    id: "lexeme000000001", language: "es", headword: "la balsa", lemma: "balsa", reading: null, ipa: "/ˈbalsa/",
    pos: "noun", gender: "feminine", register: "neutral", dialect: null, emoji: "🛶",
    topicIds: [topic.id], status: "active", shortGloss: null, notes: [], primaryGloss: null, emotion: null, clipsSearchedAt: null, ...sync
  };
  const sense: Sense = {
    id: "sense0000000001", lexemeId: lexeme.id, definition: "Una embarcación sencilla.", definitionLang: "es",
    glosses: [{ lang: "en", terms: ["raft"] }, { lang: "ru", terms: ["плот"] }], domain: null, emoji: null, order: 0, ...sync
  };
  return { vocabularies: [], topics: [topic], lexemes: [lexeme], senses: [sense], attestations: [], examples: [], imagePrompts: [], pronunciations: [], studyStates: [], loops: [], loopItems: [], stories: [], storyParts: [], storyWords: [] };
}

describe("Acervo domain", () => {
  it("validates a multilingual graph and derives its short form", () => {
    const value = graph();
    expect(() => validateGraph(value)).not.toThrow();
    expect(effectiveShortGloss(value, value.lexemes[0].id)).toBe("raft");
    value.lexemes[0].shortGloss = "small raft";
    expect(effectiveShortGloss(value, value.lexemes[0].id)).toBe("small raft");
  });

  it("requires readings for Chinese lexemes", () => {
    const value = graph();
    value.lexemes[0] = { ...value.lexemes[0], language: "zh-Hans", headword: "图书馆", lemma: "图书馆" };
    expect(() => validateGraph(value)).toThrow("Chinese lexemes require a reading");
    value.lexemes[0].reading = "tu2 shu1 guan3";
    expect(() => validateGraph(value)).not.toThrow();
  });

  it("rejects cross-lexeme attestation lineage", () => {
    const value = graph();
    value.lexemes.push({ ...value.lexemes[0], id: "lexeme000000002", headword: "mareo", lemma: "mareo" });
    value.attestations.push({
      id: "attest000000001", lexemeId: "lexeme000000002", text: "Tuvo un mareo.", translation: null,
      sourceUrl: null, sourceTitle: null, sourceKind: "lesson", capturedAt: sync.createdAt, ...sync
    });
    value.examples.push({
      id: "example00000001", senseId: value.senses[0].id, text: "Tuvo un mareo.", textLang: "es",
      translation: null, translationLang: null, origin: "attestation", sourceAttestationId: "attest000000001",
      modelId: null, videoRef: null, videoTitle: null, videoChannel: null, videoStart: null,
      videoEnd: null, clipRef: null, imageRef: null, emotion: null,
      note: null, matchedForm: null, matchedTranslationForm: null, ...sync
    });
    expect(() => validateGraph(value)).toThrow("one lexeme");
  });

  it("rejects a graph containing records from another owner", () => {
    const value = graph();
    value.senses[0].ownerId = "owner0000000002";
    expect(() => validateGraph(value)).toThrow("one owner only");
  });

  it("rejects a lexeme that references a missing topic", () => {
    const value = graph();
    value.lexemes[0].topicIds = ["topic0000000002"];
    expect(() => validateGraph(value)).toThrow("missing topic");
  });

  it("generates PocketBase-compatible ids without bias-visible shape errors", () => {
    const ids = new Set(Array.from({ length: 200 }, () => newId()));
    expect(ids.size).toBe(200);
    ids.forEach((id) => expect(id).toMatch(/^[a-z0-9]{15}$/));
  });
});
