/**
 * The dictionary routes in `pb_hooks/acervo.js`, driven against stubbed PocketBase globals.
 *
 * Two things are covered here and nowhere else: what the server says it holds, and the two online
 * connectors. §11.5 measured three Wiktionary-derived sources with three different field shapes, so
 * the mapping is the part most likely to be quietly wrong — and both sources report an absent word
 * differently, which is exactly the distinction that made an earlier measurement read 69 % coverage
 * when the real number was 100 %.
 *
 *     node --test tests/hooks/
 */

import assert from "node:assert/strict";
import { before, describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";
import os from "node:os";
import { createRequire } from "node:module";

const here = path.dirname(fileURLToPath(import.meta.url));
const HOOK = path.join(here, "..", "..", "deploy", "acervo", "pocketbase", "pb_hooks", "acervo.js");

const DICTIONARIES = fs.mkdtempSync(path.join(os.tmpdir(), "acervo-dictionaries-"));
const OWNER = "owner0000000001";

/** What the next `$http.send` returns, and what it was asked for. */
let http = { responses: [], calls: [] };

function installGlobals() {
  globalThis.$os = {
    getenv: (name) => ({ ACERVO_DICTIONARIES_PATH: DICTIONARIES }[name] ?? ""),
    readFile: (file) => fs.readFileSync(file, "utf8"),
    readDir: (directory) => fs.readdirSync(directory, { withFileTypes: true })
      .map((entry) => ({ name: () => entry.name, isDir: () => entry.isDirectory() })),
  };
  globalThis.toString = (value) => String(value);
  globalThis.$http = {
    send: (options) => {
      http.calls.push(options);
      const next = http.responses.shift();
      if (next instanceof Error) throw next;
      return next ?? { statusCode: 404, body: "" };
    },
  };
  globalThis.$security = { randomStringWithAlphabet: () => "x".repeat(15), randomString: () => "x" };
  globalThis.Record = function Record() { return {}; };
  globalThis.BadRequestError = class BadRequestError extends Error {};
}

function event(pathname, query = {}, { signedIn = true } = {}) {
  const captured = {};
  return {
    app: { logger: () => ({ error() {} }) },
    auth: signedIn ? { id: OWNER, collection: () => ({ name: "users" }) } : null,
    request: { url: { path: `/api/acervo/v1${pathname}` }, method: "GET" },
    requestInfo: () => ({ body: {}, query }),
    json: (status, payload) => { captured.status = status; captured.payload = payload; return captured; },
    captured,
  };
}

function writeMetadata(id, overrides = {}) {
  fs.writeFileSync(path.join(DICTIONARIES, `${id}.json`), JSON.stringify({
    id, name: `Dictionary ${id}`, sourceLang: "es", targetLang: "en", tier: "fields",
    licence: "CC BY-SA 4.0", attribution: "Wiktionary contributors.", entryCount: 10,
    keyCount: 12, blobBytes: 100, indexBytes: 40, schemaVersion: 1, ...overrides,
  }));
}

let hook;

describe("what the server says it holds", () => {
  before(() => {
    installGlobals();
    hook = createRequire(import.meta.url)(HOOK);
  });

  it("lists the artifacts on disk, by id", () => {
    writeMetadata("kaikki-es-es");
    writeMetadata("cc-cedict", { sourceLang: "zh-Hans" });
    const { status, payload } = hook.dispatch(event("/dictionaries"));
    assert.equal(status, 200);
    assert.deepEqual(payload.data.dictionaries.map((row) => row.id), ["cc-cedict", "kaikki-es-es"]);
  });

  it("carries the licence and attribution the interface has to show", () => {
    const [first] = hook.dispatch(event("/dictionaries")).payload.data.dictionaries;
    assert.equal(first.licence, "CC BY-SA 4.0");
    assert.equal(first.attribution, "Wiktionary contributors.");
  });

  it("ignores a half-written artifact rather than failing the whole list", () => {
    fs.writeFileSync(path.join(DICTIONARIES, "broken.json"), "{ not json");
    const { payload } = hook.dispatch(event("/dictionaries"));
    assert.deepEqual(payload.data.dictionaries.map((row) => row.id), ["cc-cedict", "kaikki-es-es"]);
    fs.unlinkSync(path.join(DICTIONARIES, "broken.json"));
  });

  it("needs the owner to be signed in", () => {
    const { status } = hook.dispatch(event("/dictionaries", {}, { signedIn: false }));
    assert.equal(status, 401);
  });
});

describe("the online connectors", () => {
  before(() => {
    installGlobals();
    hook = createRequire(import.meta.url)(HOOK);
  });

  function lookup(source, query) {
    return hook.dispatch(event(`/dictionaries/online/${source}`, query));
  }

  it("percent-encodes the headword", () => {
    // A first spike run counted four "transport failures" on each API. They were the same four
    // words, and the cause was a missing percent-encoding rather than anything about the sources.
    http = { responses: [{ statusCode: 200, body: JSON.stringify({ word: "de repente", entries: [] }) }], calls: [] };
    lookup("freedictionaryapi", { word: "de repente", language: "es" });
    assert.match(http.calls[0].url, /de%20repente/);
    assert.match(http.calls[0].headers["User-Agent"], /^Acervo\//);
  });

  it("maps freedictionaryapi's own field shape", () => {
    http = { responses: [{ statusCode: 200, body: JSON.stringify({
      word: "picar",
      entries: [{
        language: { code: "es" },
        partOfSpeech: "verb",
        pronunciations: [{ type: "ipa", text: "/piˈkaɾ/" }],
        senses: [
          { definition: "to itch", examples: ["una tela que pica"] },
          { definition: "" },
        ],
      }],
    }) }], calls: [] };
    const { payload } = lookup("freedictionaryapi", { word: "picar", language: "es" });
    const [entry] = payload.data.entries;
    assert.equal(entry.headword, "picar");
    assert.equal(entry.posLabel, "verb");
    assert.equal(entry.ipa, "/piˈkaɾ/");
    assert.deepEqual(entry.senses.map((sense) => sense.definition), ["to itch"]);
    assert.deepEqual(entry.senses[0].examples, [{ text: "una tela que pica" }]);
  });

  it("strips the wiki markup Wikimedia returns inside its definitions", () => {
    // Its definitions are HTML fragments carrying mw:WikiLink markup, so mapping means stripping it.
    http = { responses: [{ statusCode: 200, body: JSON.stringify({
      es: [{
        partOfSpeech: "Verb",
        language: "Spanish",
        definitions: [{
          definition: 'to <a rel="mw:WikiLink" href="/wiki/itch">itch</a>',
          parsedExamples: [{ example: "una tela que <b>pica</b>", translation: "a cloth that itches" }],
        }],
      }],
      en: [{ partOfSpeech: "Noun", definitions: [{ definition: "something else" }] }],
    }) }], calls: [] };
    const { payload } = lookup("wikimedia-rest", { word: "picar", language: "es" });
    assert.equal(payload.data.entries.length, 1, "only the language asked for");
    const [entry] = payload.data.entries;
    assert.equal(entry.senses[0].definition, "to itch");
    assert.deepEqual(entry.senses[0].examples,
      [{ text: "una tela que pica", translation: "a cloth that itches" }]);
  });

  it("returns every language when none is asked for", () => {
    http = { responses: [{ statusCode: 200, body: JSON.stringify({
      es: [{ partOfSpeech: "Verb", definitions: [{ definition: "to itch" }] }],
      pt: [{ partOfSpeech: "Verb", definitions: [{ definition: "picar" }] }],
    }) }], calls: [] };
    const { payload } = lookup("wikimedia-rest", { word: "picar" });
    assert.deepEqual(payload.data.entries.map((entry) => entry.language), ["es", "pt"]);
  });

  it("treats a word the source does not hold as an absence, not a failure", () => {
    // The two sources disagree about how to say it: one answers 200 with an empty list, the other
    // 404. Conflating either with a transport error understates coverage, which it once did.
    http = { responses: [{ statusCode: 200, body: JSON.stringify({ word: "zzzz", entries: [] }) }], calls: [] };
    assert.deepEqual(lookup("freedictionaryapi", { word: "zzzz" }).payload.data.entries, []);

    http = { responses: [{ statusCode: 404, body: "" }], calls: [] };
    assert.deepEqual(lookup("wikimedia-rest", { word: "zzzz" }).payload.data.entries, []);
  });

  it("says so when the source is unreachable or broken", () => {
    http = { responses: [new Error("connection refused")], calls: [] };
    assert.equal(lookup("freedictionaryapi", { word: "picar" }).status, 502);

    http = { responses: [{ statusCode: 500, body: "" }], calls: [] };
    assert.equal(lookup("freedictionaryapi", { word: "picar" }).status, 502);

    http = { responses: [{ statusCode: 200, body: "not json" }], calls: [] };
    assert.equal(lookup("wikimedia-rest", { word: "picar" }).status, 502);
  });

  it("refuses an unknown source and a missing word", () => {
    assert.equal(lookup("wordnik", { word: "picar" }).status, 404);
    assert.equal(lookup("freedictionaryapi", {}).status, 400);
  });

  it("needs the owner to be signed in", () => {
    const captured = hook.dispatch(
      event("/dictionaries/online/freedictionaryapi", { word: "picar" }, { signedIn: false }));
    assert.equal(captured.status, 401);
  });
});
