/**
 * The pinned retrieval package is installable, typed, and the version Acervo says it is.
 *
 * This exists so a version bump that breaks the contract fails here, beside the pin, rather than
 * in the clip dialog that imports the player (`docs/features/spoken-clips.md` §2.1). It is
 * deliberately a *type* and *identity* check rather than a render: the component's own behaviour is
 * that repository's to test.
 */

import { describe, expect, it } from "vitest";
import { createSpeechRetrievalClient, SpeechClipPlayer } from "@spoken-usage-retrieval/react";
import type { SearchResult, SpeechClip } from "@spoken-usage-retrieval/react";
import pin from "../../deploy/acervo/speech/pin.json";
import manifest from "../package.json";

describe("the pinned spoken-usage-retrieval package", () => {
  it("is installed from the artifact the pin names, so a bump cannot be half-applied", () => {
    // The filename carries the version on purpose: npm caches `file:` dependencies by path, so a
    // stable name could resolve to a stale extraction after a bump. Asserting the dependency points
    // at the pinned artifact is therefore the same as asserting the installed version.
    const dependency = manifest.dependencies["@spoken-usage-retrieval/react"];

    expect(dependency).toContain(pin.artifacts.react.file);
    expect(pin.artifacts.react.file).toContain(pin.version);
    expect(pin.artifacts.wheel.file).toContain(pin.version);
  });

  it("names a tag that matches its version, so the fetch script asks for the right release", () => {
    expect(pin.tag).toBe(`v${pin.version}`);
  });

  it("exports the player and the typed client Acervo will use", () => {
    expect(typeof SpeechClipPlayer).toBe("function");
    expect(typeof createSpeechRetrievalClient).toBe("function");
  });

  it("builds a client against a caller-supplied base URL without touching the network", () => {
    // Acervo points this at its own authenticated proxy rather than at the corpus, so the base URL
    // and the fetch implementation both have to be the caller's. If that ever stops being true,
    // §2.9 of the plan stops being implementable.
    const client = createSpeechRetrievalClient({
      baseUrl: "https://acervo.example.com/api/acervo/v1/speech",
      fetch: () => Promise.reject(new Error("the network is not touched by construction")),
    });

    expect(typeof client.search).toBe("function");
    expect(typeof client.clip).toBe("function");
  });

  it("types a clip and a search result with the fields a stored example needs", () => {
    // A compile-time assertion: `npm run build` type-checks this file, so a contract change that
    // removed any of these fails the build rather than surfacing when step 2 writes the schema.
    const fields = (result: SearchResult): [string, string, number, number, string] => [
      result.segment_id,
      result.sentence,
      result.clip_start,
      result.clip_end,
      result.video.channel,
    ];
    const clipFields = (clip: SpeechClip): [string, number] => [clip.segment_id, clip.clip_start];

    expect(fields).toBeTypeOf("function");
    expect(clipFields).toBeTypeOf("function");
  });
});
