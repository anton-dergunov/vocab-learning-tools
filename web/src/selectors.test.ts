import { describe, expect, it } from "vitest";
import { validateGraph } from "./domain";
import {
  articleFor, inboxCount, languageOptions, shortGlossOf, strengthOf, topicOptions, visibleRows
} from "./selectors";
import { testGraph } from "./testGraph";

const query = { language: "es", topic: "all" as const, query: "", sort: "recent" as const };

describe("vocabulary selectors", () => {
  it("keeps the fixture graph valid against the canonical model", () => {
    expect(() => validateGraph(testGraph())).not.toThrow();
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
    expect(articleFor(graph, "lexemepicar0001", [])!.senses).toHaveLength(1);
    expect(articleFor(graph, "lexemebalsa0001", [])).toBeNull();
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
    const article = articleFor(testGraph(), "lexemepicar0001", [])!;
    expect(article.senses.map((entry) => entry.sense.order)).toEqual([0, 1]);
    expect(article.senses[0].examples[0].matchedForm).toBe("pica");
    expect(article.senses[0].images).toHaveLength(1);
    expect(article.senses[1].examples[0].videoTitle).toBe("Comiendo en un mercado");
    expect(article.topics.map((topic) => topic.name)).toEqual(["Food"]);
    expect(article.attestations).toHaveLength(1);
    expect(article.study?.reps).toBe(21);
    expect(article.synced).toBe(true);
  });

  it("reports an unsent local write as not yet synced", () => {
    const article = articleFor(testGraph(), "lexemepicar0001", ["lexemes:lexemepicar0001"])!;
    expect(article.synced).toBe(false);
  });

  it("scales study strength from stability and leaves unscheduled words empty", () => {
    expect(strengthOf(null)).toBe(0);
    expect(strengthOf({ stability: 4.2 } as never)).toBeLessThan(strengthOf({ stability: 402.7 } as never));
    expect(strengthOf({ stability: 402.7 } as never)).toBe(4);
  });
});
