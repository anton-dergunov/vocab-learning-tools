import { describe, expect, it } from "vitest";
import { parse } from "yaml";
import { SCHEMA_VERSION } from "./api";
import type { VocabularyGraph } from "./domain";
import { MemoryDatabase } from "./localDatabase";
import { LocalAcervoRepository } from "./repository";
import { articleFor, lexemesIn } from "./selectors";
import { testGraph, TEST_OWNER } from "./testGraph";
import { fakeRemote } from "./testRemote";
import {
  BUNDLE_FORMAT, bundleName, exportBundle, importBundle, MANIFEST_FILE, picturesIn, readBundle, remintIds,
  slugFor, TOPICS_FILE, VOCABULARIES_FILE, type BundleFile, type ExportOptions
} from "./transfer";
import { parseArticle } from "./yaml";

const AT = "2026-09-01T12:00:00.000Z";
const everything: ExportOptions = { language: "all", markdown: true, images: false };

const bundle = (graph = testGraph(), options: ExportOptions = everything) => exportBundle(graph, options, AT);
const at = (files: BundleFile[], path: string) => files.find((file) => file.path === path)!;

async function emptyReplica() {
  const repository = new LocalAcervoRepository(new MemoryDatabase());
  await repository.load(TEST_OWNER);
  repository.attachRemote(fakeRemote());
  return repository;
}

describe("exporting a bundle", () => {
  it("lays the files out by language, with the shared records at the root", () => {
    const paths = bundle().map((file) => file.path);
    expect(paths.slice(0, 3)).toEqual([MANIFEST_FILE, VOCABULARIES_FILE, TOPICS_FILE]);
    expect(paths).toContain("es/picar.yaml");
    expect(paths).toContain("en/turmoil.yaml");
    expect(paths).toContain("markdown/Spanish vocab - Food.md");
  });

  it("carries a manifest that says what it is, and nothing about the account", () => {
    const manifest = parse(at(bundle(), MANIFEST_FILE).text) as Record<string, unknown>;
    expect(manifest).toEqual({
      format: BUNDLE_FORMAT,
      schemaVersion: SCHEMA_VERSION,
      exportedAt: AT,
      languages: ["es", "en"],
      counts: { vocabularies: 2, topics: 2, lexemes: 4 }
    });
    const text = bundle().map((file) => file.text).join("\n");
    expect(text).not.toContain(TEST_OWNER);
    expect(text).not.toContain("dataset");
  });

  it("writes the vocabulary and topic records the article documents cannot express", () => {
    expect(parse(at(bundle(), VOCABULARIES_FILE).text)).toEqual([
      { language: "es", definitionLang: "es", glossLangs: ["en"], notesLang: "en", displayName: null, flag: null, order: 0 },
      { language: "en", definitionLang: "en", glossLangs: ["ru"], notesLang: "ru", displayName: null, flag: null, order: 1 }
    ]);
    expect(parse(at(bundle(), TOPICS_FILE).text)).toEqual([
      { name: "Food", icon: "🍽️", order: 0 },
      { name: "Travel", icon: "🧭", order: 1 }
    ]);
  });

  it("strips every id but the ones the file itself points at", () => {
    /* eslint-disable @typescript-eslint/no-explicit-any */
    const word = parse(at(bundle(), "es/picar.yaml").text) as any;
    expect(word.id).toBeUndefined();
    expect(word.senses[0].id).toBeUndefined();
    expect(word.senses[0].imagePrompts[0].id).toBeUndefined();
    // Kept, because something in this same document names them: an example names the attestation it
    // was drawn from, and a picture names the example whose scene it draws. Drop either and the
    // lineage is gone. `remintIds` re-mints both on import, so the bundle depends on no account.
    expect(word.attestations[0].id).toBe("attestpicar0010");
    expect(word.senses[0].examples[0].sourceAttestationId).toBe("attestpicar0010");
    expect(word.senses[0].examples[0].id).toBe("examplepicar010");
  });

  it("names a picture after the word file it belongs to, and carries no bytes by default", () => {
    // Export-only, exactly as the Obsidian mirror is: `readBundle` never looks at `media/`, so the
    // import path grows no second writer. The bytes are `TransferPanel`'s business — this module
    // holds no transport and should not grow one.
    expect(bundle().map((file) => file.path).some((path) => path.startsWith("media/"))).toBe(false);
    expect(picturesIn(testGraph(), { language: "es", markdown: false, images: true })).toEqual([
      { path: "media/es/picar-1.webp", reference: "images/lexemepicar0001/imagepicar00010.webp" }
    ]);
  });

  it("leaves the server's own facts about a picture behind", () => {
    /* eslint-disable @typescript-eslint/no-explicit-any */
    const word = parse(at(bundle(), "es/picar.yaml").text) as any;
    // Not references — facts about the machine that drew it. `imageRef` embeds a lexeme id that
    // will not exist after import, so keeping it imports a live-looking reference to nothing.
    expect(word.senses[0].imagePrompts[0].imageRef).toBeUndefined();
    expect(word.senses[0].imagePrompts[0].imageModelId).toBeUndefined();
  });

  it("says what an id-less document means in its own header", () => {
    expect(at(bundle(), "es/picar.yaml").text)
      .toContain("# No ids here: everything in this document is created when you save.");
  });

  it("leaves study state out — it is review history, not vocabulary", () => {
    expect(at(bundle(), "es/picar.yaml").text).not.toContain("study ·");
  });

  it("exports one language on its own, for handing to someone else", () => {
    const paths = bundle(testGraph(), { language: "es", markdown: true, images: false }).map((file) => file.path);
    expect(paths).toContain("es/picar.yaml");
    expect(paths.some((path) => path.startsWith("en/"))).toBe(false);
    expect(parse(at(bundle(testGraph(), { language: "es", markdown: true, images: false }), VOCABULARIES_FILE).text))
      .toHaveLength(1);
  });

  it("omits the markdown when it is not wanted", () => {
    const paths = bundle(testGraph(), { language: "all", markdown: false, images: false }).map((file) => file.path);
    expect(paths.some((path) => path.startsWith("markdown/"))).toBe(false);
  });

  it("names the file after what is in it", () => {
    expect(bundleName("all", AT)).toBe("acervo-all-2026-09-01.zip");
    expect(bundleName("es", AT)).toBe("acervo-es-2026-09-01.zip");
  });
});

describe("naming a word file", () => {
  const word = (lemma: string, reading: string | null = null) =>
    slugFor({ headword: lemma, lemma, reading });

  it("strips accents and spaces rather than leaving them in a filename", () => {
    expect(word("ponerse malo")).toBe("ponerse-malo");
    expect(word("desmayarse")).toBe("desmayarse");
    expect(word("niño")).toBe("nino");
    expect(word("¿qué tal?")).toBe("que-tal");
  });

  it("uses the lemma, so the article does not file half a vocabulary under la-", () => {
    expect(slugFor({ headword: "la balsa", lemma: "balsa", reading: null })).toBe("balsa");
  });

  it("transliterates Cyrillic", () => {
    expect(word("суматоха")).toBe("sumatokha");
    expect(word("ёжик")).toBe("ezhik");
  });

  it("falls back to the reading for a script with no Latin form", () => {
    expect(word("麻烦", "máfan")).toBe("mafan");
    expect(word("麻烦")).toBe("word");
  });

  it("separates two words that would share a name", () => {
    const graph = testGraph();
    graph.lexemes[1] = { ...graph.lexemes[1], headword: "picár", lemma: "picár" };
    const paths = exportBundle(graph, everything, AT).map((file) => file.path);
    expect(paths).toContain("es/picar.yaml");
    expect(paths).toContain("es/picar-2.yaml");
  });
});

describe("reading a bundle", () => {
  it("reads back everything it wrote", () => {
    const plan = readBundle(bundle());
    expect(plan.problems).toEqual([]);
    expect(plan.vocabularies).toHaveLength(2);
    expect(plan.topics).toHaveLength(2);
    expect(plan.articles.map((article) => article.path))
      .toEqual(["en/turmoil.yaml", "es/balsa.yaml", "es/espolvorear.yaml", "es/picar.yaml"]);
  });

  it("accepts a single word document on its own", () => {
    const plan = readBundle([at(bundle(), "es/picar.yaml")]);
    expect(plan.articles).toHaveLength(1);
    expect(plan.articles[0].draft.headword).toBe("picar");
  });

  it("looks through the folder a re-zipped export is wrapped in", () => {
    const wrapped = bundle().map((file) => ({ ...file, path: `acervo-2026-09-01/${file.path}` }));
    expect(readBundle(wrapped).articles).toHaveLength(4);
  });

  it("reports a broken word file by name and keeps the rest", () => {
    const files = bundle().map((file) =>
      file.path === "es/picar.yaml" ? { ...file, text: "headword: picar\nsenses: []\n" } : file);
    const plan = readBundle(files);
    expect(plan.articles.map((article) => article.path)).not.toContain("es/picar.yaml");
    expect(plan.problems).toHaveLength(1);
    expect(plan.problems[0].path).toBe("es/picar.yaml");
    expect(plan.problems[0].message).toContain("at least one sense");
  });

  it("reads a version 6 bundle, which is the safety net the database rebuild rested on", () => {
    // A real version 6 word file, pinned as text rather than derived from today's writer: examples
    // carry no ids, and a picture has none of version 7's keys. Nothing was renamed and nothing
    // removed, so `upgradeBundle` rewrites no text — it accepts the version and the reader finds
    // the new keys simply absent.
    const older = [
      "language: es",
      "headword: picar",
      "lemma: picar",
      "pos: verb",
      "status: active",
      "shortGloss: to itch",
      "senses:",
      "  - order: 0",
      "    definition: Producir comezón.",
      "    definitionLang: es",
      "    glosses:",
      "      - {lang: en, terms: [to itch]}",
      "    examples:",
      "      - text: Me pica la nariz.",
      "        textLang: es",
      "        origin: llm",
      "    imagePrompts:",
      "      - prompt: A hand hovering near an itchy nose.",
      "        styleId: flat-vector",
      "        seed: 184521",
      "        modelId: demo-prompt",
      "        promptVersion: demo-v1",
      ""
    ].join("\n");

    const files = bundle()
      .filter((file) => !file.path.endsWith(".yaml") || file.path === MANIFEST_FILE
        || file.path === VOCABULARIES_FILE || file.path === TOPICS_FILE)
      .map((file) => file.path === MANIFEST_FILE
        ? { ...file, text: file.text.replace(`schemaVersion: ${SCHEMA_VERSION}`, "schemaVersion: 6") }
        : file)
      .concat([{ path: "es/picar.yaml", text: older }]);

    const plan = readBundle(files);
    expect(plan.problems).toEqual([]);
    const word = plan.articles.find((article) => article.path === "es/picar.yaml")!.draft;
    const image = word.senses.flatMap((sense) => sense.images)[0];
    expect(image.prompt).toBe("A hand hovering near an itchy nose.");
    // No anchor is invented for it. A version 6 bundle carries no example ids at all, so matching
    // by position or by text would be a guess — and a wrong anchor puts the picture under the
    // wrong sentence, which is worse than putting it under none.
    expect(image.exampleId).toBeNull();
  });

  it("refuses a bundle from another schema version, naming both", () => {
    const files = bundle().map((file) => file.path === MANIFEST_FILE
      ? { ...file, text: file.text.replace(`schemaVersion: ${SCHEMA_VERSION}`, "schemaVersion: 4") }
      : file);
    expect(() => readBundle(files))
      .toThrow(new RegExp(`schema version 4 .*version ${SCHEMA_VERSION}`));
  });

  it("refuses an unknown layout separately from an unknown record shape", () => {
    const files = bundle().map((file) => file.path === MANIFEST_FILE
      ? { ...file, text: file.text.replace(BUNDLE_FORMAT, "acervo-export/2") }
      : file);
    expect(() => readBundle(files)).toThrow(/acervo-export\/2 layout/);
  });

  it("refuses a file that is not an export at all", () => {
    expect(() => readBundle([{ path: "notes.txt", text: "hello" }])).toThrow(/does not look like/);
  });
});

describe("importing a bundle", () => {
  it("restores a whole vocabulary into an empty replica, lineage included", async () => {
    const repository = await emptyReplica();
    const report = await importBundle(repository, readBundle(bundle()));

    expect(report).toMatchObject({ vocabulariesAdded: 2, topicsAdded: 2, added: 4, aborted: false });
    expect(report.failed).toEqual([]);
    expect(report.skipped).toEqual([]);

    const restored = repository.snapshot() as VocabularyGraph;
    expect(lexemesIn(restored, "es").map((lexeme) => lexeme.headword).sort())
      .toEqual(["espolvorear", "la balsa", "picar"]);

    const picar = lexemesIn(restored, "es").find((lexeme) => lexeme.headword === "picar")!;
    const article = articleFor(restored, picar.id)!;
    expect(article.senses.map((entry) => entry.sense.definition))
      .toEqual(["Producir comezón.", "Cortar en trozos pequeños."]);
    expect(article.topics.map((topic) => topic.name)).toEqual(["Food"]);
    expect(article.lexeme.notes).toEqual(["The sense is carried by the object, not the verb."]);

    // The reference survived the round trip and points at this word's own attestation.
    const example = article.senses[0].examples[0];
    expect(example.origin).toBe("attestation");
    expect(example.sourceAttestationId).toBe(article.attestations[0].id);
    expect(article.attestations[0].text).toBe("cuidado que esa salsa pica un monton");

    // Every id is this database's own, not the one the bundle was written from.
    expect(picar.id).not.toBe("lexemepicar0001");
    expect(article.attestations[0].id).not.toBe("attestpicar0010");
  });

  it("skips a word already held rather than overwriting or duplicating it", async () => {
    const repository = await emptyReplica();
    const plan = readBundle(bundle());
    await importBundle(repository, plan);
    const second = await importBundle(repository, readBundle(bundle()));

    expect(second).toMatchObject({ vocabulariesAdded: 0, topicsAdded: 0, added: 0 });
    expect(second.skipped.map((entry) => entry.headword).sort())
      .toEqual(["espolvorear", "la balsa", "picar", "turmoil"]);
    expect(repository.snapshot().lexemes.filter((lexeme) => !lexeme.deleted)).toHaveLength(4);
  });

  it("reports one refused word by file and imports the others", async () => {
    const repository = await emptyReplica();
    const plan = readBundle(bundle());
    // A topic nothing created: `saveArticle` refuses it deliberately, and only that word suffers.
    plan.articles.find((article) => article.path === "es/picar.yaml")!.draft.topics = ["Medicina"];
    const report = await importBundle(repository, plan);

    expect(report.added).toBe(3);
    expect(report.failed).toHaveLength(1);
    expect(report.failed[0].path).toBe("es/picar.yaml");
    expect(report.failed[0].message).toContain("Medicina");
  });

  it("stops at the first word when the server is unreachable, and writes nothing", async () => {
    const repository = await emptyReplica();
    repository.attachRemote(null);
    const report = await importBundle(repository, readBundle(bundle()));

    expect(report.aborted).toBe(true);
    expect(report.added).toBe(0);
    expect(report.vocabulariesAdded).toBe(0);
    expect(repository.snapshot().lexemes).toEqual([]);
  });

  it("stops when it is cancelled", async () => {
    const repository = await emptyReplica();
    const signal = { cancelled: false };
    const report = await importBundle(repository, readBundle(bundle()), (done) => {
      if (done >= 3) signal.cancelled = true;
    }, signal);

    expect(report.aborted).toBe(true);
    expect(report.added).toBe(0);
  });

  it("counts every record it is going to touch as it goes", async () => {
    const repository = await emptyReplica();
    const steps: [number, number][] = [];
    await importBundle(repository, readBundle(bundle()), (done, total) => steps.push([done, total]));
    expect(steps).toHaveLength(8);
    expect(steps.at(-1)).toEqual([8, 8]);
  });
});

describe("re-minting ids", () => {
  it("rewrites a reference to match the attestation it now names", () => {
    const draft = parseArticle(at(bundle(), "es/picar.yaml").text);
    const minted = remintIds(draft);
    expect(minted.id).toBeNull();
    expect(minted.attestations[0].id).not.toBe("attestpicar0010");
    expect(minted.attestations[0].id).toMatch(/^[a-z0-9]{15}$/);
    expect(minted.senses[0].examples[0].sourceAttestationId).toBe(minted.attestations[0].id);
    expect(minted.senses[0].id).toBeNull();
  });

  it("rewrites a picture's anchor to match the example it now names", () => {
    const draft = parseArticle(at(bundle(), "es/picar.yaml").text);
    const minted = remintIds(draft);
    const example = minted.senses[0].examples[0];
    expect(example.id).not.toBe("examplepicar010");
    expect(example.id).toMatch(/^[a-z0-9]{15}$/);
    expect(minted.senses[0].images[0].exampleId).toBe(example.id);
  });

  it("drops a reference that names nothing in the document rather than inventing one", () => {
    const draft = parseArticle(at(bundle(), "es/picar.yaml").text);
    draft.attestations = [];
    draft.senses[0].examples = [];
    const minted = remintIds(draft);
    expect(minted.senses[0].examples).toEqual([]);
    // The picture survives its anchor: a sentence you deleted must not take the drawing with it.
    expect(minted.senses[0].images[0].exampleId).toBeNull();
  });
});
