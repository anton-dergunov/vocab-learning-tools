/**
 * Hearing a story: the third place in Acervo where anything is heard, after `pronunciation.ts` (a word
 * or a sentence) and `loops.ts` (a track), and modelled on the second.
 *
 * **A part is a queue of passages, and nothing is ever seeked.** Each passage is its own file, so
 * playing one is playing it from its first sample, and playing from a passage to the end of the part
 * is playing that file and then the ones after it. The alternative was tried and does not work: join
 * the passages, remember where each begins, and set `currentTime`. A browser seeks a compressed
 * stream to a page boundary — one second, in the Ogg the server writes — so a passage started a word
 * or two late, or a word or two into the sentence before, unpredictably; and the element reports the
 * position that was *asked for* rather than the one it gave, so nothing can detect it or correct it.
 * A file that begins where the passage begins cannot be wrong.
 *
 * **Pause is pause, and leaving is stop.** Pressing play on a part that is playing pauses it, and
 * pressing it again carries on from where it was. There is no scrubber — a story is read a part at a
 * time, and swiping to another part and back is the way to begin again, because leaving a part
 * *stops* it and drops its position. `stopPart` is what the reader calls when a page stops being the
 * one on screen.
 *
 * **A passage is a place to start.** Touching one when nothing of this part is playing plays that
 * passage alone; touching one while the part is playing goes there and carries on to the end. The
 * first answers "what was that sentence?", the second "go back to there".
 *
 * **On demand is the same route the job takes.** A part with no passages asks the server for them,
 * which is one call to the same function `story.audio` runs, and plays when they arrive. The element
 * is started on silence in the press itself, before that wait, for `pronunciation.ts`'s reason: iOS
 * lets an element play only from inside the gesture that asked.
 *
 * One sound at a time: this stops `pronunciation.ts`, pauses every other registered player before it
 * plays, and registers its own pause with them. The dependency runs one way, as it does for loops.
 */

import { useSyncExternalStore } from "react";
import { AcervoApiError, backendSession } from "./api";
import type { AudioSegment, StoryPart } from "./domain";
import { clipBlob, registerPlayer, silencePlayers, stop as stopSpeech } from "./pronunciation";
import { repository } from "./repository";
import { syncEngine } from "./sync";

export type StoryAudioStatus = "idle" | "busy" | "playing" | "paused";

export interface StoryPlayback {
  /** The part being fetched, recorded, heard or paused. Kept while `failed`, so its row can say why. */
  partId: string | null;
  status: StoryAudioStatus;
  /** Index of the passage that is sounding, or null when nothing of this part is. */
  segment: number | null;
  failed: string | null;
}

const EMPTY: StoryPlayback = { partId: null, status: "idle", segment: null, failed: null };

let state: StoryPlayback = EMPTY;
const listeners = new Set<() => void>();

function update(partial: Partial<StoryPlayback>): void {
  state = { ...state, ...partial };
  listeners.forEach((listener) => listener());
}

const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };

export const storyPlayback = (): StoryPlayback => state;

export function useStoryAudio(): StoryPlayback {
  return useSyncExternalStore(subscribe, storyPlayback);
}

/* ── the element ─────────────────────────────────────────────────────── */

let element: HTMLAudioElement | null = null;
/** The object URL the element is holding, revoked when it is let go. */
let held: string | null = null;
/** Bumped by every press that starts something, so an answer that arrives late knows it is stale. */
let run = 0;

/** What is queued: the passages, which one is sounding, which is the last, and their bytes. */
let queue: { passages: AudioSegment[]; at: number; last: number; blobs: Map<string, Blob> } | null = null;

function audio(): HTMLAudioElement {
  if (element) return element;
  element = new Audio();
  element.preload = "auto";
  // The passage's own end only: the silence `prime` starts ends too, long before one has arrived.
  element.addEventListener("ended", () => { if (held && element?.src === held) void advance(); });
  element.addEventListener("pause", () => {
    if (state.status === "playing" && held && element?.src === held) update({ status: "paused" });
  });
  element.addEventListener("play", () => {
    if (held && element?.src === held) update({ status: "playing" });
  });
  return element;
}

/* A few milliseconds of silence, for the reason `pronunciation.ts` and `loops.ts` give. */
const SILENCE = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";

function prime(): void {
  const player = audio();
  if (!player.paused) return;
  try { player.src = SILENCE; void player.play()?.catch(() => undefined); }
  catch { /* jsdom, or a browser with no audio at all */ }
}

/** Let go of the element: nothing is playing, nothing is held, and the queue is forgotten. */
function release(): void {
  if (element) {
    try { element.pause(); } catch { /* nothing to stop */ }
    element.removeAttribute("src");
  }
  if (held) { URL.revokeObjectURL(held); held = null; }
  queue = null;
}

/** Play the passage the queue is on. */
async function sound(): Promise<void> {
  if (!queue) return;
  const passage = queue.passages[queue.at];
  const blob = queue.blobs.get(passage.audioRef);
  if (!blob) { finish(); return; }
  const player = audio();
  if (held) URL.revokeObjectURL(held);
  held = URL.createObjectURL(blob);
  player.src = held;
  update({ status: "playing", segment: queue.at });
  await player.play();
}

/** This passage ended: on to the next, unless it was the last that was asked for. */
async function advance(): Promise<void> {
  if (!queue) return;
  if (queue.at >= queue.last) { finish(); return; }
  queue.at += 1;
  try {
    await sound();
  } catch (error) {
    console.warn("Acervo: a story passage could not be played", error);
    finish();
  }
}

function finish(): void {
  run += 1;
  release();
  update(EMPTY);
}

/* ── pressing ────────────────────────────────────────────────────────── */

function failure(error: unknown): string {
  if (error instanceof AcervoApiError && error.code === "offline") {
    return "Reading a story aloud needs the server, and it cannot be reached.";
  }
  if (error instanceof DOMException && error.name === "NotAllowedError") {
    return "This device would not start the audio. Press play again.";
  }
  return error instanceof Error ? error.message : "That part could not be read aloud.";
}

/**
 * Play `part` from passage `from`, stopping after `last`.
 *
 * Every passage that will be played is fetched before the first one sounds. They are a few tens of
 * kilobytes each and already on the device in the ordinary case, and holding them is what makes the
 * swap from one to the next an assignment rather than a fetch — which keeps the seam between two
 * sentences as short as the silence a speaker leaves anyway.
 */
async function start(part: StoryPart, from: number, last: number): Promise<void> {
  const mine = ++run;
  release();
  stopSpeech();
  silencePlayers(pause);
  // Before any await, so the browser still counts this as the gesture that asked.
  prime();
  update({ partId: part.id, status: "busy", segment: null, failed: null });
  try {
    let passages = part.audioSegments;
    if (!passages.length) {
      const row = await backendSession.recordStoryPart(part.storyId, part.id, repository.snapshot().deviceId);
      if (mine !== run) return;
      // The row reaches the replica the way every server-written row does; it plays meanwhile.
      void syncEngine.syncNow();
      passages = row.audioSegments;
      from = 0;
      last = passages.length - 1;
    }
    if (!passages.length) throw new Error("That part has no recording.");
    const stop = Math.min(last, passages.length - 1);
    const blobs = new Map<string, Blob>();
    for (const passage of passages.slice(from, stop + 1)) {
      blobs.set(passage.audioRef, await clipBlob(passage.audioRef));
      if (mine !== run) return;
    }
    queue = { passages, at: from, last: stop, blobs };
    await sound();
  } catch (error) {
    if (mine !== run) return;
    console.warn("Acervo: a story part could not be played", { part: part.id, error });
    release();
    update({ partId: part.id, status: "idle", segment: null, failed: failure(error) });
  }
}

/** Play, pause or carry on, for the button on a part. Pressing it while it is being made stops that. */
export function toggle(part: StoryPart): void {
  if (state.partId === part.id) {
    if (state.status === "playing") { pause(); return; }
    if (state.status === "paused") { resume(); return; }
    if (state.status === "busy") { stop(); return; }
  }
  void start(part, 0, Math.max(part.audioSegments.length - 1, 0));
}

/**
 * A touch on a passage. While this part is sounding it goes there and carries on to the end;
 * otherwise it plays that passage alone.
 */
export function playSegment(part: StoryPart, index: number): void {
  if (!part.audioSegments[index]) return;
  const sounding = state.partId === part.id && (state.status === "playing" || state.status === "paused");
  void start(part, index, sounding ? part.audioSegments.length - 1 : index);
}

export function pause(): void {
  if (state.status !== "playing") return;
  try { element?.pause(); } catch { /* nothing to stop */ }
  update({ status: "paused" });
}

function resume(): void {
  void audio().play().catch((error: unknown) => {
    release();
    update({ status: "idle", segment: null, failed: failure(error) });
  });
}

/** Stop and forget the position. */
export function stop(): void {
  run += 1;
  release();
  update(EMPTY);
}

/**
 * Stop, but only if it is this part that is being heard — what a page does when it stops being the
 * one on screen, without silencing a part that is somewhere else.
 */
export function stopPart(partId: string): void {
  if (state.partId === partId) stop();
}

export function replaceForTests(): void {
  run += 1;
  release();
  element = null;
  state = EMPTY;
}

registerPlayer(pause);
