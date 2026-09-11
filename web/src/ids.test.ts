import { describe, expect, it } from "vitest";
import { clipExampleId, imagePromptId, newId } from "./ids";

/**
 * One half of the check that the two derivations agree.
 *
 * The other is `tests/unit/jobs/test_sense_images.py` against `src/acervo/images/ids.py`, and
 * `tests/unit/clips/test_ids.py` against `src/acervo/clips/ids.py`. The vectors below were produced
 * by those functions, so a change to either side that does not match the other fails here — which
 * matters because the derivation is what makes two writers converge on one row without
 * coordinating, and disagreement would show up as a duplicate record rather than as an error.
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

describe("a clip example's id", () => {
  it("matches what the server derives, byte for byte", () => {
    expect(clipExampleId("sensepicaritch0", "seg_1f4c9a2b7e6d5c3a0b91")).toBe("6b34r20hqwnhbwj");
    expect(clipExampleId("oj3y4cakuelbgrd", "seg_0000000000000000000")).toBe("g8wb7iyop0teah3");
    // Empty inputs exercise the padding, which is where a hand-written SHA-256 goes wrong.
    expect(clipExampleId("sensepicaritch0", "")).toBe("qnfybb75s2smt0o");
    expect(clipExampleId("", "")).toBe("39upl9iwx14c6jl");
  });

  it("is keyed on the pair, so a sense may hold clips from several segments", () => {
    const first = clipExampleId("sensepicaritch0", "seg_1f4c9a2b7e6d5c3a0b91");
    expect(first).toMatch(/^[a-z0-9]{15}$/);
    expect(first).not.toBe(clipExampleId("sensepicaritch0", "seg_ffffffffffffffffffff"));
    expect(first).not.toBe(clipExampleId("sensepicarchop0", "seg_1f4c9a2b7e6d5c3a0b91"));
  });

  it("cannot collide with the picture id of the same sense", () => {
    expect(clipExampleId("sensepicaritch0", "")).not.toBe(imagePromptId("sensepicaritch0"));
  });
});
