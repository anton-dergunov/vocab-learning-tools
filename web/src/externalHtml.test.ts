import { describe, expect, it } from "vitest";
import { dictionaryHtmlToText, normaliseDictionaryHtml } from "./externalHtml";
import fixtures from "./testFixtures/dictionaryHtml.json";

const payload = (dictionaryId: string, word: string): string => {
  const found = fixtures.entries.find((entry) => entry.dictionaryId === dictionaryId && entry.word === word);
  if (!found) throw new Error(`No fixture for ${dictionaryId}/${word}`);
  return found.html;
};

describe("normaliseDictionaryHtml", () => {
  it("drops the title the masthead already shows", () => {
    const html = normaliseDictionaryHtml(payload("wikdict-es-en", "picar"), "picar");
    expect(html).not.toContain("<h1");
    expect(html).toContain("Golpear algo con una punta");
  });

  it("keeps a rule between homographs rather than repeating the word", () => {
    // `sencillo` is two entries in one payload: the adjective and the noun.
    const html = normaliseDictionaryHtml(payload("wikdict-es-en", "sencillo"), "sencillo");
    expect(html).not.toContain("<h1");
    expect(html).toContain("ext-split");
    expect(html).toContain("artless");
    expect(html).toContain("single");
  });

  it("reads a bare div as the part of speech in front of a sense list", () => {
    const html = normaliseDictionaryHtml(payload("wikdict-es-en", "picar"), "picar");
    expect(html).toContain('<p class="ext-gram">verb</p>');
    expect(html).toContain('<p class="ext-tr">puncture</p>');
  });

  it("reads a div that is the whole list item as the item, not as a translation of it", () => {
    // `casa` puts each meaning alone in a list item. Marking those as translations put an arrow in
    // front of things nothing was being translated from.
    const html = normaliseDictionaryHtml(payload("wikdict-es-en", "casa"), "casa");
    expect(html).toContain("<li>house</li>");
    expect(html).not.toContain('<p class="ext-tr">house</p>');
    expect(html).not.toContain('<p class="ext-gram">house</p>');
    expect(html).toContain('<p class="ext-gram">noun</p>');
  });

  it("keeps the arrow for a translation that follows a definition", () => {
    const html = normaliseDictionaryHtml(payload("wikdict-es-en", "picar"), "picar");
    expect(html).toContain("Cortar en pedazos muy pequeños.<p class=\"ext-tr\">mince</p>");
  });

  it("recognises the part of speech even with no list beside it", () => {
    const html = normaliseDictionaryHtml(payload("wikdict-es-ru", "casa"), "casa");
    expect(html).toContain('<p class="ext-gram">noun</p>');
    expect(html).toContain('<p class="ext-tr">дом</p>');
  });

  it("maps the Yomitan content attributes onto Acervo's marks", () => {
    const html = normaliseDictionaryHtml(payload("wty-es-en", "picar"), "picar");
    expect(html).toContain('class="ext-senses"');
    expect(html).toContain('class="ext-tag"');
    expect(html).toContain('class="ext-ex"');
    expect(html).toContain('<p class="ext-t">');
    expect(html).toContain('<p class="ext-tr">');
    expect(html).toContain("<b>pica</b>");
    // Grammar and etymology stay folded away, in the same fold the rest of the article uses.
    expect(html).toContain('class="fold ext-fold"');
    expect(html).toContain('class="caret"');
    // The fold keeps the source's own heading. Renaming the summary lost it and the browser drew
    // its own "Details" in place of "Grammar" and "Etymology".
    expect(html).toContain("<summary>");
    expect(html).toMatch(/<span class="label">Grammar<\/span>/);
    expect(html).toMatch(/<span class="label">Etymology<\/span>/);
    // A definition is not a translation of itself: no arrow in front of a Yomitan gloss.
    expect(html).toContain("<li>to sting</li>");
    expect(html).not.toContain("content=");
  });

  it("keeps a non-Latin entry intact", () => {
    const html = normaliseDictionaryHtml(payload("wty-ru-en", "дом"), "дом");
    expect(html).toContain("house, building");
    expect(html).toContain("обы́скивать");
  });

  it("splits preformatted plain text into lines", () => {
    const html = normaliseDictionaryHtml(payload("ecdict-en-zh", "house"), "house");
    expect(html).toContain('<p class="ext-line">n. 房子, 住宅, 机构, 议院, 家族, 家庭</p>');
    expect(html).toContain('<p class="ext-line">[时态] housed, housing, houses</p>');
  });

  it("strips presentational markup rather than letting it fight the theme", () => {
    // §11.4: FreeDict StarDict payloads colour IPA and grammar inline, in both themes.
    const html = normaliseDictionaryHtml(
      '<h1>dog</h1><font color="gray">[dɒg]</font> <font class="grammar" color="green">n.</font>'
      + '<div style="color:#f00" bgcolor="#000">собака</div>', "dog");
    expect(html).not.toContain("<font");
    expect(html).not.toContain("color");
    expect(html).not.toContain("style=");
    expect(html).toContain("[dɒg]");
    expect(html).toContain("собака");
  });

  it("removes anything executable and any href that is not a web address", () => {
    const html = normaliseDictionaryHtml(
      '<p onclick="steal()">hi<script>steal()</script>'
      + '<a href="javascript:steal()">x</a><a href="https://en.wiktionary.org/wiki/casa">w</a></p>');
    expect(html).not.toContain("script");
    expect(html).not.toContain("onclick");
    expect(html).not.toContain("javascript:");
    expect(html).toContain('href="https://en.wiktionary.org/wiki/casa"');
    expect(html).toContain('rel="noreferrer noopener"');
  });

  it("is empty for an empty payload", () => {
    expect(normaliseDictionaryHtml("")).toBe("");
    expect(normaliseDictionaryHtml("   ")).toBe("");
  });
});

describe("dictionaryHtmlToText", () => {
  it("keeps the structure's line breaks, which is what makes it usable as grounding", () => {
    const lines = dictionaryHtmlToText(payload("wikdict-es-en", "picar"), "picar").split("\n");
    expect(lines).toContain("verb");
    expect(lines).toContain("Golpear algo con una punta, agujereándolo o no.");
    expect(lines).toContain("mince");
    expect(lines.every((line) => line === line.trim() && line.length > 0)).toBe(true);
  });

  it("carries no markup through", () => {
    const plain = dictionaryHtmlToText(payload("wty-es-en", "casa"), "casa");
    expect(plain).not.toContain("<");
    expect(plain).toContain("house");
  });
});
