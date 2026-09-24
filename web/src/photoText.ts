/**
 * The photo's page, as a finger reads it: which word a tap landed on, which sentence it is in, and
 * the outlines to draw for both.
 *
 * Pure in the way `selectors.ts` is — a `PhotoReading` from the server in, ids and polygons out — so
 * the hit test is testable without a camera, a canvas or layout. Everything is in the photo's own
 * normalised coordinates, which is also the SVG's `viewBox` space: there is one coordinate system on
 * screen and nothing to keep in step.
 *
 * **The tolerance is relative to the line height, not the image.** The spike used a fixed 3% of the
 * image width, and a tap on a word the OCR had lost then selected the word on the line above
 * instead. A tap near nothing selects nothing, so the owner sees the word was not read, rather than
 * getting the meaning of a different one.
 */

import type { PhotoPoint, PhotoReading, PhotoSentence, PhotoWord } from "./api";
import type { PhotoRegion } from "./domain";

/** How far from a word a tap may land and still mean it, as a share of that word's height. */
const REACH = 0.6;
/** Below this, a word is shown as uncertain rather than hidden: it may be the very word meant. */
export const UNCERTAIN = 0.6;

const WORDLIKE = /[\p{L}\p{N}]/u;

/** Whether a word is one a person could mean — not a comma Vision reported on its own. */
export function isWord(word: PhotoWord): boolean {
  return WORDLIKE.test(word.text);
}

function inside(point: PhotoPoint, polygon: PhotoPoint[]): boolean {
  let hit = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    if ((yi > point[1]) !== (yj > point[1]) && point[0] < ((xj - xi) * (point[1] - yi)) / (yj - yi) + xi) {
      hit = !hit;
    }
  }
  return hit;
}

interface Box { left: number; top: number; right: number; bottom: number }

function box(polygon: PhotoPoint[], width: number, height: number): Box {
  const xs = polygon.map(([x]) => x * width);
  const ys = polygon.map(([, y]) => y * height);
  return { left: Math.min(...xs), top: Math.min(...ys), right: Math.max(...xs), bottom: Math.max(...ys) };
}

/**
 * The word a tap means, or null. `point` is normalised to the photo.
 *
 * Inside a word's outline is that word. Otherwise the nearest word whose box is within `REACH` of
 * its own height — measured in the photo's pixels, so a tall narrow photo does not stretch it.
 */
export function hitTest(reading: PhotoReading, point: PhotoPoint): string | null {
  const words = reading.words.filter(isWord);
  for (const word of words) {
    if (word.polygons.some((polygon) => inside(point, polygon))) return word.id;
  }
  const x = point[0] * reading.width;
  const y = point[1] * reading.height;
  let best: { id: string; distance: number } | null = null;
  for (const word of words) {
    for (const polygon of word.polygons) {
      const edges = box(polygon, reading.width, reading.height);
      const dx = Math.max(edges.left - x, 0, x - edges.right);
      const dy = Math.max(edges.top - y, 0, y - edges.bottom);
      const distance = Math.hypot(dx, dy);
      if (distance <= REACH * (edges.bottom - edges.top) && (!best || distance < best.distance)) {
        best = { id: word.id, distance };
      }
    }
  }
  return best?.id ?? null;
}

function order(reading: PhotoReading): Map<string, number> {
  return new Map(reading.words.map((word, index) => [word.id, index]));
}

/** Every word from one to the other in reading order, inclusive — a drag across a phrase. */
export function span(reading: PhotoReading, from: string, to: string): string[] {
  const positions = order(reading);
  const [first, last] = [positions.get(from) ?? 0, positions.get(to) ?? 0].sort((a, b) => a - b);
  return reading.words.slice(first, last + 1).filter(isWord).map((word) => word.id);
}

/**
 * What a tap does to a selection. A neighbour of it, in the same sentence, extends it into a phrase;
 * the only word selected is let go; anything else starts again with the word tapped.
 */
export function tapped(reading: PhotoReading, selection: string[], id: string): string[] {
  if (!selection.length) return [id];
  if (selection.length === 1 && selection[0] === id) return [];
  if (selection.includes(id)) return [id];
  const sentence = sentenceOf(reading, selection);
  if (!sentence || !sentence.wordIds.includes(id)) return [id];
  const byId = wordsById(reading);
  const words = sentence.wordIds.filter((one) => {
    const word = byId.get(one);
    return word ? isWord(word) : false;
  });
  const at = words.indexOf(id);
  const first = words.indexOf(selection[0]);
  const last = words.indexOf(selection[selection.length - 1]);
  if (at === first - 1 || at === last + 1) return span(reading, words[Math.min(at, first)], words[Math.max(at, last)]);
  return [id];
}

/** The sentence a selection is in: the one its first word belongs to. */
export function sentenceOf(reading: PhotoReading, selection: string[]): PhotoSentence | null {
  if (!selection.length) return null;
  return reading.sentences.find((sentence) => sentence.wordIds.includes(selection[0])) ?? null;
}

function wordsById(reading: PhotoReading): Map<string, PhotoWord> {
  return new Map(reading.words.map((word) => [word.id, word]));
}

/** Where the selection sits in its sentence's text, for the quick look-up to point at. */
export function selectionIn(
  reading: PhotoReading, sentence: PhotoSentence, selection: string[]
): { start: number; end: number } | null {
  const words = wordsById(reading);
  const chosen = selection.map((id) => words.get(id)).filter((word): word is PhotoWord => Boolean(word));
  if (!chosen.length) return null;
  const start = Math.min(...chosen.map((word) => word.start)) - sentence.start;
  const end = Math.max(...chosen.map((word) => word.end)) - sentence.start;
  return start >= 0 && end <= sentence.text.length && end > start ? { start, end } : null;
}

/** The text of the selection, as it reads on the page. */
export function selectedText(reading: PhotoReading, selection: string[]): string {
  const words = wordsById(reading);
  const chosen = selection.map((id) => words.get(id)).filter((word): word is PhotoWord => Boolean(word));
  if (!chosen.length) return "";
  return reading.text.slice(Math.min(...chosen.map((w) => w.start)), Math.max(...chosen.map((w) => w.end)));
}

/** The outlines of the selected words, every printed piece of each. */
export function wordOutlines(reading: PhotoReading, selection: string[]): PhotoPoint[][] {
  const words = wordsById(reading);
  return selection.flatMap((id) => words.get(id)?.polygons ?? []);
}

/**
 * The sentence as one band per printed line: from the left edge of its first piece on that line to
 * the right edge of its last. A hyphenated word's second piece belongs to the line after its first.
 */
export function sentenceOutlines(reading: PhotoReading, sentence: PhotoSentence): PhotoPoint[][] {
  const words = wordsById(reading);
  const lineOrder = reading.lines.map((line) => line.id);
  const bands = new Map<string, PhotoPoint[][]>();
  sentence.wordIds.forEach((id) => {
    const word = words.get(id);
    if (!word) return;
    const first = lineOrder.indexOf(word.lineId);
    word.polygons.forEach((polygon, piece) => {
      const line = lineOrder[first + piece] ?? word.lineId;
      bands.set(line, [...(bands.get(line) ?? []), polygon]);
    });
  });
  return lineOrder.flatMap((line) => {
    const pieces = bands.get(line);
    if (!pieces?.length) return [];
    const first = pieces[0];
    const last = pieces[pieces.length - 1];
    if (first.length !== 4 || last.length !== 4) return pieces;
    return [[first[0], last[1], last[2], first[3]]];
  });
}

const round = (polygons: PhotoPoint[][]): [number, number][][] =>
  polygons.map((polygon) => polygon.map(([x, y]) => [
    Math.min(1, Math.max(0, Math.round(x * 10_000) / 10_000)),
    Math.min(1, Math.max(0, Math.round(y * 10_000) / 10_000))
  ] as [number, number]));

/** What an attestation keeps of the photo: where the word and its sentence were. */
export function photoRegionFor(
  reading: PhotoReading, selection: string[], sentence: PhotoSentence | null
): PhotoRegion {
  return {
    words: round(wordOutlines(reading, selection)),
    sentence: sentence ? round(sentenceOutlines(reading, sentence)) : []
  };
}

/** An SVG `points` attribute for a polygon in the photo's normalised space. */
export function pointsOf(polygon: PhotoPoint[]): string {
  return polygon.map(([x, y]) => `${x},${y}`).join(" ");
}
