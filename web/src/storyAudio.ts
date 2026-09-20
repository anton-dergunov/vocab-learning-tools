/**
 * Hearing a story: the third place in Acervo where anything is heard, after `pronunciation.ts` (a word
 * or a sentence) and `loops.ts` (a track), and modelled on the second.
 *
 * **A part is one file.** The server built it by joining one recording per passage, so it can say
 * where every passage sits in it, and this module needs nothing else to mark the passage that is
 * sounding or to start from any of them: the position is read from the element every frame, and the
 * passage is the last one that has started. Nothing here is aligned or guessed.
 *
 * **Pause is pause, and leaving is stop.** Pressing play on a part that is playing pauses it, and
 * pressing it again carries on from where it was. There is deliberately no scrubber — a story is read
 * a part at a time, and swiping to another part and back is the way to begin again, because leaving a
 * part *stops* it and drops its position. `stop(partId)` is what the reader calls when a page stops
 * being the one on screen.
 *
 * **A passage is a place to start.** Touching one when nothing of this part is playing plays that
 * passage and then stops; touching one while the part is playing moves the recording there and it
 * carries on to the end. The first answers "what was that sentence?", the second "go back to there".
 *
 * **On demand is the same route the job takes.** A part with no recording asks the server for one,
 * which is one call to the same function `story.audio` runs, and plays it when it arrives. The
 * element is started on silence in the press itself, before that wait, for `pronunciation.ts`'s
 * reason: iOS lets an element play only from inside the gesture that asked.
 *
 * One sound at a time: this stops `pronunciation.ts`, pauses every other registered player before it
 * plays, and registers its own pause with them. The dependency runs one way, as it does for loops.
 */

import { useSyncExternalStore } from "react";
import { AcervoApiError, backendSession } from "./api";
import type { StoryPart } from "./domain";
import { clipBlob, registerPlayer, silencePlayers, stop as stopSpeech } from "./pronunciation";
import { repository } from "./repository";
import { syncEngine } from "./sync";

export type StoryAudioStatus = "idle" | "busy" | "playing" | "paused";

export interface StoryPlayback {
  /** The part being fetched, recorded, heard or paused. Kept while `failed`, so its row can say why. */
  partId: string | null;
  status: StoryAudioStatus;
  /** Index of the passage that is sounding, or null when the part has none to mark. */
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
let frame = 0;
/** The object URL the element is holding, revoked when it is let go. */
let held: string | null = null;
/** The row being played — the freshest one, which may be newer than the reader's until a pull lands. */
let active: StoryPart | null = null;
/** Where to stop, for a single passage; null plays on to the end of the part. */
let stopAt: number | null = null;
/** Bumped by every press that starts something, so an answer that arrives late knows it is stale. */
let run = 0;

function audio(): HTMLAudioElement {
  if (element) return element;
  element = new Audio();
  element.preload = "auto";
  // The part's own end only: the silence `prime` starts ends too, long before the part has arrived.
  element.addEventListener("ended", () => { if (held && element?.src === held) finish(); });
  element.addEventListener("pause", () => {
    stopClock();
    if (state.status === "playing" && held && element?.src === held) update({ status: "paused" });
  });
  element.addEventListener("play", () => {
    // Only the part's own sound: the silence `prime` starts also fires `play`.
    if (held && element?.src === held) { update({ status: "playing" }); startClock(); }
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

/** The passage that is sounding at `seconds`: the last one that has started. */
function segmentAt(seconds: number): number | null {
  const segments = active?.audioSegments ?? [];
  let found: number | null = null;
  segments.forEach((one, index) => { if (seconds >= one.start) found = index; });
  return found;
}

/* `timeupdate` is about four a second, which cannot stop a single passage where it ends or move a
   mark as the words change. So the position is read every frame while playing, and not at all while
   paused. */
function startClock(): void {
  if (frame) return;
  const tick = () => {
    const player = element;
    if (!player || player.paused) { frame = 0; return; }
    const at = player.currentTime;
    if (stopAt !== null && at >= stopAt) { frame = 0; finish(); return; }
    const segment = segmentAt(at);
    if (segment !== state.segment) update({ segment });
    frame = requestAnimationFrame(tick);
  };
  frame = requestAnimationFrame(tick);
}

function stopClock(): void {
  if (frame) cancelAnimationFrame(frame);
  frame = 0;
}

/** Let go of the element: nothing is playing, nothing is held, and the position is forgotten. */
function release(): void {
  stopClock();
  if (element) {
    try { element.pause(); } catch { /* nothing to stop */ }
    element.removeAttribute("src");
  }
  if (held) { URL.revokeObjectURL(held); held = null; }
  active = null;
  stopAt = null;
}

/** The end of the part, or of the one passage that was asked for. Either way the next press starts over. */
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

async function start(part: StoryPart, from: number, until: number | null): Promise<void> {
  const mine = ++run;
  release();
  stopSpeech();
  silencePlayers(pause);
  // Before any await, so the browser still counts this as the gesture that asked.
  prime();
  update({ partId: part.id, status: "busy", segment: null, failed: null });
  try {
    let row = part;
    if (!row.audioRef) {
      row = await backendSession.recordStoryPart(part.storyId, part.id, repository.snapshot().deviceId);
      if (mine !== run) return;
      // The row reaches the replica the way every server-written row does; it plays meanwhile.
      void syncEngine.syncNow();
    }
    const blob = await clipBlob(row.audioRef!);
    if (mine !== run) return;
    const player = audio();
    held = URL.createObjectURL(blob);
    active = row;
    stopAt = until;
    player.src = held;
    player.currentTime = from;
    update({ status: "playing", segment: segmentAt(from) });
    await player.play();
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
  void start(part, 0, null);
}

/**
 * A touch on a passage. While this part is playing it moves the recording there and it goes on to
 * the end; otherwise it plays that passage alone.
 */
export function playSegment(part: StoryPart, index: number): void {
  const passage = part.audioSegments[index];
  if (!passage) return;
  if (state.partId === part.id && state.status === "playing" && element) {
    stopAt = null;
    try { element.currentTime = passage.start; } catch { /* not seekable yet */ }
    update({ segment: index });
    return;
  }
  void start(part, passage.start, passage.end);
}

export function pause(): void {
  if (state.status !== "playing") return;
  try { element?.pause(); } catch { /* nothing to stop */ }
  stopClock();
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
