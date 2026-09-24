import { describe, expect, it } from "vitest";
import type { PhotoPoint, PhotoReading, PhotoWord } from "./api";
import {
  cropRegion, hitTest, photoRegionFor, selectedText, selectionIn, sentenceOf, sentenceOutlines, span, tapped, wordOutlines
} from "./photoText";

/* A photo 1000 × 500 px holding two printed lines, each word 0.1 wide and 0.04 tall:

     line 0:  La   pala-                (y 0.10–0.14)
     line 1:  bra  dicha  .  Otra       (y 0.20–0.24)

   "pala-" / "bra" is one word with two outlines, as the server joins it. */
const box = (x: number, y: number, w = 0.1, h = 0.04): PhotoPoint[] => [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];

function word(id: string, text: string, start: number, lineId: string, polygons: PhotoPoint[][], confidence = 0.95): PhotoWord {
  return { id, text, polygons, confidence, lineId, start, end: start + text.length };
}

const TEXT = "La palabra dicha. Otra";
const READING: PhotoReading = {
  photoRef: "photos/owner0000000001/0123456789abcdef.jpg",
  width: 1000,
  height: 500,
  language: "es",
  vocabulary: true,
  readBy: { provider: "google-vision", model: "document-text-detection" },
  text: TEXT,
  words: [
    word("w0", "La", 0, "l0", [box(0.1, 0.1)]),
    word("w1", "palabra", 3, "l0", [box(0.25, 0.1), box(0.1, 0.2)]),
    word("w2", "dicha", 11, "l1", [box(0.25, 0.2)]),
    word("w3", ".", 16, "l1", [box(0.35, 0.2, 0.01)]),
    word("w4", "Otra", 18, "l1", [box(0.4, 0.2)], 0.3)
  ],
  lines: [
    { id: "l0", polygon: [[0.1, 0.1], [0.35, 0.1], [0.35, 0.14], [0.1, 0.14]], wordIds: ["w0", "w1"] },
    { id: "l1", polygon: [[0.1, 0.2], [0.5, 0.2], [0.5, 0.24], [0.1, 0.24]], wordIds: ["w1", "w2", "w3", "w4"] }
  ],
  sentences: [
    { id: "s0", text: "La palabra dicha.", wordIds: ["w0", "w1", "w2", "w3"], start: 0, end: 17, truncatedStart: false, truncatedEnd: false },
    { id: "s1", text: "Otra", wordIds: ["w4"], start: 18, end: 22, truncatedStart: false, truncatedEnd: true }
  ]
};

describe("finding the word under a finger", () => {
  it("finds the word whose outline was tapped", () => {
    expect(hitTest(READING, [0.12, 0.12])).toBe("w0");
  });

  it("finds a hyphenated word from either of its halves", () => {
    expect(hitTest(READING, [0.3, 0.12])).toBe("w1");
    expect(hitTest(READING, [0.15, 0.22])).toBe("w1");
  });

  it("forgives a tap just beside a word, measured against the word's own height", () => {
    // 0.02 below the word is 10 px, and the word is 20 px tall: within reach.
    expect(hitTest(READING, [0.12, 0.16])).toBe("w0");
  });

  it("selects nothing for a tap on nothing, rather than the nearest word a line away", () => {
    // Halfway between the lines: 30 px from either, more than half a 20 px word.
    expect(hitTest(READING, [0.12, 0.17])).toBeNull();
    expect(hitTest(READING, [0.9, 0.9])).toBeNull();
  });

  it("does not select punctuation Vision reported as a word of its own", () => {
    expect(hitTest(READING, [0.355, 0.22])).not.toBe("w3");
  });
});

describe("growing a selection into a phrase", () => {
  it("starts with the word tapped", () => {
    expect(tapped(READING, [], "w2")).toEqual(["w2"]);
  });

  it("extends to a neighbour in the same sentence", () => {
    expect(tapped(READING, ["w2"], "w1")).toEqual(["w1", "w2"]);
    expect(tapped(READING, ["w1", "w2"], "w0")).toEqual(["w0", "w1", "w2"]);
  });

  it("starts again for a word that is not a neighbour, and lets go of the only word tapped twice", () => {
    expect(tapped(READING, ["w0"], "w2")).toEqual(["w2"]);
    expect(tapped(READING, ["w2"], "w2")).toEqual([]);
  });

  it("does not extend across a sentence boundary", () => {
    expect(tapped(READING, ["w2"], "w4")).toEqual(["w4"]);
  });

  it("drags across every word between, in reading order, skipping punctuation", () => {
    expect(span(READING, "w4", "w1")).toEqual(["w1", "w2", "w4"]);
  });
});

describe("the sentence and what to send", () => {
  it("is the sentence of the first word selected", () => {
    expect(sentenceOf(READING, ["w1", "w2"])?.id).toBe("s0");
    expect(sentenceOf(READING, [])).toBeNull();
  });

  it("points at the selection inside the sentence's own text", () => {
    const sentence = sentenceOf(READING, ["w1"])!;
    const at = selectionIn(READING, sentence, ["w1", "w2"])!;
    expect(sentence.text.slice(at.start, at.end)).toBe("palabra dicha");
    expect(selectedText(READING, ["w1", "w2"])).toBe("palabra dicha");
  });
});

describe("what is drawn and kept", () => {
  it("outlines every printed piece of a selected word", () => {
    expect(wordOutlines(READING, ["w1"])).toHaveLength(2);
  });

  it("bands a sentence one line at a time, a hyphen's second half on the next line", () => {
    const bands = sentenceOutlines(READING, READING.sentences[0])
      .map((band) => band.map(([x, y]) => [Math.round(x * 100) / 100, Math.round(y * 100) / 100]));
    expect(bands).toEqual([
      [[0.1, 0.1], [0.35, 0.1], [0.35, 0.14], [0.1, 0.14]],
      [[0.1, 0.2], [0.36, 0.2], [0.36, 0.24], [0.1, 0.24]]
    ]);
  });

  it("keeps the region rounded and inside the photo", () => {
    const region = photoRegionFor(READING, ["w0"], READING.sentences[0]);
    expect(region.words).toEqual([[[0.1, 0.1], [0.2, 0.1], [0.2, 0.14], [0.1, 0.14]]]);
    expect(region.sentence).toHaveLength(2);
    expect(photoRegionFor(READING, ["w0"], null).sentence).toEqual([]);
  });
});

describe("keeping the square that was on screen", () => {
  it("moves a region onto the crop, clamps what straddles its edge and drops what is outside", () => {
    const region = {
      words: [[[0.1, 0.5], [0.2, 0.5], [0.2, 0.55], [0.1, 0.55]]] as [number, number][][],
      sentence: [
        [[0.1, 0.3], [0.9, 0.3], [0.9, 0.34], [0.1, 0.34]],
        [[0.1, 0.38], [0.9, 0.38], [0.9, 0.42], [0.1, 0.42]]
      ] as [number, number][][]
    };
    const cropped = cropRegion(region, 0.4, 0.25);
    expect(cropped.words).toEqual([[[0.1, 0.4], [0.2, 0.4], [0.2, 0.6], [0.1, 0.6]]]);
    expect(cropped.sentence).toEqual([[[0.1, 0], [0.9, 0], [0.9, 0.08], [0.1, 0.08]]]);
  });
});

