/* The one property everything else rests on: the parts reassemble.
 *
 * `same` + `del` must rebuild the string that was there, and `same` + `ins` the string that replaced
 * it. If that ever stops holding, the article shows a sentence nobody wrote — which is worse than
 * showing no diff at all, and is why it is asserted on every case rather than once. */

import { describe, expect, it } from "vitest";
import { lcs, similarity, tokenise, TOKEN_CAP, wordDiff, words } from "./wordDiff";

const rebuilt = (parts: { at: string; text: string }[], side: "del" | "ins") =>
  parts.filter((part) => part.at === "same" || part.at === side)
    .map((part) => part.text).join("");

/** Every diff in this file is checked against its own inputs. */
function expectRebuilds(before: string, after: string) {
  const parts = wordDiff(before, after)!;
  expect(parts).not.toBeNull();
  expect(rebuilt(parts, "del")).toBe(before);
  expect(rebuilt(parts, "ins")).toBe(after);
  return parts;
}

describe("tokenising", () => {
  it.each([
    ["a plain sentence", "Me pica la nariz."],
    ["an em-dash note", "Used to describe something — often stronger than 'sorprendente'."],
    ["guillemets", "Compared to «increíble», it emphasizes being stunned."],
    ["an emoji", "Common around Carnival 🎭 and at parties."],
    ["decomposed accents", "asómbroso él"],
    ["composed accents", "asómbroso él"],
    ["Chinese, which has no spaces", "他把衣服穿上了。"],
    ["Japanese", "彼は医者に変装した。"],
    ["one word", "picar"],
    ["whitespace only", "   "],
    ["a lone dash", "—"],
    ["the empty string", ""]
  ])("rebuilds %s exactly", (_name, text) => {
    expect(tokenise(text).map((token) => token.text).join("")).toBe(text);
  });

  it("splits Chinese into words rather than one run", () => {
    // The whole reason `Intl.Segmenter` is used instead of a `\p{L}+` regex: without it the word
    // diff would say "everything replaced" for every Chinese entry.
    expect(words("他把衣服穿上了。").length).toBeGreaterThan(3);
  });

  it("keeps punctuation out of the word but inside the text", () => {
    const tokens = tokenise("duele, mucho.");
    expect(tokens.map((token) => token.word)).toEqual(["duele", "mucho"]);
    expect(tokens.map((token) => token.text)).toEqual(["duele, ", "mucho."]);
  });
});

describe("the longest common subsequence", () => {
  it("finds what stayed put through a rotation", () => {
    // This is the reorder case: one sense moved to the front, so only that one moved.
    const kept = lcs(["A", "B", "C"], ["C", "A", "B"], (one, other) => one === other);
    expect(kept.map((pair) => pair.a)).toEqual([0, 1]);
  });

  it("is empty when nothing is shared, and when a side is empty", () => {
    expect(lcs(["A"], ["B"], (one, other) => one === other)).toEqual([]);
    expect(lcs([], ["B"], (one, other) => one === other)).toEqual([]);
  });
});

describe("similarity", () => {
  it("is 1 for the same words and 0 for none shared", () => {
    expect(similarity("una balsa plana", "una balsa plana")).toBe(1);
    expect(similarity("una balsa", "zzz qqq")).toBe(0);
  });

  it("stays high when one word of several changes", () => {
    const score = similarity(
      "Used to describe something that causes great surprise or wonder",
      "Used to describe something that causes great surprise or awe"
    );
    expect(score).toBeGreaterThan(0.8);
  });

  it("is low when a note is replaced rather than reworded", () => {
    // Below the 0.5 pairing threshold, which is what keeps "removed, and here is a new one" the
    // reading for two unrelated notes.
    expect(similarity("Common around Carnival.", "Not to be confused with «el traje».")).toBeLessThan(0.5);
  });

  it("ignores punctuation, which the diff itself does not", () => {
    expect(similarity("duele mucho", "duele, mucho.")).toBe(1);
  });
});

describe("the word diff", () => {
  it("is null when the strings are identical", () => {
    expect(wordDiff("Me pica la nariz.", "Me pica la nariz.")).toBeNull();
  });

  it("marks one substitution and leaves the rest alone", () => {
    const parts = expectRebuilds(
      "La abeja me picó en el brazo y me duele un montón.",
      "La abeja me picó en el brazo y me duele muchísimo."
    );
    expect(parts.filter((part) => part.at === "del")).toHaveLength(1);
    expect(parts.filter((part) => part.at === "ins")).toHaveLength(1);
    expect(parts[0].at).toBe("same");
    expect(parts.find((part) => part.at === "del")!.text).toContain("montón");
    expect(parts.find((part) => part.at === "ins")!.text).toContain("muchísimo");
  });

  it("marks an inserted word with nothing deleted", () => {
    const parts = expectRebuilds("Producir comezón.", "Producir gran comezón.");
    expect(parts.some((part) => part.at === "del")).toBe(false);
    expect(parts.find((part) => part.at === "ins")!.text.trim()).toBe("gran");
  });

  it("merges a run of deleted words into one part", () => {
    const parts = expectRebuilds("uno dos tres cuatro cinco", "uno cinco");
    expect(parts.filter((part) => part.at === "del")).toHaveLength(1);
  });

  it("treats changed punctuation as a change", () => {
    // Comparing bare words would align these and then have to pick whose comma to print, which
    // would make the reassembly a lie. The reassembly assertion inside is the real check.
    expectRebuilds("duele mucho", "duele, mucho");
  });

  it("handles a whole-string replacement", () => {
    const parts = expectRebuilds("Rara vez.", "Muy común.");
    expect(parts.some((part) => part.at === "same")).toBe(false);
  });

  it("diffs Chinese by word", () => {
    const parts = expectRebuilds("他把衣服穿上了。", "他把大衣穿上了。");
    expect(parts.some((part) => part.at === "same")).toBe(true);
  });

  it("is deterministic, and puts a deletion before its insertion", () => {
    const once = wordDiff("uno dos tres", "uno DOS tres");
    const twice = wordDiff("uno dos tres", "uno DOS tres");
    expect(once).toEqual(twice);
    const kinds = once!.map((part) => part.at);
    expect(kinds.indexOf("del")).toBeLessThan(kinds.indexOf("ins"));
  });

  it("declines a string past the cap rather than getting slow", () => {
    const long = "palabra ".repeat(TOKEN_CAP + 10);
    expect(wordDiff(long, `${long}otra`)).toBeNull();
  });

  it("rebuilds both sides for a realistic note rewrite", () => {
    expectRebuilds(
      "Used to describe something that causes great surprise or wonder. Often stronger than 'sorprendente'.",
      "Used to describe something that causes great surprise or awe. Rather stronger than 'sorprendente'."
    );
  });
});
