import { describe, expect, it } from "vitest";
import { validateGraph } from "./domain";
import {
  articleFor, articleFromDraft, inboxCount, languageOptions, shortGlossOf, strengthOf, topicOptions,
  visibleRows
} from "./selectors";
import { testGraph } from "./testGraph";
import { draftFor, parseArticle, yamlFor } from "./yaml";

const query = { language: "es", topic: "all" as const, query: "", sort: "recent" as const };

describe("vocabulary selectors", () => {
  it("keeps the fixture graph valid against the canonical model", () => {
    expect(() => validateGraph(testGraph())).not.toThrow();
  });

  it("offers a configured language that holds no words yet", () => {
    const graph = testGraph();
    graph.vocabularies.push({
      ...graph.vocabularies[0], id: "vocabru00000001", language: "ru", definitionLang: "ru",
      glossLangs: ["en"], order: 2
    });
    const options = languageOptions(graph);
    // Without this a vocabulary could never be filled: there would be nowhere to switch to before
    // its first word, and capture is the thing that would have created that word.
    const russian = options.find((option) => option.code === "ru");
    expect(russian).toMatchObject({ count: 0, configured: true, name: "Russian" });
    // Configured languages keep the owner's order rather than being ranked by size.
    expect(options.map((option) => option.code)).toEqual(["es", "en", "ru"]);
  });

  it("keeps showing a language whose vocabulary record has been removed", () => {
    const graph = testGraph();
    graph.vocabularies = graph.vocabularies.filter((entry) => entry.language !== "en");
    const options = languageOptions(graph);
    expect(options.find((option) => option.code === "en")).toMatchObject({ configured: false });
  });

  it("lists one language at a time and keeps the inbox out of the filed collections", () => {
    const graph = testGraph();
    expect(visibleRows(graph, query).map((row) => row.headword)).toEqual(["picar", "la balsa"]);
    expect(inboxCount(graph, "es")).toBe(1);
    expect(visibleRows(graph, { ...query, topic: "inbox" }).map((row) => row.headword)).toEqual(["espolvorear"]);
    expect(visibleRows(graph, { ...query, language: "en" }).map((row) => row.headword)).toEqual(["turmoil"]);
  });

  it("sorts recently added first, alphabetically past the article, and hardest first", () => {
    const graph = testGraph();
    expect(visibleRows(graph, { ...query, sort: "recent" })[0].headword).toBe("picar");
    expect(visibleRows(graph, { ...query, sort: "alpha" }).map((row) => row.headword)).toEqual(["la balsa", "picar"]);
    expect(visibleRows(graph, { ...query, sort: "hard" })[0].headword).toBe("picar");
  });

  it("searches headwords, definitions and gloss terms", () => {
    const graph = testGraph();
    expect(visibleRows(graph, { ...query, query: "dice" }).map((row) => row.headword)).toEqual(["picar"]);
    expect(visibleRows(graph, { ...query, query: "embarcación" }).map((row) => row.headword)).toEqual(["la balsa"]);
    // Search reaches the inbox, which the topic collections deliberately exclude.
    expect(visibleRows(graph, { ...query, query: "espolvorear" })).toHaveLength(1);
  });

  it("excludes tombstoned records everywhere", () => {
    const graph = testGraph();
    graph.lexemes[1].deleted = true;
    expect(visibleRows(graph, query).map((row) => row.headword)).toEqual(["picar"]);
    graph.senses[1].deleted = true;
    expect(articleFor(graph, "lexemepicar0001")!.senses).toHaveLength(1);
    expect(articleFor(graph, "lexemebalsa0001")).toBeNull();
  });

  it("derives the short form from the configured gloss language, honouring an override", () => {
    const graph = testGraph();
    const balsa = graph.lexemes[1];
    expect(shortGlossOf(graph, balsa)).toBe("raft");
    balsa.shortGloss = "a makeshift raft";
    expect(shortGlossOf(graph, balsa)).toBe("a makeshift raft");
    // English is glossed in Russian, so the Russian terms are the one-liner.
    expect(shortGlossOf(graph, graph.lexemes[3])).toBe("суматоха; смятение");
  });

  it("orders topics by their stored order and counts only filed words", () => {
    const graph = testGraph();
    const topics = topicOptions(graph, "es");
    expect(topics.map((topic) => topic.name)).toEqual(["Food", "Travel"]);
    // espolvorear is Food but still in the inbox, so it is not counted.
    expect(topics[0].count).toBe(1);
  });

  it("offers only the languages the replica actually holds", () => {
    expect(languageOptions(testGraph()).map((option) => [option.code, option.count]))
      .toEqual([["es", 3], ["en", 1]]);
  });

  it("assembles an article with its senses, examples, images, lineage and schedule", () => {
    const article = articleFor(testGraph(), "lexemepicar0001")!;
    expect(article.senses.map((entry) => entry.sense.order)).toEqual([0, 1]);
    expect(article.senses[0].examples[0].matchedForm).toBe("pica");
    expect(article.senses[0].images).toHaveLength(1);
    expect(article.senses[1].examples[0].videoTitle).toBe("Comiendo en un mercado");
    expect(article.topics.map((topic) => topic.name)).toEqual(["Food"]);
    expect(article.attestations).toHaveLength(1);
    expect(article.study?.reps).toBe(21);
  });

  it("assembles an article the store has never seen, so a proposal renders like an entry", () => {
    const graph = testGraph();
    const draft = draftFor(articleFor(graph, "lexemepicar0001")!);
    // What capture returns: no lexeme id, a topic the owner keeps, and one the owner does not.
    const proposal = { ...draft, id: null, topics: ["food", "Cetrería"] };

    const article = articleFromDraft(graph, proposal);
    expect(article.lexeme.headword).toBe("picar");
    // Topic names are matched the way a save matches them, so what you review is what will be filed.
    expect(article.topics.map((topic) => topic.id)).toEqual(["topicfood000001", "draft:topic:Cetrería"]);
    expect(article.topics.map((topic) => topic.name)).toEqual(["Food", "Cetrería"]);
    // Senses keep the parentage the document expressed by nesting, and their order.
    expect(article.senses.map((entry) => entry.sense.order)).toEqual([0, 1]);
    expect(article.senses[0].examples.every((example) => example.senseId === article.senses[0].sense.id))
      .toBe(true);
    expect(article.senses[0].images.every((image) => image.lexemeId === article.lexeme.id)).toBe(true);
    // A document cannot carry study state, so a proposal never claims to have any.
    expect(article.study).toBeNull();
  });

  it("keeps a proposal's placeholder ids out of the shape the server accepts", () => {
    const graph = testGraph();
    const stripped = { ...draftFor(articleFor(graph, "lexemepicar0001")!), id: null };
    const lexemeId = articleFromDraft(graph, stripped).lexeme.id;
    // Render-only: nothing assembled here may be written, and a leak has to fail loudly rather
    // than land in the store, so a placeholder is deliberately not a valid record id.
    expect(lexemeId).toBe("draft:lexeme");
    expect(lexemeId).not.toMatch(/^[a-z0-9]{15}$/);
  });

  it("shows exactly what the document says, so approving the preview approves the save", () => {
    const graph = testGraph();
    const document = yamlFor(articleFor(graph, "lexemepicar0001")!);
    const draft = parseArticle(document);
    // The preview is a lossless reading of the document — the other half of the round trip
    // `yaml.test.ts` pins — which is what makes reviewing the article equivalent to reviewing YAML.
    expect(draftFor(articleFromDraft(graph, draft))).toEqual(draft);
  });

  it("scales study strength from stability and leaves unscheduled words empty", () => {
    expect(strengthOf(null)).toBe(0);
    expect(strengthOf({ stability: 4.2 } as never)).toBeLessThan(strengthOf({ stability: 402.7 } as never));
    expect(strengthOf({ stability: 402.7 } as never)).toBe(4);
  });
});
