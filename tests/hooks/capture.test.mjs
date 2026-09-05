/**
 * The capture pipeline in `pb_hooks/acervo.js`, driven against stubbed PocketBase globals.
 *
 * The Docker integration test covers the real server, but it needs Docker and a built image; this
 * runs anywhere in a second and covers the part most likely to be wrong — what the hook does with a
 * model answer that is sloppy, which is every model answer eventually.
 *
 *     node --test tests/hooks/
 */

import assert from "node:assert/strict";
import { after, before, describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { createRequire } from "node:module";

const here = path.dirname(fileURLToPath(import.meta.url));
const HOOK = path.join(here, "..", "..", "deploy", "acervo", "pocketbase", "pb_hooks", "acervo.js");
const PROMPTS = path.join(here, "..", "..", "prompts");

/* ── the PocketBase surface the hook uses ───────────────────────────────── */

const GEMINI_ENV = {
  ACERVO_LLM_PROVIDER: "gemini",
  GEMINI_API_KEY: "stub-key",
  ACERVO_LLM_MODEL: "stub-model",
  ACERVO_PROMPTS_PATH: PROMPTS,
};
let environment = { ...GEMINI_ENV };
let llm = { resolution: {}, article: {}, calls: [], requests: [], errors: [], statusCode: 200, hiddenThinking: false };

class FakeRecord {
  constructor(collection, fields = {}) {
    this.collectionName = collection;
    this.fields = { ...fields };
    this.id = fields.id ?? "";
  }
  collection() { return { name: this.collectionName }; }
  get(field) { return this.fields[field]; }
  getString(field) { return String(this.fields[field] ?? ""); }
  getInt(field) { return Number(this.fields[field]) || 0; }
  getBool(field) { return Boolean(this.fields[field]); }
  getStringSlice(field) { return this.fields[field] ?? []; }
  getDateTime(field) { return { string: () => String(this.fields[field] ?? "") }; }
  set(field, value) {
    this.fields[field] = value;
    if (field === "id") this.id = value;
  }
}

class FakeApp {
  constructor() {
    this.records = { vocabularies: [], topics: [], lexemes: [], senses: [], attestations: [], examples: [], imagePrompts: [], image_prompts: [], study_states: [], sync_state: [] };
    this.sequence = 0;
  }
  add(collection, fields) {
    const record = new FakeRecord(collection, fields);
    this.records[collection].push(record);
    return record;
  }
  findCollectionByNameOrId(name) {
    if (!(name in this.records)) throw new Error(`no collection ${name}`);
    return { name, id: name };
  }
  findRecordsByFilter(collection, filter, _sort, _page, _limit, params = {}) {
    let rows = this.records[collection] ?? [];
    if (params.id !== undefined) rows = rows.filter((row) => row.id === params.id);
    if (params.owner !== undefined) rows = rows.filter((row) => row.getString("owner") === params.owner);
    if (filter.includes("deleted = false")) rows = rows.filter((row) => !row.getBool("deleted"));
    if (params.since !== undefined) rows = rows.filter((row) => row.getInt("revision") > params.since);
    if (params.language !== undefined) rows = rows.filter((row) => row.getString("language") === params.language);
    if (params.form !== undefined) {
      rows = rows.filter((row) =>
        row.getString("headword").toLowerCase().includes(params.form)
        || row.getString("lemma").toLowerCase().includes(params.form));
    }
    return rows;
  }
  findFirstRecordByFilter(collection, filter, params) {
    const found = this.findRecordsByFilter(collection, filter, "", 0, 0, params ?? {});
    if (!found.length) throw new Error("not found");
    return found[0];
  }
  findRecordById(collection, id) {
    const found = (this.records[collection] ?? []).find((row) => row.id === id);
    if (!found) throw new Error("not found");
    return found;
  }
  save(record) {
    const rows = this.records[record.collectionName];
    // Stands in for the save hook that allocates revisions on every replicated collection.
    if (record.collectionName !== "sync_state") record.set("revision", ++this.sequence);
    if (!rows.includes(record)) rows.push(record);
  }
  runInTransaction(work) { work(this); }
  logger() { return { error: (...args) => { llm.errors.push(args); } }; }
}

function installGlobals() {
  globalThis.$os = {
    getenv: (name) => environment[name] ?? "",
    readFile: (file) => createRequire(import.meta.url)("node:fs").readFileSync(file, "utf8"),
  };
  globalThis.toString = (value) => String(value);
  globalThis.$security = {
    randomStringWithAlphabet: (length, alphabet) => {
      let out = "";
      for (let index = 0; index < length; index += 1) {
        out += alphabet[Math.floor(Math.random() * alphabet.length)];
      }
      return out;
    },
    randomString: (length) => "x".repeat(length),
  };
  globalThis.$http = {
    send: (options) => {
      const payload = JSON.parse(options.body);
      llm.calls.push(payload);
      llm.requests.push(options);
      const system = payload.systemInstruction.parts[0].text;
      const answer = system.includes("You decide what a learner") ? llm.resolution : llm.article;
      const parts = [{ text: JSON.stringify(answer) }];
      if (llm.hiddenThinking) parts.unshift({ thought: true, text: "private reasoning" });
      return {
        statusCode: llm.statusCode,
        body: "provider details that must stay private",
        json: { candidates: [{ content: { parts } }] },
      };
    },
  };
  globalThis.Record = function Record(collection) { return new FakeRecord(collection.name, {}); };
  globalThis.BadRequestError = class BadRequestError extends Error {};
}

/* ── a request, and what came back ──────────────────────────────────────── */

function event(app, ownerId, body, route = "/capture") {
  const captured = {};
  return {
    app,
    auth: { id: ownerId, collection: () => ({ name: "users" }) },
    request: { url: { path: `/api/acervo/v1${route}` }, method: "POST" },
    requestInfo: () => ({ body, query: {} }),
    json: (status, payload) => { captured.status = status; captured.payload = payload; return captured; },
    captured,
  };
}

let hook;
let app;
const OWNER = "owner0000000001";

function seed() {
  app = new FakeApp();
  app.add("sync_state", { id: "dataset00000001", owner: OWNER, sequence: 0 });
  app.add("vocabularies", {
    id: "vocabes00000001", owner: OWNER, language: "es", definition_lang: "es",
    gloss_langs: ["en"], display_name: "Spanish", vocab_order: 0, deleted: false, revision: 1,
  });
  ["Food", "Culture"].forEach((name, index) => app.add("topics", {
    id: `topic${index}000000001`.slice(0, 15), owner: OWNER, name, topic_order: index,
    deleted: false, revision: 1,
  }));
  app.add("lexemes", {
    id: "lexemepicar0001", owner: OWNER, language: "es", headword: "picar", lemma: "picar",
    pos: "verb", status: "active", short_gloss: "to itch", topics: [], notes: [],
    deleted: false, revision: 1, created_at: "2026-01-01T00:00:00.000Z",
    edited_at: "2026-01-01T00:00:00.000Z", edited_by: "seed",
  });
  environment = { ...GEMINI_ENV };
  llm = { resolution: {}, article: {}, calls: [], requests: [], errors: [], statusCode: 200, hiddenThinking: false };
}

const RESOLUTION = {
  language: "es", headword: "el garfio", lemma: "garfio", pos: "noun",
  sentences: [{ text: "El disfraz de pirata viene con un garfio.", translation: null }],
  consumedLines: 2, consumedText: "El disfraz de pirata viene con un garfio.",
};

const ARTICLE = {
  headword: "el garfio", lemma: "garfio", pos: "noun", gender: "masculine", register: "neutral",
  emoji: "🪝", topics: ["Culture", "Nonexistent"], shortGloss: "hook", notes: ["Not el gancho."],
  senses: [{
    definition: "Gancho de metal curvo.",
    glosses: [{ lang: "en", terms: ["hook"] }],
    examples: [
      { text: "El disfraz de pirata viene con un garfio.",
        translation: "The pirate costume comes with a hook.",
        matchedForm: "un garfio", matchedTranslationForm: "hook", fromSentence: 0 },
      { text: "Perdió la mano y le pusieron un garfio.",
        translation: "He lost his hand and they gave him a hook.",
        matchedForm: "el garfio", matchedTranslationForm: "hooks", fromSentence: null },
    ],
  }],
};

function capture(body) {
  return hook.dispatch(event(app, OWNER, {
    schemaVersion: 5, deviceId: "device000000001", mode: "single", text: "some text", ...body,
  })).payload;
}

function resetGraph(confirm = "delete-all-words") {
  return hook.dispatch(event(app, OWNER, {
    schemaVersion: 5, deviceId: "device000000001", confirm,
  }, "/graph/reset")).payload;
}

describe("the capture endpoint", () => {
  before(() => {
    installGlobals();
    hook = createRequire(import.meta.url)(HOOK);
  });
  after(() => { delete globalThis.$http; });

  it("stops at a word the account already holds, before generating anything", () => {
    seed();
    llm.resolution = { ...RESOLUTION, headword: "Picar", lemma: "picar", sentences: [] };
    const result = capture({ text: "¿Te pica mucho la salsa?" });
    assert.deepEqual(result.data.duplicates.map((item) => item.headword), ["picar"]);
    assert.equal(result.data.draft, null);
    // One call, not two: an article for a word already held would be thrown away.
    assert.equal(llm.calls.length, 1);
  });

  it("passes on the word the submitter named, and says nothing when they did not", () => {
    seed();
    llm.resolution = RESOLUTION;
    llm.article = ARTICLE;
    capture({ text: "El disfraz de pirata viene con un garfio.", headword: "garfio" });
    // A hint for the resolver, not a bypass of it: the model still fixes the spelling, adds the
    // article and picks the lemma, so a named word and a picked one reach the article the same way.
    assert.match(llm.calls[0].contents[0].parts[0].text, /The learner says the word is: garfio/);

    seed();
    llm.resolution = RESOLUTION;
    llm.article = ARTICLE;
    capture({ text: "El disfraz de pirata viene con un garfio." });
    assert.doesNotMatch(llm.calls[0].contents[0].parts[0].text, /The learner says the word is/);
  });

  it("carries a dictionary entry to both steps as reference, and only as reference", () => {
    seed();
    llm.resolution = { ...RESOLUTION, sentences: [] };
    llm.article = ARTICLE;
    const reference = "## Wiktionary (es→es)\nverb\n1. Golpear algo con una punta.\n"
      + "   - una tela que pica — an itchy fabric";
    capture({ text: "picar", headword: "picar", reference, referenceMode: "expand" });

    const [resolve, compose] = llm.calls.map((call) => call.contents[0].parts[0].text);
    // The resolver is told what it is looking at, and told plainly that it is not learner input.
    assert.match(resolve, /una tela que pica/);
    assert.match(resolve, /CONTEXT ONLY/);
    // The composer is grounded on it and told which treatment was chosen.
    assert.match(compose, /Golpear algo con una punta/);
    assert.match(compose, /FILL IN THE GAPS/);
    assert.doesNotMatch(compose, /STAY CLOSE TO THE REFERENCE/);
  });

  it("says to stay close when that is what was asked for", () => {
    seed();
    llm.resolution = { ...RESOLUTION, sentences: [] };
    llm.article = ARTICLE;
    capture({ text: "picar", reference: "1. Golpear algo con una punta.", referenceMode: "faithful" });
    const compose = llm.calls[1].contents[0].parts[0].text;
    assert.match(compose, /STAY CLOSE TO THE REFERENCE/);
    assert.doesNotMatch(compose, /FILL IN THE GAPS/);
  });

  it("never turns a reference into an attestation", () => {
    seed();
    // The resolver is what mints attestations, and a grounded capture gives it no sentences: the
    // dictionary's examples are the dictionary's, not places this person met the word.
    llm.resolution = { ...RESOLUTION, sentences: [] };
    llm.article = ARTICLE;
    const result = capture({
      text: "picar", reference: "1. Golpear algo con una punta.\n   - una tela que pica",
      referenceMode: "expand",
    });
    assert.deepEqual(result.data.draft.attestations, []);
    // And the example the model drew from it is not filed against one either.
    const examples = result.data.draft.senses.flatMap((sense) => sense.examples);
    assert.ok(examples.length > 0);
    assert.ok(examples.every((example) => example.sourceAttestationId === null));
    assert.ok(examples.every((example) => example.origin === "llm"));
  });

  it("ignores a reference mode it does not recognise, rather than passing it on", () => {
    seed();
    llm.resolution = { ...RESOLUTION, sentences: [] };
    llm.article = ARTICLE;
    capture({ text: "picar", reference: "1. Golpear algo.", referenceMode: "whatever-you-like" });
    const compose = llm.calls[1].contents[0].parts[0].text;
    assert.match(compose, /Reference entry from an external dictionary/);
    assert.doesNotMatch(compose, /Treatment:/);
  });

  it("refuses a language with no vocabulary, and does not generate for it", () => {
    seed();
    llm.resolution = { ...RESOLUTION, language: "de", headword: "Wanderlust" };
    const result = capture({ text: "Fernweh und Wanderlust" });
    assert.equal(result.error.code, "language_not_configured");
    assert.match(result.error.message, /de/);
    assert.equal(llm.calls.length, 1);
  });

  it("builds a draft, keeping the learner's sentence as an attestation the example names", () => {
    seed();
    llm.resolution = RESOLUTION;
    llm.article = ARTICLE;
    const draft = capture({}).data.draft;

    assert.equal(draft.id, null);
    assert.equal(draft.status, "inbox");
    assert.equal(draft.headword, "el garfio");
    assert.equal(draft.gender, "masculine");
    // A topic the account does not have is dropped rather than invented: saving would refuse it.
    assert.deepEqual(draft.topics, ["Culture"]);

    assert.equal(draft.attestations.length, 1);
    const [own, invented] = draft.senses[0].examples;
    assert.equal(own.origin, "attestation");
    assert.equal(own.sourceAttestationId, draft.attestations[0].id);
    assert.equal(own.modelId, null);
    assert.equal(invented.origin, "llm");
    assert.equal(invented.modelId, "stub-model");
    // Every minted id is a real Acervo id, or nothing could reference anything.
    [draft.senses[0].id, own.id, draft.attestations[0].id].forEach((id) =>
      assert.match(id, /^[a-z0-9]{15}$/));
  });

  it("drops a marked form the model retyped instead of copying", () => {
    seed();
    llm.resolution = RESOLUTION;
    llm.article = ARTICLE;
    const [own, invented] = capture({}).data.draft.senses[0].examples;
    assert.equal(own.matchedForm, "un garfio");
    // "el garfio" does not occur in "Perdió la mano y le pusieron un garfio", and "hooks" does not
    // occur in its translation. Keeping either would make the record validator refuse the batch.
    assert.equal(invented.matchedForm, null);
    assert.equal(invented.matchedTranslationForm, null);
  });

  it("fills in a gloss and a definition language rather than losing the sense", () => {
    seed();
    llm.resolution = RESOLUTION;
    llm.article = { ...ARTICLE, senses: [{ definition: "Gancho de metal.", glosses: [], examples: [] }] };
    const sense = capture({}).data.draft.senses[0];
    assert.deepEqual(sense.glosses, [{ lang: "en", terms: ["el garfio"] }]);
    assert.equal(sense.definitionLang, "es");
  });

  it("applies the draft through the ordinary write path when asked", () => {
    seed();
    llm.resolution = RESOLUTION;
    llm.article = ARTICLE;
    const response = capture({ apply: true });
    assert.ok(response.data, JSON.stringify(response.error));
    const result = response.data;
    assert.match(result.applied.lexemeId, /^[a-z0-9]{15}$/);

    const created = app.records.lexemes.find((row) => row.id === result.applied.lexemeId);
    assert.equal(created.getString("headword"), "el garfio");
    assert.equal(created.getString("status"), "inbox");
    // Numbered by the save hook, which is what makes it visible to a cursor pull at all.
    assert.ok(created.getInt("revision") > 0);
    assert.equal(app.records.attestations.length, 1);
    assert.equal(app.records.examples.length, 2);
    assert.equal(
      app.records.examples[0].getString("source_attestation"),
      app.records.attestations[0].id
    );
  });

  it("never consumes zero lines in a stream, so a walk cannot stall", () => {
    seed();
    llm.resolution = { ...RESOLUTION, consumedLines: 0, consumedText: "line one" };
    llm.article = ARTICLE;
    const result = capture({ mode: "stream", text: "line one\nline two\nline three" }).data;
    assert.equal(result.resolution.consumedLines, 1);
  });

  it("uses the Gemini Developer API with its key and sampling setting", () => {
    seed();
    llm.resolution = RESOLUTION;
    llm.article = ARTICLE;
    capture({});
    const request = llm.requests[0];
    assert.equal(request.url,
      "https://generativelanguage.googleapis.com/v1beta/models/stub-model:generateContent");
    assert.equal(request.headers["x-goog-api-key"], "stub-key");
    assert.equal(llm.calls[0].generationConfig.temperature, 0.2);
    assert.equal(llm.calls[0].generationConfig.thinkingConfig, undefined);
  });

  it("uses the full Vertex URL, Vertex key, JSON output and medium thinking", () => {
    seed();
    environment = {
      ...GEMINI_ENV,
      ACERVO_LLM_PROVIDER: "vertex",
      VERTEX_API_KEY: "vertex-key",
      ACERVO_VERTEX_PROJECT: "personal-project",
      ACERVO_VERTEX_LOCATION: "global",
      ACERVO_LLM_MODEL: "gemini-3.7-flash",
    };
    llm.resolution = RESOLUTION;
    llm.article = ARTICLE;
    capture({});
    const request = llm.requests[0];
    assert.equal(request.url,
      "https://aiplatform.googleapis.com/v1/projects/personal-project/locations/global/publishers/google/models/gemini-3.7-flash:generateContent");
    assert.equal(request.headers["x-goog-api-key"], "vertex-key");
    assert.deepEqual(llm.calls[0].generationConfig, {
      responseMimeType: "application/json",
      thinkingConfig: { thinkingLevel: "MEDIUM" },
    });
  });

  it("ignores hidden thinking parts and parses only the article JSON", () => {
    seed();
    llm.hiddenThinking = true;
    llm.resolution = RESOLUTION;
    llm.article = ARTICLE;
    assert.equal(capture({}).data.draft.headword, "el garfio");
  });

  for (const [status, code] of [[401, "llm_authentication"], [403, "llm_authentication"],
    [400, "llm_configuration"], [404, "llm_configuration"], [429, "llm_rate_limited"],
    [500, "llm_unavailable"], [503, "llm_unavailable"]]) {
    it(`classifies provider HTTP ${status} without exposing its response`, () => {
      seed();
      llm.statusCode = status;
      llm.resolution = RESOLUTION;
      const result = capture({});
      assert.equal(result.error.code, code);
      assert.doesNotMatch(result.error.message, /provider details/);
    });
  }

  it("refuses a mismatched stream boundary before composing or writing", () => {
    seed();
    llm.resolution = { ...RESOLUTION, consumedLines: 1, consumedText: "different text" };
    llm.article = ARTICLE;
    const result = capture({ mode: "stream", text: "line one\nline two", apply: true });
    assert.equal(result.error.code, "stream_boundary_mismatch");
    assert.equal(llm.calls.length, 1);
    assert.equal(app.records.attestations.length, 0);
    assert.equal(app.records.examples.length, 0);
  });

  it("reports a model that answers with nothing usable, rather than half an entry", () => {
    seed();
    llm.resolution = RESOLUTION;
    llm.article = { headword: "el garfio", senses: [] };
    assert.equal(capture({}).error.code, "llm_unusable");
  });

  it("says so when the input cannot be read as a word at all", () => {
    seed();
    llm.resolution = { error: "!!! ???" };
    assert.equal(capture({ text: "!!! ???" }).error.code, "unreadable_input");
  });
});

describe("delete all words", () => {
  it("tombstones words and every descendant while retaining vocabularies and topics", () => {
    seed();
    const lexeme = app.records.lexemes[0];
    app.add("senses", { id: "sense0000000001", owner: OWNER, lexeme: lexeme.id, deleted: false });
    app.add("attestations", { id: "attest000000001", owner: OWNER, lexeme: lexeme.id, deleted: false });
    app.add("examples", { id: "example00000001", owner: OWNER, sense: "sense0000000001", deleted: false });
    app.add("image_prompts", { id: "image0000000001", owner: OWNER, lexeme: lexeme.id, deleted: false });
    app.add("study_states", { id: "study0000000001", owner: OWNER, lexeme: lexeme.id, deleted: false });

    const datasetId = app.records.sync_state[0].id;
    const result = resetGraph();
    assert.equal(result.data.deleted, 6);
    for (const collection of ["lexemes", "senses", "attestations", "examples", "image_prompts", "study_states"]) {
      assert.ok(app.records[collection].every((record) => record.getBool("deleted")), collection);
    }
    assert.ok(app.records.vocabularies.every((record) => !record.getBool("deleted")));
    assert.ok(app.records.topics.every((record) => !record.getBool("deleted")));
    assert.equal(result.data.datasetId, datasetId);
  });

  it("requires the delete-all-words confirmation token", () => {
    seed();
    assert.equal(resetGraph("delete-all-vocabulary").error.code, "confirmation_required");
    assert.ok(app.records.lexemes.every((record) => !record.getBool("deleted")));
  });
});
