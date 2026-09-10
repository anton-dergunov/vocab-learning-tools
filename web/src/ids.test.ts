import { describe, expect, it } from "vitest";
import { imagePromptId, newId } from "./ids";

/**
 * One half of the check that the two derivations agree.
 *
 * The other is `tests/unit/jobs/test_sense_images.py`, against
 * `src/acervo/images/ids.py`. The vectors below were produced by that function, so a change to
 * either side that does not match the other fails here — which matters because the derivation is
 * what makes two engines converge on one row without coordinating, and disagreement would show up
 * as duplicate pictures rather than as an error.
 */
describe("an image prompt's id", () => {
  it("matches what the server derives, byte for byte", () => {
    expect(imagePromptId("sensepicaritch0")).toBe("otxot3jm55or06a");
    expect(imagePromptId("oj3y4cakuelbgrd")).toBe("0088hcytqci2gl0");
    // Short and empty inputs exercise the padding, which is where a hand-written SHA-256 goes wrong.
    expect(imagePromptId("a")).toBe("rtggsgprao8u2o3");
    expect(imagePromptId("")).toBe("5el2yfarsw7agle");
  });

  it("is a valid Acervo id", () => {
    expect(imagePromptId("sensepicaritch0")).toMatch(/^[a-z0-9]{15}$/);
  });

  it("is the same every time, which is the whole point", () => {
    expect(imagePromptId("sensepicaritch0")).toBe(imagePromptId("sensepicaritch0"));
    expect(imagePromptId("sensepicaritch0")).not.toBe(imagePromptId("sensepicarchop0"));
  });

  it("is not what `newId` produces, which is random and stays that way", () => {
    expect(newId()).not.toBe(newId());
    expect(newId()).toMatch(/^[a-z0-9]{15}$/);
  });
});
