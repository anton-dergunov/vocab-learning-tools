import { IDBFactory } from "fake-indexeddb";
import { beforeEach, describe, expect, it } from "vitest";
import { createLocalDatabase } from "./localDatabase";
import { LocalAcervoRepository } from "./repository";

const lexemeInput = {
  language: "es", headword: "la balsa", lemma: "balsa", reading: null, pos: "noun" as const,
  gender: "feminine" as const, register: "neutral" as const, dialect: null, emoji: "🛶",
  topics: ["travel"], status: "active" as const, shortGloss: null, notes: []
};

describe("IndexedDB Acervo repository", () => {
  beforeEach(() => {
    Object.defineProperty(globalThis, "indexedDB", { configurable: true, value: new IDBFactory() });
  });

  it("persists an atomic multi-store graph and its pending markers", async () => {
    const first = new LocalAcervoRepository(createLocalDatabase());
    await first.load("owner0000000001");
    const sync = {
      ownerId: "owner0000000001", deleted: false, createdAt: "2026-08-28T12:00:00.000Z",
      editedAt: "2026-08-28T12:00:00.000Z", editedBy: first.snapshot().deviceId, revision: 0
    };
    await first.writeGraph({
      lexemes: [{ id: "lexeme000000001", ...lexemeInput, ...sync }],
      senses: [{
        id: "sense0000000001", lexemeId: "lexeme000000001", definition: "Una embarcación sencilla.",
        definitionLang: "es", glosses: [{ lang: "en", terms: ["raft"] }], domain: null, order: 0, ...sync
      }]
    });

    const reopened = new LocalAcervoRepository(createLocalDatabase());
    await reopened.load("owner0000000001");
    expect(reopened.snapshot()).toMatchObject({ persistent: true, pendingCount: 2 });
    expect(reopened.snapshot().lexemes[0].headword).toBe("la balsa");
    expect(reopened.snapshot().senses[0].lexemeId).toBe("lexeme000000001");
  });

  it("wipes the IndexedDB replica when the authenticated owner changes", async () => {
    const first = new LocalAcervoRepository(createLocalDatabase());
    await first.load("owner0000000001");
    await first.saveLexeme(lexemeInput, "lexeme000000001");
    const deviceId = first.snapshot().deviceId;

    const second = new LocalAcervoRepository(createLocalDatabase());
    await second.load("owner0000000002");
    expect(second.snapshot().lexemes).toEqual([]);
    expect(second.snapshot()).toMatchObject({ ownerId: "owner0000000002", deviceId, persistent: true });
  });
});
