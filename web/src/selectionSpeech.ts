/**
 * What a selection says, split into runs of one language each.
 *
 * An article mixes languages on purpose — a Spanish sentence, its English translation, a definition
 * in Spanish, a note in English — and a selection can cross any of them. Every block that holds text
 * says what language it is in with an ordinary `lang` attribute, which a screen reader wants anyway,
 * so a selection is read by walking the blocks it touches and taking each one's language from the
 * markup rather than guessing it from the letters.
 *
 * Two small generosities, both because a selection is a rough gesture on a phone:
 *
 * - **A partial sentence is extended to the whole one**, inside its block, with `Intl.Segmenter` —
 *   hearing half a sentence is rarely what a thumb meant.
 * - **A run that turns out to be a whole stored record** (`data-say`) is read as that record, so it
 *   plays the kept clip, offline and with its emotion, instead of asking the server for a new one.
 *
 * Pure over the DOM it is handed: no network and no storage, so it is tested with jsdom.
 */

import type { SayTarget, SpokenRun } from "./pronunciation";

const BLOCK = "[lang]";

function segmenter(lang: string): Intl.Segmenter | null {
  try {
    return typeof Intl !== "undefined" && "Segmenter" in Intl ? new Intl.Segmenter(lang, { granularity: "sentence" }) : null;
  } catch {
    return null;
  }
}

/** The whole sentences of `text` that the span [start, end) touches. */
export function sentencesAround(text: string, start: number, end: number, lang: string): string {
  const splitter = segmenter(lang);
  if (!splitter) return text.slice(start, end);
  let from = start;
  let to = end;
  for (const piece of splitter.segment(text)) {
    const pieceEnd = piece.index + piece.segment.length;
    if (pieceEnd <= start || piece.index >= end) continue;
    from = Math.min(from, piece.index);
    to = Math.max(to, pieceEnd);
  }
  return text.slice(from, to);
}

/** How many characters of `block` come before the boundary (`node`, `offset`). */
function offsetWithin(block: Element, node: Node, offset: number): number {
  const before = document.createRange();
  before.selectNodeContents(block);
  before.setEnd(node, offset);
  return before.toString().length;
}

/**
 * The runs a selection inside `root` should be read as.
 *
 * `targets` maps a block's `data-say` to the record it is the whole text of. `fallback` is the
 * language of text in no tagged block at all, which is the article's own.
 */
export function runsOf(range: Range, root: Element, targets: ReadonlyMap<string, SayTarget>, fallback: string): SpokenRun[] {
  const blocks = [...root.querySelectorAll(BLOCK)]
    // The innermost tagged block only: an outer one would read its children's text twice.
    .filter((block) => !block.querySelector(BLOCK) && range.intersectsNode(block));

  const runs: SpokenRun[] = [];
  for (const block of blocks) {
    const whole = block.textContent ?? "";
    const lang = block.getAttribute("lang") || fallback;
    const start = block.contains(range.startContainer) ? offsetWithin(block, range.startContainer, range.startOffset) : 0;
    const end = block.contains(range.endContainer) ? offsetWithin(block, range.endContainer, range.endOffset) : whole.length;
    if (end <= start) continue;
    // Without the quotation marks a card sets an epigraph in: they are typography, not words.
    const text = sentencesAround(whole, start, end, lang).replace(/^[\s“”"«»]+|[\s“”"«»]+$/g, "");
    if (!text) continue;
    const said = block.getAttribute("data-say");
    const target = said ? targets.get(said) ?? null : null;
    runs.push({ text, lang, target: target && target.text.trim() === text ? target : null });
  }

  if (!runs.length) {
    const text = range.toString().trim();
    return text ? [{ text, lang: fallback, target: null }] : [];
  }
  return runs;
}
