/**
 * Pressing a clip, and what happens when the corpus is not there.
 *
 * The player itself is the retrieval package's and is tested there; what is stubbed is the module
 * boundary, so this asserts Acervo's half — that the current clip is asked for by `clipRef`, that
 * an unreachable corpus still shows a real citation, and that a segment the corpus no longer holds
 * is not presented as a failure.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Example } from "./domain";
import { testGraph } from "./testGraph";

const clipFor = vi.fn();
const translationFor = vi.fn(async (..._args: unknown[]) => null as unknown);

vi.mock("./clips", async () => {
  const actual = await vi.importActual<typeof import("./clips")>("./clips");
  return {
    ...actual,
    clipFor: (...args: unknown[]) => clipFor(...args),
    translationFor: (...args: unknown[]) => translationFor(...args)
  };
});

/* Never loaded for real: it carries the YouTube iframe API, which jsdom has no use for.

   The stub reports the translation props as well as the segment, because the player renders one
   grey sentence for every way target text can fail to arrive — so a stub that showed only the
   segment id let a translation that never worked look exactly like one that did. */
vi.mock("@spoken-usage-retrieval/react/player", () => ({
  SpeechClipPlayer: ({ clip, targetText, translationStatus, onTranslationRetry }: {
    clip: { segment_id: string };
    targetText?: string | null;
    translationStatus?: string;
    onTranslationRetry?: (language: string) => void;
  }) => <div data-testid="player">
    playing {clip.segment_id}
    <span data-testid="status">{translationStatus}</span>
    <span data-testid="target">{targetText ?? ""}</span>
    <button onClick={() => onTranslationRetry?.("en")}>retry</button>
  </div>
}));
vi.mock("@spoken-usage-retrieval/react/styles.css", () => ({}));

const { ClipDialog } = await import("./ClipDialog");
const { storedClipOf } = await import("./clips");

const clipExample = (): Example =>
  testGraph().examples.find((example) => example.origin === "subtitle")!;

afterEach(() => { vi.clearAllMocks(); });

describe("opening a clip", () => {
  it("asks the corpus for the current clip by the segment the record names", async () => {
    const stored = storedClipOf(clipExample())!;
    clipFor.mockResolvedValue({ clip: null, stored, unreachable: false });
    render(<ClipDialog stored={stored} glossLang="en" headword="picar" onClose={() => undefined} />);

    await waitFor(() => expect(clipFor).toHaveBeenCalled());
    expect(clipFor.mock.calls[0][0].clipRef).toBe("seg_7c3d18e5b04a92f6de27");
  });

  it("hands the player what the corpus returned, not what the record stored", async () => {
    // The corpus is the authority on where a passage starts and ends and may have re-cut it since.
    const stored = storedClipOf(clipExample())!;
    clipFor.mockResolvedValue({
      clip: { segment_id: "seg_7c3d18e5b04a92f6de27", source_language: "es" },
      stored, unreachable: false
    });
    render(<ClipDialog stored={stored} glossLang="en" headword="picar" onClose={() => undefined} />);
    await waitFor(() => expect(screen.getByTestId("player").textContent)
      .toContain("seg_7c3d18e5b04a92f6de27"));
  });

  it("still offers the sentence and a direct link with the corpus unreachable", async () => {
    const stored = storedClipOf(clipExample())!;
    clipFor.mockResolvedValue({ clip: null, stored, unreachable: true });
    render(<ClipDialog stored={stored} glossLang="en" headword="picar" onClose={() => undefined} />);

    await waitFor(() => expect(screen.getByText(/could not be reached/)).toBeTruthy());
    expect(screen.getByText("Pica la cebolla bien fina.")).toBeTruthy();
    const link = screen.getByRole("link") as HTMLAnchorElement;
    expect(link.href).toContain("t=461");
  });

  it("says a segment is gone rather than calling it a failure", async () => {
    const stored = storedClipOf(clipExample())!;
    clipFor.mockResolvedValue({ clip: null, stored, unreachable: false });
    render(<ClipDialog stored={stored} glossLang="en" headword="picar" onClose={() => undefined} />);
    await waitFor(() => expect(screen.getByText(/no longer in the corpus/)).toBeTruthy());
  });

  it("gives the player the target text the corpus produced", async () => {
    const stored = storedClipOf(clipExample())!;
    clipFor.mockResolvedValue({
      clip: { segment_id: "seg_7c3d18e5b04a92f6de27", source_language: "es" },
      stored, unreachable: false
    });
    translationFor.mockResolvedValue({
      job_id: "job-1", status: "complete",
      result: { target_text: "Chop the onion very fine.", target_language: "en",
                provenance: "llm", alignment_status: "complete", alignment_groups: [],
                alignment_graph: null }
    });
    render(<ClipDialog stored={stored} glossLang="en" headword="picar" onClose={() => undefined} />);

    await waitFor(() => expect(screen.getByTestId("target").textContent)
      .toBe("Chop the onion very fine."));
    expect(screen.getByTestId("status").textContent).toBe("complete");
  });

  it("offers a retry that re-asks, because the corpus remembers a refusal", async () => {
    /* The service caches a stage that produced unusable output and answers from that memory ever
       after, `cache_hit` and all. So a clip attempted under a broken configuration keeps failing
       once the configuration is fixed, and only `retryFailed` re-asks. Without this the reader has
       no way out of a cached failure at all. */
    const stored = storedClipOf(clipExample())!;
    clipFor.mockResolvedValue({
      clip: { segment_id: "seg_7c3d18e5b04a92f6de27", source_language: "es" },
      stored, unreachable: false
    });
    translationFor.mockResolvedValue({
      job_id: "job-1", status: "failed", result: null,
      error: { code: "invalid_output", message: "…", retryable: true }
    });
    render(<ClipDialog stored={stored} glossLang="en" headword="picar" onClose={() => undefined} />);

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("failed"));
    // The first ask does not force a re-run: a cached *success* is the whole point of the cache.
    expect(translationFor.mock.calls[0][3]).toBeUndefined();

    fireEvent.click(screen.getByText("retry"));
    await waitFor(() => expect(translationFor).toHaveBeenCalledTimes(2));
    expect(translationFor.mock.calls[1][1]).toBe("en");
    expect(translationFor.mock.calls[1][3]).toBe(true);
  });

  it("closes on Escape", async () => {
    const onClose = vi.fn();
    const stored = storedClipOf(clipExample())!;
    clipFor.mockResolvedValue({ clip: null, stored, unreachable: false });
    render(<ClipDialog stored={stored} glossLang="en" headword="picar" onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});

describe("what the record alone can do", () => {
  it("is a playable citation without a segment id at all", () => {
    // An imported or hand-written clip example names a video and a start but no corpus segment.
    const stored = storedClipOf({ ...clipExample(), clipRef: null })!;
    expect(stored.videoRef).toBeTruthy();
    expect(stored.videoStart).toBe(461);
  });

  it("is nothing at all without a video reference, which is what every clip field hangs on", () => {
    expect(storedClipOf({ ...clipExample(), videoRef: null })).toBeNull();
  });
});
