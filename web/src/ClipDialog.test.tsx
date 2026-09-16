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
  SpeechClipPlayer: ({ clip, targetText, translationStatus, match, onTranslationRetry }: {
    clip: { segment_id: string };
    targetText?: string | null;
    translationStatus?: string;
    match?: { text: string; char_start: number; char_end: number };
    onTranslationRetry?: (language: string) => void;
  }) => <div data-testid="player">
    playing {clip.segment_id}
    <span data-testid="status">{translationStatus}</span>
    <span data-testid="target">{targetText ?? ""}</span>
    <span data-testid="match">{match ? `${match.text}@${match.char_start}-${match.char_end}` : ""}</span>
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

  it("shows the article's own translation at once, and asks only for its alignment", async () => {
    /* The clip-selection call already wrote a translation into the graph. Asking the corpus to
       translate the passage again produced a second, differently worded sentence for the same clip
       — two provider calls to end up disagreeing with the page behind the dialog. */
    const stored = storedClipOf(clipExample())!;
    clipFor.mockResolvedValue({
      clip: { segment_id: "seg_7c3d18e5b04a92f6de27", source_language: "es" },
      stored, unreachable: false
    });
    render(<ClipDialog stored={stored} glossLang="en" headword="picar" onClose={() => undefined} />);

    // On screen before the corpus has answered anything, and it is the article's wording.
    await waitFor(() => expect(screen.getByTestId("target").textContent).toBe(stored.translation));
    expect(screen.getByTestId("status").textContent).toBe("complete");
    // And what was asked for is the alignment *of that sentence*, not a new one.
    await waitFor(() => expect(translationFor).toHaveBeenCalled());
    expect(translationFor.mock.calls[0][4]).toBe(stored.translation);
  });

  it("marks the headword in the source, which the corpus cannot do for it", async () => {
    /* A clip fetched by id carries no match span and structurally cannot — a segment id does not
       know which word was searched for. The stored example names the form, so Acervo supplies it;
       without this the translation was marked and the sentence it translates was not. */
    const stored = storedClipOf(clipExample())!;
    clipFor.mockResolvedValue({
      clip: { segment_id: "seg_7c3d18e5b04a92f6de27", source_language: "es" },
      stored, unreachable: false
    });
    render(<ClipDialog stored={stored} glossLang="en" headword="picar" onClose={() => undefined} />);

    await waitFor(() => expect(screen.getByTestId("player")).toBeTruthy());
    const marked = screen.getByTestId("match").textContent!;
    expect(marked).toContain(stored.matchedForm!);
    const [, span] = marked.split("@");
    const [start, end] = span.split("-").map(Number);
    expect(Array.from(stored.text).slice(start, end).join("")).toBe(stored.matchedForm);
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
    expect(translationFor.mock.calls[0][3]).toBe(false);

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

/* The sentence is the article's own and is on screen from the first frame, so what this line
   reports is the *alignment* — whether the corpus managed to link the words. A failure there is a
   nicety lost, not content missing, and it must not claim a translation is absent while one is
   plainly visible above it. */
describe("where the word linking has got to", () => {
  const playing = () => {
    const stored = storedClipOf(clipExample())!;
    clipFor.mockResolvedValue({
      clip: { segment_id: "seg_7c3d18e5b04a92f6de27", source_language: "es" },
      stored, unreachable: false
    });
    return stored;
  };

  it("says the corpus could not be reached, and offers a way to try again", async () => {
    const stored = playing();
    translationFor.mockResolvedValue(null);
    render(<ClipDialog stored={stored} glossLang="en" headword="picar" onClose={() => undefined} />);

    expect(await screen.findByText(/words are not linked/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    // And the sentence itself is still there: it never depended on the corpus. `find`, not `get`:
    // the player is lazy and commits after the line above it.
    expect((await screen.findByTestId("target")).textContent).toBe(stored.translation);
  });

  it("says nothing at all while it is still asking, and takes up no room saying it", async () => {
    // The linking runs quietly. A status line here had a rule above it and a line's worth of
    // height, so it pushed everything down while it showed and pulled it back up when it went —
    // and the reader, mid-sentence, saw the text move rather than a message go away.
    const stored = playing();
    translationFor.mockReturnValue(new Promise(() => { /* never settles */ }));
    render(<ClipDialog stored={stored} glossLang="en" headword="picar" onClose={() => undefined} />);

    expect((await screen.findByTestId("target")).textContent).toBe(stored.translation);
    expect(document.querySelector(".clip-translation")).toBeNull();
    expect(screen.queryByText(/Linking/)).not.toBeInTheDocument();
  });

  it("says nothing of its own once the words are linked", async () => {
    const stored = playing();
    translationFor.mockResolvedValue({
      job_id: "j1", status: "complete",
      result: {
        target_text: stored.translation, target_language: "en",
        alignment_graph: { source_tokens: [], target_tokens: [], edges: [] }
      }
    });
    render(<ClipDialog stored={stored} glossLang="en" headword="picar" onClose={() => undefined} />);

    await waitFor(() => expect(screen.queryByText(/not linked/)).not.toBeInTheDocument());
    expect(screen.queryByText("Linking the words…")).not.toBeInTheDocument();
  });

  it("says so when the clip was saved with no translation, and asks for nothing", async () => {
    const stored = {
      ...playing(), clipRef: "seg_untranslated", translation: null, translationLang: null
    };
    clipFor.mockResolvedValue({
      clip: { segment_id: "seg_untranslated", source_language: "es" }, stored, unreachable: false
    });
    render(<ClipDialog stored={stored} glossLang="en" headword="picar" onClose={() => undefined} />);

    expect(await screen.findByText(/saved without a translation/)).toBeInTheDocument();
    // Nothing to align, so the corpus is never asked about *this* clip. Named rather than counted:
    // a lazy player mounted by an earlier test can commit after `clearAllMocks` and its effect then
    // lands in this test's tally, where a bare count would be measuring the wrong component.
    expect(translationFor.mock.calls.map((call) => call[0])).not.toContain("seg_untranslated");
  });
});
