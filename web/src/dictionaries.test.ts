import { IDBFactory } from "fake-indexeddb";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { backendSession } from "./api";
import {
  ANY_LANGUAGE,
  catalogue,
  groupedByLanguage,
  install,
  installed,
  forgetCachedLookups,
  isEnabled,
  lookup,
  primaryLanguage,
  setEnabled,
  uninstall
} from "./dictionaries";
import { createDictionaryStore, storageReport } from "./dictionaryStore";
import sample from "./testFixtures/sampleDictionary.json";

const bytes = (name: "dict" | "idx") =>
  Uint8Array.from(atob(sample[name]), (character) => character.charCodeAt(0));

/**
 * Answers artifact requests out of the committed fixture, so an install exercises the real download
 * path — streamed body, three files, one store write — without a server.
 */
function serveArtifacts(options: { missing?: string[] } = {}) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((async (url: string) => {
    const name = String(url).split("/").pop()!;
    const [id, extension] = [name.replace(/\.[a-z]+$/, ""), name.split(".").pop()!];
    if (options.missing?.includes(id)) return { ok: false, status: 404 } as Response;
    const body = extension === "json"
      ? new TextEncoder().encode(JSON.stringify({ ...sample.metadata, id }))
      : bytes(extension as "dict" | "idx");
    return {
      ok: true,
      status: 200,
      headers: new Headers({ "Content-Length": String(body.length) }),
      blob: async () => new Blob([body]),
      text: async () => new TextDecoder().decode(body),
      body: {
        getReader: () => {
          let done = false;
          return {
            read: async () => (done ? { done: true, value: undefined }
                                    : ((done = true), { done: false, value: body }))
          };
        }
      }
    } as unknown as Response;
  }) as typeof fetch);
}

describe("the shipped catalogue", () => {
  it("carries real breadth rather than a token few rows", () => {
    expect(catalogue.length).toBeGreaterThan(40);
    const languages = new Set(catalogue.map((entry) => primaryLanguage(entry.sourceLang)));
    expect(languages.size).toBeGreaterThan(8);
  });

  it("says who wrote every dictionary and under what licence", () => {
    // The obligation attaches to displaying the content, so it has to travel with every row.
    for (const entry of catalogue) {
      expect(entry.licence, entry.id).toBeTruthy();
      expect(entry.attribution, entry.id).toBeTruthy();
      expect(entry.url, entry.id).toMatch(/^https:\/\//);
    }
  });

  it("has no duplicate ids", () => {
    expect(new Set(catalogue.map((entry) => entry.id)).size).toBe(catalogue.length);
  });

  it("groups a language's scripts together and sorts the any-language sources last", () => {
    const groups = groupedByLanguage(catalogue);
    const chinese = groups.find(([code]) => code === "zh");
    // zh, zh-Hans and zh-Hant are one language to a reader, not three headings.
    expect(new Set(chinese?.[1].map((entry) => entry.sourceLang)).size).toBeGreaterThan(1);
    expect(groups[groups.length - 1][0]).toBe(ANY_LANGUAGE);
  });
});

describe("which dictionaries are switched on here", () => {
  beforeEach(() => localStorage.clear());

  it("remembers a choice about this device", () => {
    expect(isEnabled("cc-cedict")).toBe(false);
    setEnabled("cc-cedict", true);
    expect(isEnabled("cc-cedict")).toBe(true);
    setEnabled("cc-cedict", false);
    expect(isEnabled("cc-cedict")).toBe(false);
  });

  it("survives storage that refuses to answer", () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("denied"); });
    try {
      expect(isEnabled("cc-cedict")).toBe(false);
    } finally {
      getItem.mockRestore();
    }
  });
});

describe("storing a dictionary on this device", () => {
  beforeEach(async () => {
    Object.defineProperty(globalThis, "indexedDB", { configurable: true, value: new IDBFactory() });
    localStorage.clear();
    forgetCachedLookups();
    for (const record of await installed()) await uninstall(record.id);
    await backendSession.logout();
    await backendSession.restore();
    vi.spyOn(backendSession, "dictionaryFileUrl").mockImplementation(
      (id, extension) => `https://acervo.example.com/api/acervo/dictionaries/${id}.${extension}`);
    vi.spyOn(backendSession, "dictionaryHeaders").mockReturnValue({ Authorization: "Bearer t" });
  });

  afterEach(() => vi.restoreAllMocks());

  it("downloads the three files and reports progress while it does", async () => {
    serveArtifacts();
    const stages: string[] = [];
    const record = await install("sample", (progress) => stages.push(progress.stage));
    expect(record.metadata.id).toBe("sample");
    expect(record.bytes).toBe(bytes("dict").length + bytes("idx").length);
    expect(stages).toContain("index");
    expect(stages).toContain("payloads");
    expect(stages).toContain("saving");
  });

  it("switches the dictionary on once it is stored", async () => {
    serveArtifacts();
    await install("sample");
    expect(isEnabled("sample")).toBe(true);
  });

  it("says plainly when the server has not compiled it", async () => {
    serveArtifacts({ missing: ["sample"] });
    await expect(install("sample")).rejects.toThrow(/has not compiled that dictionary yet/);
    expect(await installed()).toHaveLength(0);
  });

  it("leaves every other dictionary alone when one cannot be stored", async () => {
    serveArtifacts();
    await install("sample");
    serveArtifacts({ missing: ["other"] });
    await expect(install("other")).rejects.toThrow();
    expect((await installed()).map((row) => row.id)).toEqual(["sample"]);
  });

  it("frees the space when a dictionary is removed, and touches nothing else", async () => {
    serveArtifacts();
    await install("sample");
    expect(await installed()).toHaveLength(1);
    await uninstall("sample");
    expect(await installed()).toHaveLength(0);
  });
});

describe("looking a word up", () => {
  beforeEach(async () => {
    Object.defineProperty(globalThis, "indexedDB", { configurable: true, value: new IDBFactory() });
    localStorage.clear();
    forgetCachedLookups();
    for (const record of await installed()) await uninstall(record.id);
    vi.spyOn(backendSession, "dictionaryFileUrl").mockImplementation(
      (id, extension) => `https://acervo.example.com/api/acervo/dictionaries/${id}.${extension}`);
    vi.spyOn(backendSession, "dictionaryHeaders").mockReturnValue({});
  });

  afterEach(() => vi.restoreAllMocks());

  it("answers from this device, and says that is where the answer came from", async () => {
    serveArtifacts();
    await install("sample");
    vi.spyOn(backendSession, "listDictionaries").mockRejectedValue(new Error("offline"));

    const results = await lookup("picar", "es");
    expect(results).toHaveLength(1);
    expect(results[0].origin).toBe("device");
    expect(results[0].entry?.articles?.[0].ipa).toBe("/piˈkaɾ/");
    // The obligation follows the entry, not just the settings row.
    expect(results[0].licence).toBeTruthy();
  });

  it("keeps working with the server unreachable", async () => {
    serveArtifacts();
    await install("sample");
    vi.spyOn(backendSession, "listDictionaries").mockRejectedValue(new Error("offline"));
    setEnabled("cc-cedict", true);   // enabled, not stored here, server down: silently unavailable

    const results = await lookup("picar", "es");
    expect(results.map((result) => result.dictionaryId)).toEqual(["sample"]);
  });

  it("returns nothing at all for a word no enabled dictionary holds", async () => {
    serveArtifacts();
    await install("sample");
    vi.spyOn(backendSession, "listDictionaries").mockRejectedValue(new Error("offline"));
    expect(await lookup("zzzznotaword", "es")).toEqual([]);
  });

  it("ignores dictionaries that are switched off", async () => {
    serveArtifacts();
    await install("sample");
    setEnabled("sample", false);
    vi.spyOn(backendSession, "listDictionaries").mockRejectedValue(new Error("offline"));
    expect(await lookup("picar", "es")).toEqual([]);
  });

  it("asks an online source through the server, never the browser", async () => {
    setEnabled("freedictionaryapi", true);
    const online = vi.spyOn(backendSession, "lookupOnlineDictionary").mockResolvedValue({
      source: "freedictionaryapi", word: "picar",
      entries: [{ headword: "picar", posLabel: "verb", senses: [{ definition: "to itch" }] }]
    });
    const results = await lookup("picar", "es");
    expect(online).toHaveBeenCalledWith("freedictionaryapi", "picar", "es");
    expect(results[0].origin).toBe("online");
    expect(results[0].articles?.[0].senses[0].definition).toBe("to itch");
  });

  it("does not let one failing dictionary silence the others", async () => {
    serveArtifacts();
    await install("sample");
    setEnabled("freedictionaryapi", true);
    vi.spyOn(backendSession, "listDictionaries").mockResolvedValue({ dictionaries: [] });
    vi.spyOn(backendSession, "lookupOnlineDictionary").mockRejectedValue(new Error("upstream down"));

    const results = await lookup("picar", "es");
    expect(results.map((result) => result.dictionaryId)).toEqual(["sample"]);
  });

  it("uses a dictionary the shipped catalogue does not name", async () => {
    // The catalogue is a starting list, not an allow-list: a server can compile something nobody
    // wrote a row for, and an installed artifact describes itself.
    serveArtifacts();
    await install("sample");
    vi.spyOn(backendSession, "listDictionaries").mockRejectedValue(new Error("offline"));
    expect(catalogue.some((entry) => entry.id === "sample")).toBe(false);
    expect((await lookup("picar", "es")).map((result) => result.dictionaryId)).toEqual(["sample"]);
  });

  it("only consults dictionaries for the language being read", async () => {
    serveArtifacts();
    await install("sample");
    vi.spyOn(backendSession, "listDictionaries").mockRejectedValue(new Error("offline"));
    expect(await lookup("picar", "ja")).toEqual([]);
  });
});

describe("reporting storage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("says what it does not know rather than guessing", async () => {
    const report = await storageReport();
    expect(report.usedBytes === null || typeof report.usedBytes === "number").toBe(true);
    expect(typeof report.persisted).toBe("boolean");
  });

  it("falls back to a memory store where IndexedDB is unavailable", async () => {
    Object.defineProperty(globalThis, "indexedDB", { configurable: true, value: undefined });
    const store = createDictionaryStore();
    await store.save({ id: "x", metadata: sample.metadata as never,
                       blob: new Blob([bytes("dict")]), index: new Blob([bytes("idx")]) });
    expect((await store.list()).map((row) => row.id)).toEqual(["x"]);
    await store.clear();
    expect(await store.list()).toEqual([]);
  });
});
