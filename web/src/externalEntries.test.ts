import { describe, expect, it } from "vitest";
import type { LookupResult } from "./dictionaries";
import { externalEntryOf, glossOf, mergeHits, referenceTextOf, type RawHit } from "./externalEntries";

const hit = (word: string, dictionaryId: string, origin: RawHit["origin"], gloss?: string): RawHit =>
  ({ word, dictionaryId, name: dictionaryId, origin, gloss });

describe("mergeHits", () => {
  it("collapses one word held by several dictionaries into one row", () => {
    const rows = mergeHits("casa", [
      hit("casa", "kaikki-es-es", "device"),
      hit("casa", "wikdict-es-en", "device"),
      hit("casa", "freedictionaryapi", "online")
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0].sources.map((source) => source.dictionaryId))
      .toEqual(["kaikki-es-es", "wikdict-es-en", "freedictionaryapi"]);
  });

  it("puts the word actually typed first, however it sorts", () => {
    const rows = mergeHits("casa", [
      hit("casaca", "a", "device"), hit("casal", "a", "device"), hit("casa", "a", "device")
    ]);
    expect(rows.map((row) => row.word)).toEqual(["casa", "casal", "casaca"]);
  });

  it("prefers the nearest source for the plate and lists sources nearest first", () => {
    const rows = mergeHits("casa", [
      hit("casa", "online-one", "online"),
      hit("casa", "server-one", "server"),
      hit("casa", "device-one", "device")
    ]);
    expect(rows[0].origin).toBe("device");
    expect(rows[0].sources.map((source) => source.origin)).toEqual(["device", "server", "online"]);
  });

  it("treats a difference of case or accent as one word", () => {
    const rows = mergeHits("casa", [hit("Casa", "a", "device"), hit("casa", "b", "device")]);
    expect(rows).toHaveLength(1);
    expect(rows[0].sources).toHaveLength(2);
  });

  it("keeps the first gloss offered, so the list does not flicker as slower sources land", () => {
    const rows = mergeHits("casa", [
      hit("casa", "a", "device", "house"), hit("casa", "b", "online", "dwelling")
    ]);
    expect(rows[0].gloss).toBe("house");
  });

  it("sorts by UTF-8 bytes, the order the index is built in", () => {
    // JavaScript's own string comparison is over UTF-16 code units, which disagrees above the BMP.
    const rows = mergeHits("", [hit("\u{20000}", "a", "device"), hit("Ａ", "a", "device")]);
    expect(rows.map((row) => row.word)).toEqual(["Ａ", "\u{20000}"]);
  });
});

describe("glossOf", () => {
  it("joins the first few definitions of a mapped entry", () => {
    expect(glossOf({
      dictionaryId: "a", word: "picar", tier: "fields",
      articles: [{ headword: "picar", senses: [
        { definition: "to itch" }, { definition: "to chop" }, { definition: "to sting" },
        { definition: "to pique" }] }]
    })).toBe("to itch; to chop; to sting");
  });

  it("falls back to the visible text of an html entry", () => {
    expect(glossOf({
      dictionaryId: "a", word: "casa", tier: "html",
      html: "<h1>casa</h1><ol><li>Vivienda.<div>house</div></li></ol>"
    })).toContain("Vivienda");
  });
});

describe("externalEntryOf", () => {
  const fields: LookupResult = {
    dictionaryId: "kaikki-es-es", name: "Wiktionary (es→es)", attribution: "Wiktionary. CC BY-SA 4.0.",
    licence: "CC BY-SA 4.0", origin: "device", sourceLang: "es",
    entry: { dictionaryId: "kaikki-es-es", word: "picar", tier: "fields", articles: [{
      headword: "picar", ipa: "[piˈkaɾ]", posLabel: "verb", language: "es",
      senses: [{ definition: "Cortar en pedazos muy pequeños.",
                 examples: [{ text: "Picar cebollas.", translation: "To chop onions." }] }]
    }] }
  };
  const online: LookupResult = {
    dictionaryId: "freedictionaryapi", name: "Free Dictionary API", attribution: "freedictionaryapi.com",
    licence: "CC BY-SA 4.0", origin: "online", sourceLang: "es",
    articles: [{ headword: "picar", posLabel: "verb", senses: [{ definition: "to itch" }] }]
  };

  it("orders sections by how near the source is", () => {
    const entry = externalEntryOf("picar", [online, fields]);
    expect(entry.sections.map((section) => section.origin)).toEqual(["device", "online"]);
  });

  it("leads with a mapped section over a restyled one from the same place", () => {
    const markup: LookupResult = {
      dictionaryId: "wikdict-es-en", name: "WikDict (es→en)", attribution: "WikDict",
      licence: "CC BY-SA 4.0", origin: "device", sourceLang: "es",
      entry: { dictionaryId: "wikdict-es-en", word: "picar", tier: "html", html: "<p>puncture</p>" }
    };
    // Alphabetically WikDict would come first; the mapped entry is the one that reads like an
    // Acervo article, so it leads regardless.
    const entry = externalEntryOf("picar", [markup, fields]);
    expect(entry.sections.map((section) => section.tier)).toEqual(["fields", "html"]);
  });

  it("takes each masthead fact from the first source that knows it", () => {
    const entry = externalEntryOf("picar", [fields, online]);
    expect(entry.ipa).toBe("[piˈkaɾ]");
    expect(entry.posLabel).toBe("verb");
    expect(entry.language).toBe("es");
  });

  it("renders an online answer through the same shape as a stored one", () => {
    const entry = externalEntryOf("picar", [online]);
    expect(entry.sections[0].articles[0].senses[0].definition).toBe("to itch");
    expect(entry.sections[0].tier).toBe("fields");
  });

  it("sanitises an html section on the way in, not at the point of rendering", () => {
    const entry = externalEntryOf("casa", [{
      dictionaryId: "wikdict-es-en", name: "WikDict", attribution: "WikDict", licence: "CC BY-SA 4.0",
      origin: "device", sourceLang: "es",
      entry: { dictionaryId: "wikdict-es-en", word: "casa", tier: "html",
               html: '<h1>casa</h1><script>steal()</script><ol><li>Vivienda.</li></ol>' }
    }]);
    expect(entry.sections[0].html).not.toContain("script");
    expect(entry.sections[0].html).toContain("Vivienda");
  });
});

describe("referenceTextOf", () => {
  it("carries what was on screen, not a richer thing the reader never saw", () => {
    const text = referenceTextOf(externalEntryOf("picar", [{
      dictionaryId: "kaikki-es-es", name: "Wiktionary (es→es)", attribution: "Wiktionary",
      licence: "CC BY-SA 4.0", origin: "device", sourceLang: "es",
      entry: { dictionaryId: "kaikki-es-es", word: "picar", tier: "fields", articles: [{
        headword: "picar", posLabel: "verb",
        senses: [{ definition: "Cortar en pedazos muy pequeños.",
                   examples: [{ text: "Picar cebollas.", translation: "To chop onions." }] }]
      }] }
    }]));
    expect(text).toContain("## Wiktionary (es→es)");
    expect(text).toContain("1. Cortar en pedazos muy pequeños.");
    expect(text).toContain("Picar cebollas. — To chop onions.");
    expect(text).not.toContain("<");
  });
});
