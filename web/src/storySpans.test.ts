import { describe, expect, it } from "vitest";
import { segmentSpans, storySpans } from "./selectors";
import type { AudioSegment, StoryWord } from "./domain";

function word(lexemeId: string, forms: string[], translationForms: string[] = []): StoryWord {
  return {
    id: `w${lexemeId}`, storyId: "s1", lexemeId, position: 0, sourceText: forms[0] ?? "", forms,
    translationForms,
    ownerId: "o", deleted: false, createdAt: "", editedAt: "", editedBy: "", revision: 1
  } as StoryWord;
}

const marked = (text: string, words: StoryWord[]) =>
  storySpans(text, words).filter((span) => span.lexemeId).map((span) => span.text);

describe("marking a story's words", () => {
  it("keeps the whole text when nothing is marked", () => {
    expect(storySpans("Un perro.", [])).toEqual([{ text: "Un perro.", lexemeId: null }]);
  });

  it("puts the text back together exactly, marked or not", () => {
    const text = "Marcos vio un perro asombroso en la panadería.";
    const spans = storySpans(text, [word("l1", ["asombroso"]), word("l2", ["panadería"])]);
    expect(spans.map((span) => span.text).join("")).toBe(text);
  });

  it("marks a form wherever it appears", () => {
    expect(marked("Asombroso. Muy asombroso.", [word("l1", ["asombroso"])]))
      .toEqual(["Asombroso", "asombroso"]);
  });

  it("marks a word capitalised at the start of a sentence", () => {
    const spans = storySpans("Asombroso perro.", [word("l1", ["asombroso"])]);
    expect(spans[0]).toEqual({ text: "Asombroso", lexemeId: "l1" });
  });

  it("does not mark a word inside another word", () => {
    // `pan` must not light up the middle of `panadería`, which is a different word entirely.
    expect(marked("Compró pan en la panadería.", [word("l1", ["pan"])])).toEqual(["pan"]);
  });

  it("prefers the longer form when one contains the other", () => {
    expect(marked("Son asombrosos.", [word("l1", ["asombroso", "asombrosos"])]))
      .toEqual(["asombrosos"]);
  });

  it("ignores a form the writer did not actually write", () => {
    expect(marked("Un perro normal.", [word("l1", ["asombroso"])])).toEqual([]);
  });

  it("matches across an accent difference without shifting the text", () => {
    const text = "Fue a la panaderia y a la panadería.";
    const spans = storySpans(text, [word("l1", ["panadería"])]);
    expect(spans.map((span) => span.text).join("")).toBe(text);
    expect(marked(text, [word("l1", ["panadería"])])).toEqual(["panaderia", "panadería"]);
  });

  it("marks several different words", () => {
    const words = [word("l1", ["asombroso"]), word("l2", ["ladrar"])];
    const spans = storySpans("Es asombroso oírle ladrar.", words);
    expect(spans.filter((s) => s.lexemeId).map((s) => [s.text, s.lexemeId]))
      .toEqual([["asombroso", "l1"], ["ladrar", "l2"]]);
  });

  it("leaves a word with no forms unmarked", () => {
    expect(marked("Nada que marcar.", [word("l1", [])])).toEqual([]);
  });
});

describe("marking a translation's words", () => {
  const spans = (text: string, words: StoryWord[]) =>
    storySpans(text, words, "translationForms").filter((span) => span.lexemeId).map((span) => span.text);

  it("looks in the translation's own forms, not the story's", () => {
    const words = [word("l1", ["asombroso"], ["amazing"])];
    expect(spans("Marcos saw an amazing dog.", words)).toEqual(["amazing"]);
    // The story's own form would have marked nothing here, and the translation's marks nothing in
    // the original: the two searches are independent.
    expect(storySpans("Marcos vio un perro asombroso.", words).filter((span) => span.lexemeId).map((span) => span.text))
      .toEqual(["asombroso"]);
  });

  it("degrades to plain text when the translator reported nothing", () => {
    expect(storySpans("A dog.", [word("l1", ["perro"])], "translationForms"))
      .toEqual([{ text: "A dog.", lexemeId: null }]);
  });
});


describe("a part's text cut into the passages a recording has", () => {
  const TEXT = "Marcos subió a la balsa al amanecer. Nadie dijo nada.";
  const passage = (text: string, index = 0): AudioSegment =>
    ({ text, direction: "", audioRef: `stories/s/p-${index}.ogg`, audioMime: "audio/ogg", durationSeconds: 1 });
  const cuts = [passage("Marcos subió a la balsa "), passage("al amanecer. ", 1), passage("Nadie dijo nada.", 2)];
  const joined = (runs: ReturnType<typeof segmentSpans>) =>
    runs.map((run) => run.spans.map((span) => span.text).join("")).join("");

  it("is the text unbroken, in one ungrouped run, when there is no recording", () => {
    expect(segmentSpans(TEXT, [], [])).toEqual([{ segment: null, spans: [{ text: TEXT, lexemeId: null }] }]);
  });

  /* A clear voice records the whole part as one passage. There is nothing to tell it from, so there
     is nothing to tap, and the reader draws it exactly as it draws a part with no recording. */
  it("offers nothing to tap when the whole part is one passage", () => {
    expect(segmentSpans(TEXT, [], [passage(TEXT)]))
      .toEqual([{ segment: null, spans: [{ text: TEXT, lexemeId: null }] }]);
  });

  it("groups the runs by passage and gives back exactly the text", () => {
    const runs = segmentSpans(TEXT, [], cuts);

    expect(runs.map((run) => run.segment)).toEqual([0, 1, 2]);
    expect(joined(runs)).toBe(TEXT);
    expect(runs[1].spans).toEqual([{ text: "al amanecer. ", lexemeId: null }]);
  });

  it("keeps a marked word marked inside its passage", () => {
    const runs = segmentSpans(TEXT, [word("l1", ["balsa"])], cuts);

    expect(runs[0].spans).toEqual([
      { text: "Marcos subió a la ", lexemeId: null },
      { text: "balsa", lexemeId: "l1" },
      { text: " ", lexemeId: null }
    ]);
  });

  it("cuts a marked word at a seam and keeps the mark on both halves", () => {
    const runs = segmentSpans("La balsa flota.", [word("l1", ["balsa"])], [passage("La bal"), passage("sa flota.", 1)]);

    expect(runs[0].spans.at(-1)).toEqual({ text: "bal", lexemeId: "l1" });
    expect(runs[1].spans[0]).toEqual({ text: "sa", lexemeId: "l1" });
    expect(joined(runs)).toBe("La balsa flota.");
  });

  it("gives up on passages that do not join to the text, rather than draw them over other words", () => {
    const runs = segmentSpans("Marcos subió a otra cosa.", [], cuts);

    expect(runs).toHaveLength(1);
    expect(runs[0].segment).toBeNull();
    expect(joined(runs)).toBe("Marcos subió a otra cosa.");
  });

  it("counts characters the way the text does, so an accent or an emoji cannot shift a seam", () => {
    const text = "¡Qué frío! 🥶 Nadie contestó.";
    const runs = segmentSpans(text, [], [passage("¡Qué frío! 🥶 "), passage("Nadie contestó.", 1)]);

    expect(runs.map((run) => run.spans.map((span) => span.text).join(""))).toEqual(["¡Qué frío! 🥶 ", "Nadie contestó."]);
  });
});
