/**
 * The reveal rule, in the DOM.
 *
 * `selectors.test.ts` pins the arithmetic; this pins that the component obeys it — that a
 * translation which has not been spoken is a bar and not text, that winding back puts it away
 * again, and that the mark following the utterances is the only thing that moves. Those are the
 * three ways this screen could quietly stop being an exercise and become a caption.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Loop, LoopItem } from "./domain";
import * as playerModule from "./loops";
import LoopPlayer from "./LoopPlayer";

const loop: Loop = {
  id: "loop00000000001", language: "es", styleId: "gentle-game", seed: 104740,
  engineVersion: "1.4.0", bedFingerprint: "f35282aaf3c40245", pattern: "retrieval",
  audioRef: "loops/es/loop00000000001-6ad2f019.mp3", audioMime: "audio/mpeg",
  durationSeconds: 90, position: 1,
  ownerId: "owner0000000001", deleted: false, createdAt: "2026-09-16T00:00:00.000Z",
  editedAt: "2026-09-16T00:00:00.000Z", editedBy: "device000000001", revision: 1
};

const word = (over: Partial<LoopItem>): LoopItem => ({
  id: "loopitem0000001", loopId: loop.id, lexemeId: "lexeme000000001", position: 0,
  sourceText: "asco", targetText: "disgust", emotion: "repulsed",
  startSeconds: 8.82, sourceRevealSeconds: 8.82, targetRevealSeconds: 17.65, endSeconds: 44.12,
  repeats: 3, repeatSeconds: 4.41,
  ownerId: "owner0000000001", deleted: false, createdAt: "2026-09-16T00:00:00.000Z",
  editedAt: "2026-09-16T00:00:00.000Z", editedBy: "device000000001", revision: 1, ...over
});

const items = [
  word({}),
  word({ id: "loopitem0000002", position: 1, sourceText: "la balsa", targetText: "raft",
         startSeconds: 44.12, sourceRevealSeconds: 44.12, targetRevealSeconds: 52.94, endSeconds: 79.41 })
];

function at(seconds: number) {
  vi.spyOn(playerModule, "usePlayback").mockReturnValue({
    loopId: loop.id, at: seconds, duration: 90, playing: true, loading: false, failed: null
  });
  return render(<LoopPlayer loop={loop} items={items} />);
}

afterEach(() => vi.restoreAllMocks());

describe("playing a loop", () => {
  it("does not draw a translation that has not been spoken", () => {
    const { container } = at(12);
    expect(screen.getByText("asco")).toBeInTheDocument();
    // The answer is a bar of a fixed width, not text: present so the line does not jump, and the
    // same width for every word so it says nothing about the answer.
    expect(screen.queryByText("disgust")).not.toBeInTheDocument();
    expect(container.querySelector(".lyric-row.now .lyric-held")).toBeInTheDocument();
  });

  it("draws it once it has been", () => {
    at(18);
    expect(screen.getByText("disgust")).toBeInTheDocument();
  });

  it("withholds it again when the line is wound back", () => {
    at(18).unmount();
    at(12);
    expect(screen.queryByText("disgust")).not.toBeInTheDocument();
  });

  it("marks whichever of the pair was spoken most recently, and nothing else", () => {
    const early = at(12).container;
    expect(early.querySelector(".lyric-source.saying")?.textContent).toBe("asco");
    expect(early.querySelector(".lyric-target.saying")).toBeNull();

    const later = at(27).container;
    expect(later.querySelector(".lyric-source.saying")).toBeNull();
    expect(later.querySelector(".lyric-target.saying")).toBeInTheDocument();
  });

  it("keeps every word on screen and marks only the one being taught", () => {
    const { container } = at(50);
    expect(screen.getByText("asco")).toBeInTheDocument();
    expect(screen.getByText("la balsa")).toBeInTheDocument();
    expect(container.querySelectorAll(".lyric-row.now")).toHaveLength(1);
    expect(container.querySelector(".lyric-row.now .lyric-source")?.textContent).toBe("la balsa");
    // A word already heard keeps its answer; one still to come does not have it yet.
    expect(screen.getByText("disgust")).toBeInTheDocument();
    expect(screen.queryByText("raft")).not.toBeInTheDocument();
  });

  it("puts a tick on the line for every word", () => {
    const { container } = at(0);
    expect(container.querySelectorAll(".seek-tick")).toHaveLength(items.length);
  });

  it("seeks to a word when its line is pressed", () => {
    const play = vi.spyOn(playerModule, "play").mockResolvedValue(undefined);
    at(12);
    fireEvent.click(screen.getByText("la balsa"));
    expect(play).toHaveBeenCalledWith(loop, items, { at: 44.12 });
  });
});
