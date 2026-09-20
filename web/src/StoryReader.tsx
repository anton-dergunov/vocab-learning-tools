/**
 * Reading a story: one part to a screen, the picture above it, the translation behind a tap.
 *
 * **A deck rather than a scroller**, and that is the whole layout decision. A part is two to four
 * sentences under a picture, which is about one screen — so a column of them is a page you scroll
 * to see what a swipe would show whole. Arrows, a swipe and the arrow keys move between parts, and
 * a dot per part says where you are. It reads like the comic page the feature was sketched from.
 *
 * **The translation is never drawn before it is asked for**, which is `LoopPlayer`'s rule about an
 * answer arriving before the recall gap has passed, in the one other place Acervo has one. The
 * space it will take is held open, so revealing it does not move the story under the reader's eye.
 *
 * The controls are the footer of a column that owns its height, never a sticky element inside a
 * scroller — so Next is always where you left it, exactly as the player's transport is.
 *
 * Marks are found rather than stored: `storySpans` locates the forms the writer reported, and a
 * form it cannot find is simply not marked. See `selectors.ts`.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import type { Story, StoryPart, StoryWord } from "./domain";
import { BackIcon, ForwardIcon } from "./icons";
import { usePicture } from "./picture";
import { storySpans } from "./selectors";

/** How far a finger has to travel before it counts as a swipe rather than a tap. */
const SWIPE = 48;

function Picture({ part, title }: { part: StoryPart; title: string }) {
  const { url, error } = usePicture(part.imageRef);
  // The frame is always here, drawn or not: a picture that arrives into space already reserved
  // does not move the words under it.
  return <div className={`story-pic${url ? " is-ready" : ""}`}>
    {url
      ? <img src={url} alt={part.imagePrompt || `Picture for ${title}`} />
      : <span className="story-pic-note">
        {error ? "That picture could not be read."
          : part.failureReason ? "No picture for this part."
            : "Drawing…"}
      </span>}
  </div>;
}

export default function StoryReader({ story, parts, words }: {
  story: Story;
  parts: StoryPart[];
  words: StoryWord[];
}) {
  const [at, setAt] = useState(0);
  /* Which parts have been turned over. Per part rather than one switch for the story, because
     revealing one answer must not reveal the next — and it is deliberately *not* remembered
     between visits: coming back to a story you have read is reading it again. */
  const [shown, setShown] = useState<Set<string>>(() => new Set());
  const touch = useRef<number | null>(null);
  const index = Math.min(at, Math.max(parts.length - 1, 0));
  const part = parts[index];

  const go = (delta: number) => setAt((current) =>
    Math.max(0, Math.min(parts.length - 1, current + delta)));

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "ArrowRight") go(1);
      if (event.key === "ArrowLeft") go(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [parts.length]);

  const spans = useMemo(
    () => (part ? storySpans(part.text, words) : []),
    [part?.id, part?.text, words]
  );

  if (!part) {
    return <div className="story-read">
      <p className="empty">This story has not been written yet.</p>
    </div>;
  }

  const revealed = shown.has(part.id);
  const reveal = () => setShown((current) => new Set(current).add(part.id));

  return <div
    className="story-read"
    onTouchStart={(event) => { touch.current = event.touches[0]?.clientX ?? null; }}
    onTouchEnd={(event) => {
      const from = touch.current;
      touch.current = null;
      if (from === null) return;
      const travelled = (event.changedTouches[0]?.clientX ?? from) - from;
      if (Math.abs(travelled) > SWIPE) go(travelled < 0 ? 1 : -1);
    }}
  >
    <div className="story-dots" aria-hidden="true">
      {parts.map((one, position) => (
        <span key={one.id} className={`story-dot${position === index ? " on" : ""}`} />
      ))}
    </div>

    <article className="story-part" aria-live="polite">
      <Picture part={part} title={story.title || "this story"} />
      {part.heading && <h3 className="story-head">{part.heading}</h3>}
      <p className="story-text" lang={story.language}>
        {spans.map((span, position) => (
          span.lexemeId
            ? <b key={position} className="story-mark">{span.text}</b>
            : <span key={position}>{span.text}</span>
        ))}
      </p>

      {/* The space is held whether or not it has been asked for, so revealing moves nothing. */}
      <div className="story-tr-slot">
        {revealed
          ? <p className="story-tr">
            {part.headingTranslation && <span className="story-tr-head">{part.headingTranslation}. </span>}
            {part.translation}
          </p>
          : <button className="story-reveal" onClick={reveal} disabled={!part.translation}>
            {part.translation ? "Tap to read it in your own language" : "Not translated yet"}
          </button>}
      </div>
    </article>

    <footer className="story-controls">
      <button
        className="icon-btn" onClick={() => go(-1)} disabled={index === 0}
        aria-label="The part before"
      ><BackIcon /></button>
      <span className="story-count">{index + 1} of {parts.length}</span>
      <button
        className="icon-btn" onClick={() => go(1)} disabled={index >= parts.length - 1}
        aria-label="The next part"
      ><ForwardIcon /></button>
    </footer>
  </div>;
}
