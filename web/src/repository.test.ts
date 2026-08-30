import { describe, expect, it } from "vitest";
import { MemoryDatabase } from "./localDatabase";
import { LOCAL_SCHEMA_VERSION, LocalAcervoRepository } from "./repository";
import { fakeRemote } from "./testRemote";
import { articleFor } from "./selectors";
import { parseArticle, YAML_TEMPLATE, yamlFor } from "./yaml";

const lexemeInput = {
  language: "es", headword: "desmayarse", lemma: "desmayarse", reading: null, ipa: null, pos: "verb" as const,
  gender: null, register: "neutral" as const, dialect: null, emoji: "😵‍💫", topicIds: [],
  status: "active" as const, shortGloss: null, notes: []
};

describe("the Acervo repository", () => {
  it("commits valid multi-collection graph writes atomically", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    repository.attachRemote(fakeRemote());
    const sync = {
      ownerId: "owner0000000001", deleted: false, createdAt: "2026-08-28T12:00:00.000Z",
      editedAt: "2026-08-28T12:00:00.000Z", editedBy: repository.snapshot().deviceId, revision: 0
    };
    await repository.writeGraph({
      topics: [{ id: "topic0000000001", name: "Health", icon: "🩺", order: 0, ...sync }],
      lexemes: [{ id: "lexeme000000001", ...lexemeInput, topicIds: ["topic0000000001"], ...sync }],
      senses: [{
        id: "sense0000000001", lexemeId: "lexeme000000001", definition: "Perder el conocimiento.",
        definitionLang: "es", glosses: [{ lang: "en", terms: ["to faint"] }], domain: null, order: 0, ...sync
      }]
    });
    expect(repository.snapshot().topics).toHaveLength(1);
    expect(repository.snapshot().lexemes).toHaveLength(1);
    expect(repository.snapshot().senses).toHaveLength(1);
  });

  it("leaves every store untouched when a graph write is invalid", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    repository.attachRemote(fakeRemote());
    const sync = {
      ownerId: "owner0000000001", deleted: false, createdAt: "2026-08-28T12:00:00.000Z",
      editedAt: "2026-08-28T12:00:00.000Z", editedBy: repository.snapshot().deviceId, revision: 0
    };
    await expect(repository.writeGraph({ senses: [{
      id: "sense0000000001", lexemeId: "missing00000001", definition: "Missing", definitionLang: "en",
      glosses: [{ lang: "en", terms: ["missing"] }], domain: null, order: 0, ...sync
    }] })).rejects.toThrow("missing lexeme");
    expect((await database.read()).senses).toEqual([]);
  });

  it("stores a complete graph with the revisions the server allocated", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    repository.attachRemote(fakeRemote());
    const topic = await repository.saveTopic({ name: "Health", icon: "🩺", order: 0 }, "topic0000000001");
    const lexeme = await repository.saveLexeme({ ...lexemeInput, topicIds: [topic.id] }, "lexeme000000001");
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
      videoRef: null, videoTitle: null, videoStart: null, imageRef: null, audioRef: null, note: null,
      matchedForm: null, matchedTranslationForm: null, approved: true
    }, "example00000001");
    expect(repository.snapshot()).toMatchObject({ ready: true, ownerId: "owner0000000001" });
    // Every stored record carries the revision the server allocated, never a locally invented one.
    const stored = await database.read();
    expect([...stored.topics, ...stored.lexemes, ...stored.senses, ...stored.attestations, ...stored.examples]
      .map((record) => record.revision).sort((a, b) => a - b)).toEqual([1, 2, 3, 4, 5]);
  });

  it("atomically refuses invalid relations and Chinese records without readings", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    repository.attachRemote(fakeRemote());
    await expect(repository.saveSense({
      lexemeId: "missing00000001", definition: "Missing", definitionLang: "en",
      glosses: [{ lang: "en", terms: ["missing"] }], domain: null, order: 0
    })).rejects.toThrow("missing lexeme");
    await expect(repository.saveLexeme({ ...lexemeInput, language: "zh-Hans", headword: "图书馆", lemma: "图书馆" }))
      .rejects.toThrow("require a reading");
    expect(repository.snapshot().senses).toHaveLength(0);
    expect(repository.snapshot().lexemes).toHaveLength(0);
  });

  it("tombstones a lexeme and its dependent graph in one write", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    const remote = fakeRemote();
    repository.attachRemote(remote);
    const lexeme = await repository.saveLexeme(lexemeInput, "lexeme000000001");
    await repository.saveSense({
      lexemeId: lexeme.id, definition: "Perder el conocimiento.", definitionLang: "es",
      glosses: [{ lang: "en", terms: ["faint"] }], domain: null, order: 0
    }, "sense0000000001");
    await repository.delete("lexemes", lexeme.id);
    expect(repository.snapshot().lexemes[0].deleted).toBe(true);
    expect(repository.snapshot().senses[0].deleted).toBe(true);
    // The lexeme and its dependent sense travel to the server as one batch.
    expect(Object.keys(remote.sent.at(-1)!).sort()).toEqual(["lexemes", "senses"]);
  });

  it("tombstones a topic and removes it from related lexemes atomically", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    const remote = fakeRemote();
    repository.attachRemote(remote);
    const topic = await repository.saveTopic({ name: "Health", icon: "🩺", order: 0 }, "topic0000000001");
    await repository.saveLexeme({ ...lexemeInput, topicIds: [topic.id] }, "lexeme000000001");
    await repository.delete("topics", topic.id);
    expect(repository.snapshot().topics[0].deleted).toBe(true);
    expect(repository.snapshot().lexemes[0].topicIds).toEqual([]);
    expect(Object.keys(remote.sent.at(-1)!).sort()).toEqual(["lexemes", "topics"]);
  });

  it("leaves every store untouched when the server refuses the write", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    const remote = fakeRemote();
    repository.attachRemote(remote);
    await repository.saveLexeme(lexemeInput, "lexeme000000001");
    const before = await database.read();

    remote.fail = new Error("This entry was changed somewhere else.");
    await expect(repository.delete("lexemes", "lexeme000000001")).rejects.toThrow("changed somewhere else");

    expect(await database.read()).toEqual(before);
    expect(repository.snapshot().lexemes[0].deleted).toBe(false);
  });

  it("refuses to write with no transport attached, rather than queueing", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    await expect(repository.saveLexeme(lexemeInput, "lexeme000000001")).rejects.toThrow("not connected");
    expect((await database.read()).lexemes).toEqual([]);
  });

  it("does not let two graph writes landing at once drop each other's records", async () => {
    // The window is the await inside a commit: both callers copy the graph, both store, and the
    // later assignment would silently discard the earlier one's records.
    const database = new MemoryDatabase();
    const write = database.write.bind(database);
    let gate: Promise<void> | null = null;
    database.write = async (changes) => { if (gate) await gate; return write(changes); };

    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    const topic = (id: string, name: string, revision: number) => ({
      id, name, icon: null, order: 0, ownerId: "owner0000000001", deleted: false,
      createdAt: "2026-08-29T12:00:00.000Z", editedAt: "2026-08-29T12:00:00.000Z",
      editedBy: "device000000001", revision
    });

    let release: () => void = () => {};
    gate = new Promise<void>((resolve) => { release = resolve; });
    const first = repository.applyRemote({ topics: [topic("topic0000000001", "Health", 1)] }, 1, "dataset00000001");
    const second = repository.applyRemote({ topics: [topic("topic0000000002", "Travel", 2)] }, 2, "dataset00000001");
    release();
    await Promise.all([first, second]);

    expect(repository.snapshot().topics.map((entry) => entry.id).sort())
      .toEqual(["topic0000000001", "topic0000000002"]);
    expect(repository.snapshot().cursor).toBe(2);
    expect((await database.read()).topics).toHaveLength(2);
  });

  it("wipes another owner's replica without converting it and preserves the device id", async () => {
    const database = new MemoryDatabase();
    const first = new LocalAcervoRepository(database);
    await first.load("owner0000000001");
    first.attachRemote(fakeRemote());
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
    repository.attachRemote(fakeRemote());
    expect(repository.snapshot()).toMatchObject({
      lexemes: [], cursor: 0, datasetId: "", deviceId: "device000000001", ownerId: "owner0000000001"
    });
    expect((await database.read()).meta.schemaVersion).toBe(LOCAL_SCHEMA_VERSION);
  });
});

describe("saving an article edited as YAML", () => {
  /** A repository holding one seeded entry, ready to be edited through its YAML projection. */
  async function seeded() {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    const remote = fakeRemote();
    repository.attachRemote(remote);
    await repository.saveTopic({ name: "Health", icon: "🩺", order: 0 }, "topic0000000001");
    await repository.saveLexeme({ ...lexemeInput, topicIds: ["topic0000000001"] }, "lexeme000000001");
    await repository.saveSense({
      lexemeId: "lexeme000000001", definition: "Perder el conocimiento.", definitionLang: "es",
      glosses: [{ lang: "en", terms: ["to faint"] }], domain: null, order: 0
    }, "sense0000000001");
    await repository.saveExample({
      senseId: "sense0000000001", text: "Me desmayé.", textLang: "es", translation: "I fainted.",
      translationLang: "en", origin: "manual", sourceAttestationId: null, modelId: null,
      videoRef: null, videoTitle: null, videoStart: null, imageRef: null, audioRef: null,
      note: null, matchedForm: null, matchedTranslationForm: null, approved: true
    }, "example00000001");
    const draft = () => parseArticle(yamlFor(articleFor(repository.snapshot(), "lexeme000000001")!));
    return { database, repository, remote, draft };
  }

  it("sends an update, a creation and a removal as one batch", async () => {
    const { repository, remote, draft } = await seeded();
    const article = draft();
    article.emoji = "🫠";
    article.senses[0].examples[0].id = null;          // replaced rather than edited
    article.senses.push({
      id: null, order: 1, definition: "Sentir una emoción intensa.", definitionLang: "es",
      glosses: [{ lang: "en", terms: ["to swoon"] }], domain: null, examples: [], images: []
    });
    const before = remote.sent.length;
    await repository.saveArticle(article);

    expect(remote.sent.length - before).toBe(1);
    const snapshot = repository.snapshot();
    expect(snapshot.lexemes[0].emoji).toBe("🫠");
    expect(snapshot.senses.filter((sense) => !sense.deleted)).toHaveLength(2);
    // The example whose id was dropped is replaced: a new row, and the old one tombstoned.
    expect(snapshot.examples.find((example) => example.id === "example00000001")!.deleted).toBe(true);
    expect(snapshot.examples.filter((example) => !example.deleted)).toHaveLength(1);
  });

  it("keeps every id it was given, so nothing is recreated by an ordinary edit", async () => {
    const { repository, draft } = await seeded();
    const created = repository.snapshot().lexemes[0].createdAt;
    const article = draft();
    article.headword = "desvanecerse";
    await repository.saveArticle(article);

    const snapshot = repository.snapshot();
    // Not one tombstone between them: the ids the document carried are the ids that were written.
    expect(snapshot.lexemes.map((lexeme) => lexeme.id)).toEqual(["lexeme000000001"]);
    expect(snapshot.senses.map((sense) => sense.id)).toEqual(["sense0000000001"]);
    expect(snapshot.examples.map((example) => example.id)).toEqual(["example00000001"]);
    // The Anki join and the image seed hang off these, and provenance off createdAt.
    expect(snapshot.lexemes[0].createdAt).toBe(created);
    expect(snapshot.lexemes[0].headword).toBe("desvanecerse");
  });

  it("carries the examples of a removed sense away with it", async () => {
    const { repository, draft } = await seeded();
    const added = draft();
    added.senses.push({
      id: null, order: 1, definition: "Sentir una emoción intensa.", definitionLang: "es",
      glosses: [{ lang: "en", terms: ["to swoon"] }], domain: null, images: [],
      examples: [{
        id: null, text: "Casi me desmayo de la emoción.", textLang: "es", translation: null,
        translationLang: null, origin: "manual", sourceAttestationId: null, modelId: null,
        videoRef: null, videoTitle: null, videoStart: null, imageRef: null, audioRef: null,
        note: null, matchedForm: null, matchedTranslationForm: null, approved: true
      }]
    });
    await repository.saveArticle(added);

    // Now drop the original sense. Its example is never mentioned again, and must not survive it.
    const trimmed = draft();
    trimmed.senses = trimmed.senses.filter((sense) => sense.id !== "sense0000000001");
    await repository.saveArticle(trimmed);

    const snapshot = repository.snapshot();
    expect(snapshot.senses.find((sense) => sense.id === "sense0000000001")!.deleted).toBe(true);
    expect(snapshot.examples.find((example) => example.id === "example00000001")!.deleted).toBe(true);
    expect(snapshot.examples.filter((example) => !example.deleted)).toHaveLength(1);
  });

  it("creates a whole entry when the document carries no ids", async () => {
    const { repository, remote } = await seeded();
    const article = parseArticle(YAML_TEMPLATE
      .replace('headword: ""', "headword: sobremesa")
      .replace('topics: []', "topics: [Health]")
      .replace('definition: ""', "definition: Charla tras la comida.")
      .replace('terms: [""]', "terms: [after-dinner talk]")
      .replace('- text: ""', "- text: La sobremesa duró dos horas.")
      .replace('translation: ""', "translation: The talk lasted two hours."));
    const before = remote.sent.length;
    const id = await repository.saveArticle(article);

    expect(remote.sent.length - before).toBe(1);
    expect(id).toMatch(/^[a-z0-9]{15}$/);
    const created = repository.snapshot().lexemes.find((lexeme) => lexeme.id === id)!;
    expect(created.headword).toBe("sobremesa");
    expect(created.topicIds).toEqual(["topic0000000001"]);
  });

  it("creates the ids a generated document minted, so an example can name its attestation", async () => {
    const { repository, remote } = await seeded();
    const before = remote.sent.length;
    // What the ingest endpoint proposes: a new entry whose example points at an attestation that
    // does not exist yet, because both are created by this one save.
    const id = await repository.saveArticle({
      id: null, language: "es", headword: "el garfio", lemma: "garfio", reading: null, ipa: null,
      pos: "noun", gender: "masculine", register: "neutral", dialect: null, emoji: "\u{1FA9D}",
      topics: ["Health"], status: "inbox", shortGloss: "hook", notes: [], images: [],
      senses: [{
        id: "sense0000000091", order: 0, definition: "Gancho de metal curvo.", definitionLang: "es",
        glosses: [{ lang: "en", terms: ["hook"] }], domain: null, images: [],
        examples: [{
          id: "example00000091", text: "Viene con un garfio.", textLang: "es",
          translation: "It comes with a hook.", translationLang: "en", origin: "attestation",
          sourceAttestationId: "attest000000091", modelId: null, videoRef: null, videoTitle: null,
          videoStart: null, imageRef: null, audioRef: null, note: null, matchedForm: null,
          matchedTranslationForm: null, approved: false
        }]
      }],
      attestations: [{
        id: "attest000000091", text: "Viene con un garfio.", translation: null, sourceUrl: null,
        sourceTitle: null, sourceKind: "unknown", capturedAt: "2026-08-29T12:00:00.000Z"
      }]
    });

    expect(remote.sent.length - before).toBe(1);
    const saved = repository.snapshot();
    expect(saved.senses.find((sense) => sense.id === "sense0000000091")?.lexemeId).toBe(id);
    expect(saved.attestations.find((record) => record.id === "attest000000091")?.lexemeId).toBe(id);
    expect(saved.examples.find((record) => record.id === "example00000091")?.sourceAttestationId)
      .toBe("attest000000091");
  });

  it("still refuses an unknown id when the document edits an entry that exists", async () => {
    const { repository, draft } = await seeded();
    const article = draft();
    // The article is stored, so every id in it should name a stored record. One that names nothing
    // is a typo or a paste from elsewhere, and silently creating a record under it would hide that.
    article.senses[0].id = "sense0000000099";
    await expect(repository.saveArticle(article)).rejects.toThrow("not in your vocabulary");
  });

  it("refuses a topic that does not exist, and names the ones that do", async () => {
    const { repository, draft } = await seeded();
    const article = draft();
    article.topics = ["Cooking"];
    await expect(repository.saveArticle(article)).rejects.toThrow('There is no topic called "Cooking"');
    await expect(repository.saveArticle(article)).rejects.toThrow("Health");
  });

  it("refuses an id belonging to another entry rather than stealing the record", async () => {
    const { repository, draft } = await seeded();
    await repository.saveLexeme({ ...lexemeInput, headword: "mareo" }, "lexeme000000002");
    const article = draft();
    article.id = "lexeme000000002";
    await expect(repository.saveArticle(article)).rejects.toThrow("belongs to a different entry");
  });

  it("changes nothing locally when the server refuses the batch", async () => {
    const { database, repository, remote, draft } = await seeded();
    const before = await database.read();
    const article = draft();
    article.headword = "desvanecerse";

    remote.fail = new Error("This entry was changed somewhere else.");
    await expect(repository.saveArticle(article)).rejects.toThrow("changed somewhere else");

    expect(await database.read()).toEqual(before);
    expect(repository.snapshot().lexemes[0].headword).toBe("desmayarse");
  });
});
