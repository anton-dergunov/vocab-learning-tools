import { describe, expect, it } from "vitest";
import { articleFor } from "./selectors";
import { testGraph } from "./testGraph";
import { draftFor, parseArticle, YAML_TEMPLATE, YamlProblems, yamlFor, yamlForDraft, type ArticleDraft } from "./yaml";

const articles = () => {
  const graph = testGraph();
  return graph.lexemes.map((lexeme) => articleFor(graph, lexeme.id)!);
};

const problemsOf = (text: string): string[] => {
  try { parseArticle(text); }
  catch (error) { return (error as YamlProblems).problems.map((problem) => problem.message); }
  throw new Error("expected the document to be refused");
};

describe("the YAML projection", () => {
  it("writes the record, its ids and the fields the reader will need back", () => {
    const document = yamlFor(articleFor(testGraph(), "lexemepicar0001")!);
    expect(document).toContain("id: lexemepicar0001");
    expect(document).toContain("topics: [Food]");
    expect(document).toContain("- {lang: en, terms: [to itch]}");
    expect(document).toContain("id: sensepicaritch0");
    // Rendered in the read view, and dropped by the projection before this change.
    expect(document).toContain("audioRef: audio/picar.mp3");
    expect(document).toContain("matchedTranslationForm: itches");
  });

  it("keeps an instant a string, so it is not read back as a date", () => {
    const document = yamlFor(articleFor(testGraph(), "lexemepicar0001")!);
    expect(document).toContain('capturedAt: "2026-02-11T12:00:00.000Z"');
    expect(parseArticle(document).attestations[0].capturedAt).toBe("2026-02-11T12:00:00.000Z");
  });

  it("writes study state as comments, because the scheduler owns it", () => {
    const document = yamlFor(articleFor(testGraph(), "lexemepicar0001")!);
    expect(document).toContain("# study · anki · reps 21 · lapses 4");
    expect(parseArticle(document)).not.toHaveProperty("study");
  });

  it("quotes a headword that would otherwise read as something else", () => {
    const graph = testGraph();
    graph.lexemes[1].headword = "yes: really";
    const document = yamlFor(articleFor(graph, graph.lexemes[1].id)!);
    expect(document).toContain('headword: "yes: really"');
    expect(parseArticle(document).headword).toBe("yes: really");
  });
});

describe("reading YAML back", () => {
  // The safety argument for editing: anything the writer forgets is a field the next save deletes.
  it("round-trips every entry in the fixture without losing a field", () => {
    articles().forEach((article) => {
      expect(parseArticle(yamlFor(article))).toEqual(draftFor(article));
    });
  });

  it("treats a record with no id as new and keeps the ids of the rest", () => {
    const article = articleFor(testGraph(), "lexemepicar0001")!;
    const document = yamlFor(article)
      .replace("- id: examplepicar010\n        text:", "- text:");
    const draft = parseArticle(document);
    expect(draft.senses[0].examples[0].id).toBeNull();
    expect(draft.senses[0].id).toBe("sensepicaritch0");
  });

  it("reports the field and the line rather than failing as a whole document", () => {
    const article = articleFor(testGraph(), "lexemepicar0001")!;
    const document = yamlFor(article).replace("pos: verb", "pos: preposition");
    try {
      parseArticle(document);
      throw new Error("expected the document to be refused");
    } catch (error) {
      const [problem] = (error as YamlProblems).problems;
      expect(problem.message).toContain('pos: must be one of');
      expect(problem.message).toContain('found "preposition"');
      expect(document.split("\n")[problem.line! - 1]).toBe("pos: preposition");
    }
  });

  it("collects every problem in one pass", () => {
    expect(problemsOf("language: es\nheadword: \"\"\nsenses: []\n")).toEqual([
      "headword: is required.",
      "senses: an entry needs at least one sense."
    ]);
  });

  it("refuses a key it does not know, rather than ignoring the typo", () => {
    const document = yamlFor(articleFor(testGraph(), "lexemepicar0001")!).replace("emoji:", "emojis:");
    expect(problemsOf(document)[0]).toContain("document.emojis: is not a field Acervo knows");
  });

  it("refuses an id that is not an Acervo id", () => {
    const document = yamlFor(articleFor(testGraph(), "lexemepicar0001")!)
      .replace("id: sensepicaritch0", "id: sense-2");
    expect(problemsOf(document)[0]).toContain("is not an Acervo id");
  });

  // The document repeats `text:` and `id:` many times; a text search would name the first one.
  it("points at the offending record, not the first one that looks like it", () => {
    const article = articleFor(testGraph(), "lexemepicar0001")!;
    const document = yamlFor(article).replace("origin: subtitle", "origin: overheard");
    try {
      parseArticle(document);
      throw new Error("expected the document to be refused");
    } catch (error) {
      const [problem] = (error as YamlProblems).problems;
      expect(problem.message).toContain("senses[1].examples[0].origin");
      expect(document.split("\n")[problem.line! - 1]).toContain("origin: overheard");
    }
  });

  it("reports a syntax error with its line", () => {
    try {
      parseArticle("language: es\nsenses:\n  - order: 0\n   definition: x\n");
      throw new Error("expected the document to be refused");
    } catch (error) {
      const [problem] = (error as YamlProblems).problems;
      expect(problem.line).toBe(4);
    }
  });
});

describe("the new-entry template", () => {
  // Not "it parses" — a blank template deliberately does not. What matters is that every key it
  // offers is one the reader accepts, so the only complaints are the blanks you came to fill in.
  it("names exactly the fields you have to fill in", () => {
    expect(problemsOf(YAML_TEMPLATE)).toEqual([
      "headword: is required.",
      "senses[0].definition: is required.",
      "senses[0].examples[0].text: is required."
    ]);
  });

  it("renders a generated draft through the same serialiser, ids and all", () => {
    // What the ingest endpoint returns: no lexeme id, because the entry is new, but minted ids on
    // the records that have to reference each other before anything is stored.
    const generated: ArticleDraft = {
      id: null, language: "es", headword: "el garfio", lemma: "garfio", reading: null, ipa: null,
      pos: "noun", gender: "masculine", register: "neutral", dialect: null, emoji: "🪝",
      topics: ["Travel"], status: "inbox", shortGloss: "hook", notes: ["Not the same as el gancho."],
      senses: [{
        id: "sense0000000091", order: 0, definition: "Gancho de metal curvo.", definitionLang: "es",
        glosses: [{ lang: "en", terms: ["hook"] }], domain: null, images: [],
        examples: [{
          id: "example00000091", text: "El disfraz de pirata viene con un garfio.", textLang: "es",
          translation: "The pirate costume comes with a hook.", translationLang: "en",
          origin: "attestation", sourceAttestationId: "attest000000091", modelId: null,
          videoRef: null, videoTitle: null, videoStart: null, imageRef: null, audioRef: null,
          note: null, matchedForm: "un garfio", matchedTranslationForm: "hook", approved: false
        }]
      }],
      attestations: [{
        id: "attest000000091", text: "El disfraz de pirata viene con un garfio.", translation: null,
        sourceUrl: null, sourceTitle: null, sourceKind: "unknown",
        capturedAt: "2026-08-29T12:00:00.000Z"
      }],
      images: []
    };
    // The contract that makes review safe: what the model proposed is exactly what a save applies.
    expect(parseArticle(yamlForDraft(generated))).toEqual(generated);
  });

  it("parses once filled in, and creates everything it describes", () => {
    const filled = YAML_TEMPLATE
      .replace('headword: ""', 'headword: sobremesa')
      .replace('definition: ""', 'definition: Charla tras la comida.')
      .replace('terms: [""]', 'terms: [after-dinner talk]')
      .replace('- text: ""', '- text: La sobremesa duró dos horas.')
      .replace('translation: ""', 'translation: The after-dinner talk lasted two hours.');
    const draft = parseArticle(filled);
    expect(draft.id).toBeNull();
    expect(draft.headword).toBe("sobremesa");
    // Left empty in the template, and the only default in the format.
    expect(draft.lemma).toBe("sobremesa");
    expect(draft.senses[0].id).toBeNull();
    expect(draft.senses[0].examples[0].id).toBeNull();
    expect(draft.senses[0].examples[0].textLang).toBe("es");
  });
});
