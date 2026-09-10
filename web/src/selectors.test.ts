import { describe, expect, it } from "vitest";
import { validateGraph } from "./domain";
import {
  articleFor, articleFromDraft, imageWork, inboxCount, isRetryable, languageOptions, shortGlossOf,
  strengthOf, topicOptions, visibleRows
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
      ...graph.vocabularies[0], id: "vocabru00000001", language: "ru", definitionLang: "ru", notesLang: "en",
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


describe("how many pictures a sense shows", () => {
  it("shows one, keeping the drawn one over a bare brief", () => {
    // What an import used to leave behind: the document's row under a random id and the restored
    // picture's under the derived one, so the sense had an empty frame *and* a picture.
    const graph = testGraph();
    const [drawn] = graph.imagePrompts;
    graph.imagePrompts.push({
      ...drawn, id: "imagepicar00099", imageRef: null, imageModelId: null,
      editedAt: "2030-01-01T00:00:00.000Z"
    });

    const [sense] = articleFor(graph, "lexemepicar0001")!.senses;
    expect(sense.images.map((image) => image.id)).toEqual(["imagepicar00010"]);
  });

  it("falls back to the most recently edited when neither has a picture", () => {
    const graph = testGraph();
    const [first] = graph.imagePrompts;
    Object.assign(first, { imageRef: null, imageModelId: null, editedAt: "2026-01-01T00:00:00.000Z" });
    graph.imagePrompts.push({
      ...first, id: "imagepicar00099", editedAt: "2026-06-01T00:00:00.000Z"
    });

    const [sense] = articleFor(graph, "lexemepicar0001")!.senses;
    expect(sense.images.map((image) => image.id)).toEqual(["imagepicar00099"]);
  });
});

describe("what still needs a picture", () => {
  /* A query against the replica, never a stored queue — which is also how the interface reports
     work the *server's* sweep is doing, with no job store to poll and deliberately none to build. */

  const pictured = () => {
    const graph = testGraph();
    const [drawn] = graph.imagePrompts;
    return { graph, drawn };
  };

  it("counts a drawn picture as done and every other sense as unbriefed", () => {
    const { graph } = pictured();
    const work = imageWork(graph);
    expect(work.drawn.map((entry) => entry.prompt.id)).toEqual(["imagepicar00010"]);
    expect(work.undrawn).toEqual([]);
    // Every other sense in the fixture has no prompt row at all.
    expect(work.unbriefed.length).toBeGreaterThan(0);
    expect(work.unbriefed.every((item) => item.senseId !== "sensepicaritch0")).toBe(true);
  });

  it("separates briefed-not-drawn from attempted-and-still-blank", () => {
    const { graph, drawn } = pictured();
    Object.assign(drawn, { imageRef: null, imageModelId: null, attempts: 0 });
    expect(imageWork(graph).undrawn.map((entry) => entry.prompt.id)).toEqual([drawn.id]);

    drawn.attempts = 2;
    drawn.failureReason = "the provider declined to draw this";
    expect(imageWork(graph).undrawn).toEqual([]);
    expect(imageWork(graph).failed.map((entry) => entry.prompt.id)).toEqual([drawn.id]);
  });

  it("counts a sense the owner ruled on rather than offering it again", () => {
    const { graph, drawn } = pictured();
    Object.assign(drawn, { imageRef: null, imageModelId: null, suppressed: true });
    const work = imageWork(graph);
    expect(work.suppressed.map((entry) => entry.prompt.id)).toEqual([drawn.id]);
    expect(work.undrawn).toEqual([]);
    expect(work.failed).toEqual([]);
  });

  it("says what will be tried again, and the threshold is the only thing that decides", () => {
    const { drawn } = pictured();
    Object.assign(drawn, { imageRef: null, imageModelId: null, attempts: 1 });
    expect(isRetryable(drawn, 4)).toBe(true);
    drawn.attempts = 4;
    expect(isRetryable(drawn, 4)).toBe(false);

    drawn.attempts = 0;
    drawn.suppressed = true;
    expect(isRetryable(drawn, 4)).toBe(false);
  });

  it("names a picture the way the article does, so the two can be read together", () => {
    const { graph } = pictured();
    const [entry] = imageWork(graph).drawn;
    expect(entry.headword).toBe("picar");
    // 1-based, matching the "01" the article prints beside the sense.
    expect(entry.senseNumber).toBe(1);
  });

  it("puts the most recently written picture first, whichever engine wrote it", () => {
    // The panel used to show a session log, which emptied on reload and could never mention a
    // picture the server's sweep drew overnight. `editedAt` is on the record, so this can.
    const graph = testGraph();
    const [first] = graph.imagePrompts;
    graph.imagePrompts.push({
      ...first, id: "imagepicar00020", senseId: "sensepicarchop0",
      imageRef: "images/lexemepicar0001/imagepicar00020.webp",
      editedAt: "2026-09-01T00:00:00.000Z"
    });
    first.editedAt = "2026-01-01T00:00:00.000Z";

    expect(imageWork(graph).drawn.map((entry) => entry.prompt.id))
      .toEqual(["imagepicar00020", "imagepicar00010"]);
  });

  it("leaves a sense whose word was deleted, rather than being told about it", () => {
    const { graph } = pictured();
    const before = imageWork(graph).unbriefed.length;
    graph.lexemes.forEach((lexeme) => { lexeme.deleted = true; });
    expect(imageWork(graph).unbriefed).toEqual([]);
    expect(before).toBeGreaterThan(0);
  });
});
