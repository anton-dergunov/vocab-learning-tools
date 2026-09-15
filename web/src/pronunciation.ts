/**
 * Hearing a word: every pronunciation call, the one audio element, and the clips kept on this device.
 *
 * **Reads are offline-first here too.** A clip the replica names and this device holds plays with no
 * request at all. Otherwise the server is asked, and it answers with the stored clip while it still
 * says what the record says, or records a new one — which is a write, so it needs the server and
 * fails loudly without one. Nothing is queued: a press that could not be answered says so.
 *
 * A clip is a row in the replica (`pronunciations`) naming a file in the server's media directory,
 * the way a picture is. The bytes are kept in `mediaStore.ts`'s `pronunciations` store — a store of
 * its own, so switching this off forgets clips and never pictures — keyed by the reference the row
 * carries. Recording again gives the row a new reference, so a stale key is simply never asked for.
 *
 * A **selection** is the one thing spoken and not kept, anywhere: it names no record, so there is no
 * row to put it in and nothing to tell when it is stale. `selectionSpeech.ts` decides what the runs
 * are; this module says them.
 */

import { useSyncExternalStore } from "react";
import { AcervoApiError, backendSession } from "./api";
import type { Pronunciation, PronunciationTarget, VocabularyGraph } from "./domain";
import { pronunciationCacheEnabled } from "./editorPreferences";
import { pronunciationId } from "./ids";
import { createMediaStore, type MediaStore } from "./mediaStore";
import { repository } from "./repository";
import { syncEngine } from "./sync";

/** What a play button says. `id` is null in an unsaved proposal, which has nothing to store against. */
export interface SayTarget {
  kind: PronunciationTarget;
  id: string | null;
  text: string;
  lang: string;
}

/** One stretch of a selection in one language, and the record it is the whole text of, if any. */
export interface SpokenRun {
  text: string;
  lang: string;
  target: SayTarget | null;
}

export interface Played {
  /** The voice that read it, for the toast. */
  voice: string | null;
  /** True when a stored clip played, which is what can be recorded again. */
  stored: boolean;
}

export const COLLECTIONS: Record<PronunciationTarget, string> = {
  lexeme: "lexemes", sense: "senses", example: "examples", attestation: "attestations"
};

let store: MediaStore = createMediaStore("pronunciations");
/** Clips heard this session while keeping is off, so a second press does not fetch again. Bounded. */
const session = new Map<string, Blob>();
const SESSION_LIMIT = 40;

/* ── what is playing ─────────────────────────────────────────────────── */

export interface SpeechState {
  /** The key being fetched or recorded. */
  busy: string | null;
  /** The key being heard. */
  playing: string | null;
}

let state: SpeechState = { busy: null, playing: null };
const listeners = new Set<() => void>();

function update(next: Partial<SpeechState>): void {
  state = { ...state, ...next };
  listeners.forEach((listener) => listener());
}

export function keyOf(target: Pick<SayTarget, "kind" | "id" | "text">): string {
  return `${target.kind}:${target.id ?? target.text}`;
}

export function useSpeechState(): SpeechState {
  return useSyncExternalStore(
    (listener) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    () => state
  );
}

/* ── the audio element ───────────────────────────────────────────────── */

let element: HTMLAudioElement | null = null;
let finish: (() => void) | null = null;

/* A few milliseconds of silence. iOS lets an element play only from inside the gesture that asked,
   and the clip arrives after a fetch — so the element is started on silence first, synchronously,
   and the clip is swapped in once it arrives. */
const SILENCE = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";

function audio(): HTMLAudioElement {
  element ??= new Audio();
  return element;
}

/** Called synchronously from the press, before anything is awaited. */
function prime(): void {
  const player = audio();
  if (!player.paused) return;
  try {
    player.src = SILENCE;
    void player.play()?.catch(() => undefined);
  } catch { /* jsdom, or a browser with no audio at all */ }
}

/** Stop whatever is being heard. */
export function stop(): void {
  const player = element;
  if (player) {
    try { player.pause(); } catch { /* nothing to stop */ }
  }
  finish?.();
  finish = null;
  update({ playing: null });
}

async function sound(blob: Blob, key: string): Promise<void> {
  stop();
  const player = audio();
  const url = URL.createObjectURL(blob);
  update({ playing: key });
  try {
    await new Promise<void>((resolve, reject) => {
      finish = resolve;
      // Only this clip's own end: the silence `prime` started may finish after the clip was swapped in.
      player.onended = () => { if (player.src === url) resolve(); };
      player.onerror = () => { if (player.src === url) reject(new Error("This device could not play that recording.")); };
      player.src = url;
      player.play().catch((error: unknown) => {
        const name = error instanceof DOMException ? error.name : "";
        reject(new Error(name === "NotAllowedError"
          ? "This device would not start the audio. Press play again."
          : "This device could not play that recording."));
      });
    });
  } catch (error) {
    console.warn("Acervo: a pronunciation could not be played", { key, type: blob.type, size: blob.size, error });
    throw error;
  } finally {
    finish = null;
    player.onended = null;
    player.onerror = null;
    URL.revokeObjectURL(url);
    if (state.playing === key) update({ playing: null });
  }
}

/* ── the clips ───────────────────────────────────────────────────────── */

/** The stored clip for a target, while it still says what the record says. */
export function currentClip(graph: Pick<VocabularyGraph, "pronunciations">, target: SayTarget): Pronunciation | null {
  if (!target.id) return null;
  const id = pronunciationId(target.kind, target.id);
  const clip = graph.pronunciations.find((record) => record.id === id);
  return clip && !clip.deleted && clip.text === target.text && clip.lang === target.lang ? clip : null;
}

async function download(reference: string): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(backendSession.mediaFileUrl(reference), { headers: backendSession.mediaHeaders(), cache: "no-store" });
  } catch {
    throw new Error("This pronunciation is not on this device yet, and the server cannot be reached.");
  }
  if (!response.ok) {
    console.warn("Acervo: a pronunciation could not be read from the server", { reference, status: response.status });
    throw new Error(response.status === 404
      ? "That recording is not on the server any more. Record it again."
      : `That recording could not be read from the server (${response.status}).`);
  }
  return response.blob();
}

/** The clip's bytes: this device first, then the server — kept on the device when keeping is on. */
async function clipBlob(reference: string): Promise<Blob> {
  const kept = await store.read(reference).catch(() => null);
  if (kept) return kept.blob;
  const remembered = session.get(reference);
  if (remembered) return remembered;
  const blob = await download(reference);
  if (pronunciationCacheEnabled()) {
    await store.save(reference, blob).catch(() => undefined);
  } else {
    session.set(reference, blob);
    if (session.size > SESSION_LIMIT) session.delete(session.keys().next().value as string);
  }
  return blob;
}

/** For the export, which writes clips into a zip rather than playing them. */
export async function clipBytes(reference: string): Promise<Uint8Array> {
  return new Uint8Array(await (await clipBlob(reference)).arrayBuffer());
}

function failure(error: unknown): Error {
  if (error instanceof AcervoApiError && error.code === "offline") {
    return new Error("Recording a pronunciation needs the server, and it cannot be reached.");
  }
  return error instanceof Error ? error : new Error("That could not be pronounced.");
}

/**
 * Say one target. Pressing the button that is playing stops it instead.
 *
 * `again` asks the server for a fresh recording even when the stored one is current — "Record again"
 * after hearing a bad one. The previous clip is dropped from this device as the new one arrives.
 */
export async function play(target: SayTarget, options: { again?: boolean } = {}): Promise<Played | null> {
  const key = keyOf(target);
  if (!options.again && (state.playing === key || state.busy === key)) {
    stop();
    return null;
  }
  prime();
  update({ busy: key });
  try {
    if (!target.id) {
      const spoken = await backendSession.utterance(target.text, target.lang).catch((error) => { throw failure(error); });
      update({ busy: null });
      await sound(spoken.audio, key);
      return { voice: spoken.voice, stored: false };
    }
    const graph = repository.snapshot();
    const previous = graph.pronunciations.find((record) => record.id === pronunciationId(target.kind, target.id!));
    let clip = options.again ? null : currentClip(graph, target);
    if (!clip) {
      clip = await backendSession.pronounce(COLLECTIONS[target.kind], target.id, graph.deviceId, options.again === true)
        .catch((error) => { throw failure(error); });
      // The row reaches the replica the way every server-written row does; the clip plays meanwhile.
      void syncEngine.syncNow();
      if (previous && previous.audioRef !== clip.audioRef) void forget(previous.audioRef);
    }
    const blob = await clipBlob(clip.audioRef);
    update({ busy: null });
    await sound(blob, key);
    return { voice: clip.voice, stored: true };
  } finally {
    if (state.busy === key) update({ busy: null });
  }
}

/** Say a selection, one run after another. Nothing is stored unless a run is a whole stored record. */
export async function playRuns(runs: SpokenRun[]): Promise<void> {
  for (const run of runs) {
    if (run.target?.id) {
      await play(run.target);
      continue;
    }
    const key = `selection:${run.lang}:${run.text}`;
    prime();
    update({ busy: key });
    let spoken;
    try {
      spoken = await backendSession.utterance(run.text, run.lang).catch((error) => { throw failure(error); });
    } finally {
      update({ busy: null });
    }
    await sound(spoken.audio, key);
  }
}

/* ── recording in advance ─────────────────────────────────────────────── */

export interface RecordInAdvance {
  headword: boolean;
  definitions: boolean;
  examples: boolean;
}

const sameLanguage = (one: string, other: string) =>
  one.split("-")[0].toLowerCase() === other.split("-")[0].toLowerCase();

/**
 * What recording in advance means for one word, read from the replica: the fields chosen, in the
 * language being learned only, that have no current clip. A query, never a queue — the rule the
 * picture work lives by, so a word saved twice asks for nothing it already has.
 *
 * Twinned with `acervo.pronunciation.targets.wanted` on the server, which a sweep would use.
 */
export function recordingsWanted(graph: VocabularyGraph, lexemeId: string, choice: RecordInAdvance): SayTarget[] {
  const lexeme = graph.lexemes.find((record) => record.id === lexemeId && !record.deleted);
  if (!lexeme) return [];
  const found: SayTarget[] = [];
  if (choice.headword) found.push({ kind: "lexeme", id: lexeme.id, text: lexeme.headword, lang: lexeme.language });
  graph.senses
    .filter((sense) => sense.lexemeId === lexemeId && !sense.deleted)
    .sort((left, right) => left.order - right.order || left.id.localeCompare(right.id))
    .forEach((sense) => {
      if (choice.definitions && sameLanguage(sense.definitionLang, lexeme.language)) {
        found.push({ kind: "sense", id: sense.id, text: sense.definition, lang: sense.definitionLang });
      }
      if (!choice.examples) return;
      graph.examples
        .filter((example) => example.senseId === sense.id && !example.deleted && !example.videoRef
          && sameLanguage(example.textLang, lexeme.language))
        .forEach((example) => found.push({ kind: "example", id: example.id, text: example.text, lang: example.textLang }));
    });
  return found.filter((target) => !currentClip(graph, target));
}

/* ── keeping clips ───────────────────────────────────────────────────── */

async function forget(reference: string): Promise<void> {
  session.delete(reference);
  await store.remove(reference).catch(() => undefined);
}

let filling: Promise<number> | null = null;

/**
 * Bring every clip the replica names onto this device, so a word recorded elsewhere — or in advance —
 * plays offline. One at a time and stopping at the first failure, because the usual failure is
 * "offline" and the next sync will try again. Only while keeping is on.
 */
export function fill(graph: Pick<VocabularyGraph, "pronunciations"> = repository.snapshot()): Promise<number> {
  if (filling || !pronunciationCacheEnabled()) return filling ?? Promise.resolve(0);
  filling = (async () => {
    let fetched = 0;
    for (const clip of graph.pronunciations) {
      if (clip.deleted || !clip.audioRef) continue;
      if (await store.read(clip.audioRef).catch(() => null)) continue;
      try {
        await store.save(clip.audioRef, await download(clip.audioRef));
        fetched += 1;
      } catch {
        break;
      }
    }
    return fetched;
  })().finally(() => { filling = null; });
  return filling;
}

/** Forget every clip kept on this device. The rows stay; a press fetches the clip again. */
export async function forgetPronunciations(): Promise<void> {
  session.clear();
  await store.clear().catch(() => undefined);
}

export function keptPronunciationBytes(): Promise<number> {
  return store.bytes().catch(() => 0);
}

/** For tests: a store that does not need IndexedDB. */
export function replaceStoreForTests(replacement: MediaStore): void {
  store = replacement;
  session.clear();
  state = { busy: null, playing: null };
  element = null;
}
