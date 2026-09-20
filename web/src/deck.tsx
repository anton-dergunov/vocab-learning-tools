/**
 * What a deck of cards needs, shared by the two things in Acervo that are one: a word's cards and a
 * story's pages.
 *
 * **A deck is a native scroller**, and everything the owner likes about moving through one comes from
 * that: the page follows the finger and reveals the next one, a trackpad's horizontal scroll works,
 * and a release settles on a card. There is no gesture code here to keep in step with the browser's.
 * `styles.css` (`.cards-track`) is the other half of it.
 *
 * This is the part of that behaviour with logic in it — where the arrows go, how a card is reached,
 * which keys move it — lifted out of `ArticleCards` so a second deck does not carry a second copy.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type UIEvent } from "react";
import { BackIcon, HederaIcon } from "./icons";

/** Whether a key press belongs to a field the reader is typing into rather than to the page. */
export function isTyping(target: EventTarget | null): boolean {
  return target instanceof Element && Boolean(target.closest("input, textarea, select, [contenteditable], .cm-editor"));
}

/** An ivy leaf, pointing away from the words it marks: ☙ above them, ❧ below them. */
export function Hedera({ side }: { side: "above" | "below" }) {
  return <span className={`card-ornament ${side}`} aria-hidden="true"><HederaIcon /></span>;
}

/**
 * The state of one deck: which card is showing, how to reach another, and whether the arrows fit
 * beside the column.
 *
 * `resetKey` starts the deck again at its first card when it changes — a different word, a different
 * story — and is the only thing that does.
 */
export function useDeck(resetKey: string) {
  const root = useRef<HTMLDivElement | null>(null);
  const track = useRef<HTMLDivElement | null>(null);
  const [at, setAt] = useState(0);
  const [beside, setBeside] = useState(false);

  /* Beside the column only where the margin really has room for them, measured against `.main`,
     which clips: a window-width rule put them where the space it assumed was not always there. */
  useEffect(() => {
    const element = root.current;
    const clipper = element?.closest(".main");
    if (!element || !clipper || typeof ResizeObserver === "undefined") return;
    const measure = () => {
      const inner = element.getBoundingClientRect();
      const outer = clipper.getBoundingClientRect();
      setBeside(inner.left - outer.left >= 100 && outer.right - inner.right >= 100);
    };
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    observer.observe(clipper);
    measure();
    return () => observer.disconnect();
  }, []);

  const go = useCallback((index: number) => {
    const element = track.current;
    if (!element) return;
    const to = Math.max(0, Math.min(index, element.children.length - 1));
    element.scrollTo({ left: to * element.clientWidth, behavior: "smooth" });
  }, []);

  useLayoutEffect(() => {
    setAt(0);
    if (track.current) track.current.scrollLeft = 0;
  }, [resetKey]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      if (isTyping(event.target)) return;
      event.preventDefault();
      go(at + (event.key === "ArrowRight" ? 1 : -1));
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [at, go]);

  const onScroll = useCallback((event: UIEvent<HTMLDivElement>) => {
    const element = event.currentTarget;
    setAt(Math.round(element.scrollLeft / Math.max(element.clientWidth, 1)));
  }, []);

  return { root, track, at, go, beside, onScroll };
}

/**
 * The two arrows. Beside the column when there is margin for them, else a pair at the foot of the
 * deck; on a touch device `styles.css` hides them, because a swipe is the gesture there.
 */
export function DeckEdges({ at, count, go, previous, next }: {
  at: number;
  count: number;
  go(index: number): void;
  previous: string;
  next: string;
}) {
  return <div className="cards-edges">
    <button type="button" className="cards-edge prev" aria-label={previous} disabled={at === 0} onClick={() => go(at - 1)}><BackIcon /></button>
    <button type="button" className="cards-edge next" aria-label={next} disabled={at >= count - 1} onClick={() => go(at + 1)}><BackIcon /></button>
  </div>;
}
