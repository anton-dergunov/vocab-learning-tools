import { beforeAll, describe, expect, it } from "vitest";
import { Dictionary, blobSource, rangeSource, type ByteSource } from "./dictionary";
import sample from "./testFixtures/sampleDictionary.json";

/**
 * The other half of `tests/unit/dictionaries/test_fixture.py`.
 *
 * These files were written by the Python compiler, so this suite is the only place the format is
 * checked across the boundary it actually has to cross. A reader that agrees with a TypeScript
 * re-implementation of the writer would prove nothing.
 */
// Base64 in JSON rather than two binary files: `web/` carries no Node type definitions, so a test
// cannot call `readFileSync` without buying a dependency to do it.
const fixture = (name: "dict" | "idx") =>
  Uint8Array.from(atob(sample[name]), (character) => character.charCodeAt(0));

/** A byte source that records its reads, so "does not hold the dictionary" is testable. */
function countingSource(bytes: Uint8Array): ByteSource & { reads: number; bytesRead: number } {
  return {
    size: bytes.length,
    reads: 0,
    bytesRead: 0,
    async read(offset: number, length: number) {
      this.reads += 1;
      this.bytesRead += length;
      return bytes.slice(offset, offset + length);
    }
  };
}

describe("reading a compiled dictionary", () => {
  const blobBytes = fixture("dict");
  const indexBytes = fixture("idx");
  let dictionary: Dictionary;

  beforeAll(async () => {
    dictionary = await Dictionary.open("sample", countingSource(blobBytes), countingSource(indexBytes));
  });

  it("reports what the compiler wrote", () => {
    expect(dictionary.tier).toBe("fields");
    expect(dictionary.entryCount).toBe(45);
  });

  it("finds every headword it holds", async () => {
    for (let index = 0; index < 40; index += 1) {
      const word = `palabra${String(index).padStart(3, "0")}`;
      const entry = await dictionary.lookup(word);
      expect(entry?.articles?.[0].headword, `${word} was written but not found`).toBe(word);
    }
  });

  it("returns the whole article, not a summary of it", async () => {
    const entry = await dictionary.lookup("picar");
    const article = entry!.articles![0];
    expect(article.ipa).toBe("/piˈkaɾ/");
    expect(article.pos).toBe("verb");
    expect(article.senses).toHaveLength(2);
    expect(article.senses[0].examples?.[0].text).toBe("Picó la cebolla.");
  });

  it("keeps every article a headword has rather than the first", async () => {
    // CC-CEDICT writes one line per reading, so this character is both háng and xíng.
    const entry = await dictionary.lookup("行");
    expect(entry!.articles!.map((article) => article.reading)).toEqual(["hang2", "xing2"]);
  });

  it("keeps a part of speech Acervo's enum has no room for, as the source's own word", async () => {
    const article = (await dictionary.lookup("sobre"))!.articles![0];
    expect(article.posLabel).toBe("preposition");
    expect(article.pos).toBeUndefined();
  });

  it("finds an accented headword typed without its case", async () => {
    const entry = await dictionary.lookup("ñandú");
    expect(entry?.articles?.[0].headword).toBe("Ñandú");
  });

  it("finds a headword above the BMP, where UTF-16 order and UTF-8 order disagree", async () => {
    const entry = await dictionary.lookup("\u{1F600}");
    expect(entry?.articles?.[0].senses[0].definition).toBe("a grinning face");
  });

  it("reports an absent word as absent rather than as a neighbour", async () => {
    for (const word of ["", "   ", "palabra999", "palabr", "zzzznotaword", "picaro"]) {
      expect(await dictionary.lookup(word), `${word} should not resolve`).toBeNull();
    }
  });

  it("lists headwords by prefix without decoding any payload", async () => {
    const blob = countingSource(blobBytes);
    const search = await Dictionary.open("sample", blob, countingSource(indexBytes));
    const before = blob.reads;
    expect(await search.search("palabra00", 5))
      .toEqual(["palabra000", "palabra001", "palabra002", "palabra003", "palabra004"]);
    expect(blob.reads, "a prefix search must not touch the payload blob").toBe(before);
    expect(await search.search("zzz")).toEqual([]);
  });

  it("reads a small fraction of the index to answer one lookup", async () => {
    // The point of the format: a lookup is a binary search plus one frame, not a whole file.
    const index = countingSource(indexBytes);
    const opened = await Dictionary.open("sample", countingSource(blobBytes), index);
    const afterOpen = index.bytesRead;
    await opened.lookup("picar");
    expect(index.bytesRead - afterOpen).toBeLessThan(indexBytes.length / 2);
  });

  it("keeps only a bounded amount resident, whatever the dictionary's size", async () => {
    expect(dictionary.residentBytes).toBeLessThan(indexBytes.length);
  });

  it("refuses an index it does not understand instead of returning nonsense", async () => {
    const wrongMagic = indexBytes.slice();
    wrongMagic[0] = 0x58;
    await expect(Dictionary.open("x", countingSource(blobBytes), countingSource(wrongMagic)))
      .rejects.toThrow(/not an Acervo dictionary/);

    const wrongVersion = indexBytes.slice();
    wrongVersion[4] = 99;
    await expect(Dictionary.open("x", countingSource(blobBytes), countingSource(wrongVersion)))
      .rejects.toThrow(/Install it again/);
  });
});

describe("byte sources", () => {
  it("reads ranges out of a stored blob", async () => {
    const bytes = fixture("idx");
    const source = blobSource(new Blob([bytes]));
    expect(source.size).toBe(bytes.length);
    expect(Array.from(await source.read(4, 2))).toEqual(Array.from(bytes.slice(4, 6)));
    expect(await source.read(0, 0)).toHaveLength(0);
  });

  it("opens a dictionary the device does not hold, from a blob stored locally", async () => {
    const dictionary = await Dictionary.open(
      "sample", blobSource(new Blob([fixture("dict")])),
      blobSource(new Blob([fixture("idx")])));
    expect((await dictionary.lookup("picar"))?.articles?.[0].headword).toBe("picar");
  });

  it("asks the server for exactly the bytes it needs", async () => {
    const bytes = fixture("idx");
    const asked: string[] = [];
    const original = globalThis.fetch;
    globalThis.fetch = (async (_url: string, options: RequestInit) => {
      asked.push(String((options.headers as Record<string, string>).Range));
      const [from, to] = String((options.headers as Record<string, string>).Range)
        .replace("bytes=", "").split("-").map(Number);
      return { ok: true, arrayBuffer: async () => bytes.slice(from, to + 1).buffer };
    }) as typeof fetch;
    try {
      const source = rangeSource("https://acervo.example.com/x.idx", bytes.length);
      expect(await source.read(4, 2)).toHaveLength(2);
      expect(asked).toEqual(["bytes=4-5"]);
    } finally {
      globalThis.fetch = original;
    }
  });

  it("says so when the server refuses the read", async () => {
    const original = globalThis.fetch;
    globalThis.fetch = (async () => ({ ok: false, status: 403 })) as unknown as typeof fetch;
    try {
      await expect(rangeSource("https://acervo.example.com/x.idx", 10).read(0, 4))
        .rejects.toThrow(/could not be read from the server \(403\)/);
    } finally {
      globalThis.fetch = original;
    }
  });
});
