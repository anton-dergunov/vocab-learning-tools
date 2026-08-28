import { describe, expect, it } from "vitest";
import { MemoryDatabase } from "./localDatabase";
import { LocalAcervoRepository } from "./repository";

const lexemeInput = {
  language: "es", headword: "desmayarse", lemma: "desmayarse", reading: null, pos: "verb" as const,
  gender: null, register: "neutral" as const, dialect: null, emoji: "😵‍💫", topics: ["health"],
  status: "active" as const, shortGloss: null, notes: []
};

describe("offline Acervo repository", () => {
  it("commits valid multi-collection graph writes atomically", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    const sync = {
      ownerId: "owner0000000001", deleted: false, createdAt: "2026-08-28T12:00:00.000Z",
      editedAt: "2026-08-28T12:00:00.000Z", editedBy: repository.snapshot().deviceId, revision: 0
    };
    await repository.writeGraph({
      lexemes: [{ id: "lexeme000000001", ...lexemeInput, ...sync }],
      senses: [{
        id: "sense0000000001", lexemeId: "lexeme000000001", definition: "Perder el conocimiento.",
        definitionLang: "es", glosses: [{ lang: "en", terms: ["to faint"] }], domain: null, order: 0, ...sync
      }]
    });
    expect(repository.snapshot()).toMatchObject({ pendingCount: 2 });
    expect(repository.snapshot().lexemes).toHaveLength(1);
    expect(repository.snapshot().senses).toHaveLength(1);
  });

  it("leaves every store untouched when a graph write is invalid", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    const sync = {
      ownerId: "owner0000000001", deleted: false, createdAt: "2026-08-28T12:00:00.000Z",
      editedAt: "2026-08-28T12:00:00.000Z", editedBy: repository.snapshot().deviceId, revision: 0
    };
    await expect(repository.writeGraph({ senses: [{
      id: "sense0000000001", lexemeId: "missing00000001", definition: "Missing", definitionLang: "en",
      glosses: [{ lang: "en", terms: ["missing"] }], domain: null, order: 0, ...sync
    }] })).rejects.toThrow("missing lexeme");
    expect((await database.read()).senses).toEqual([]);
    expect((await database.read()).pending).toEqual([]);
  });

  it("writes a complete graph locally and marks every record pending", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    const lexeme = await repository.saveLexeme(lexemeInput, "lexeme000000001");
    const sense = await repository.saveSense({
      lexemeId: lexeme.id, definition: "Perder brevemente el conocimiento.", definitionLang: "es",
      glosses: [{ lang: "en", terms: ["to faint", "to pass out"] }], domain: "health", order: 0
    }, "sense0000000001");
    const attestation = await repository.saveAttestation({
      lexemeId: lexeme.id, text: "Se desmayó durante la clase.", translation: null, sourceUrl: null,
      sourceTitle: "Language lesson", sourceKind: "lesson", capturedAt: "2026-08-28T12:00:00.000Z"
    }, "attest000000001");
    await repository.saveExample({
      senseId: sense.id, text: "Se desmayó durante la clase.", textLang: "es", translation: "They fainted during class.",
      translationLang: "en", origin: "attestation", sourceAttestationId: attestation.id, modelId: null,
      videoRef: null, imageRef: null, audioRef: null, note: null, approved: true
    }, "example00000001");
    expect(repository.snapshot()).toMatchObject({ ready: true, ownerId: "owner0000000001", pendingCount: 4 });
    expect((await database.read()).pending).toHaveLength(4);
  });

  it("atomically refuses invalid relations and Chinese records without readings", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    await expect(repository.saveSense({
      lexemeId: "missing00000001", definition: "Missing", definitionLang: "en",
      glosses: [{ lang: "en", terms: ["missing"] }], domain: null, order: 0
    })).rejects.toThrow("missing lexeme");
    await expect(repository.saveLexeme({ ...lexemeInput, language: "zh-Hans", headword: "图书馆", lemma: "图书馆" }))
      .rejects.toThrow("require a reading");
    expect(repository.snapshot().senses).toHaveLength(0);
    expect(repository.snapshot().lexemes).toHaveLength(0);
  });

  it("tombstones a lexeme and its dependent graph in one database write", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    const lexeme = await repository.saveLexeme(lexemeInput, "lexeme000000001");
    await repository.saveSense({
      lexemeId: lexeme.id, definition: "Perder el conocimiento.", definitionLang: "es",
      glosses: [{ lang: "en", terms: ["faint"] }], domain: null, order: 0
    }, "sense0000000001");
    await repository.delete("lexemes", lexeme.id);
    expect(repository.snapshot().lexemes[0].deleted).toBe(true);
    expect(repository.snapshot().senses[0].deleted).toBe(true);
    expect((await database.read()).pending).toEqual(expect.arrayContaining(["lexemes:lexeme000000001", "senses:sense0000000001"]));
  });

  it("wipes another owner's replica without converting it and preserves the device id", async () => {
    const database = new MemoryDatabase();
    const first = new LocalAcervoRepository(database);
    await first.load("owner0000000001");
    await first.saveLexeme(lexemeInput, "lexeme000000001");
    const deviceId = first.snapshot().deviceId;
    const second = new LocalAcervoRepository(database);
    await second.load("owner0000000002");
    expect(second.snapshot().lexemes).toEqual([]);
    expect(second.snapshot().deviceId).toBe(deviceId);
    expect(second.snapshot().ownerId).toBe("owner0000000002");
  });

  it("wipes a mismatched local schema instead of transforming it", async () => {
    const database = new MemoryDatabase();
    await database.write({ meta: {
      ownerId: "owner0000000001", deviceId: "device000000001", schemaVersion: 999
    } });
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    expect(repository.snapshot()).toMatchObject({
      lexemes: [], pendingCount: 0, deviceId: "device000000001", ownerId: "owner0000000001"
    });
    expect((await database.read()).meta.schemaVersion).toBe(1);
  });
});
