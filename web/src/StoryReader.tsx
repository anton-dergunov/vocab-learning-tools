/**
 * Reading a story: a deck of pages, one part to a page, and a last page that lists the words.
 *
 * **A deck rather than a scroller**, and that is the whole layout decision. A part is two to four
 * sentences under a picture, which is about one screen — so a column of them is a page you scroll to
 * see what a swipe would show whole. It is the same deck a word's cards are (`deck.tsx`), and so it
 * moves the same way: a swipe that follows the finger, a horizontal scroll, the arrow keys, and two
 * arrows that sit beside the column when there is margin for them and under it when there is not.
 * There are no dots and no footer — where you are is the counter in the header, and a control that
 * needs its own row is a row the story does not get. The ivy leaves are for the wide layout only,
 * where they fill the space the picture leaves the words; narrow, the picture opens the page.
 *
 * **The translation is never drawn before it is asked for**, which is `LoopPlayer`'s rule about an
 * answer arriving before the recall gap has passed, in the one other place Acervo has one. The
 * space it will take is held open, so revealing it does not move the story under the reader's eye.
 *
 * Marks are found rather than stored: `storySpans` locates the forms the writer reported, and a
 * form it cannot find is simply not marked. The translation is marked the same way from the words
 * the translator reported, and a story translated before that was asked for simply has none.
 * See `selectors.ts`.
 *
 * Only a page and its neighbours fetch their picture. Every page is mounted — that is what lets a
 * swipe show the next one under the finger — but a picture is a blob behind bearer auth, and a
 * story of six should not ask for six at once to read the first.
 */

import { useMemo, useState } from "react";
import { DeckEdges, Hedera, useDeck } from "./deck";
import type { Story, StoryPart, StoryWord } from "./domain";
import { BackIcon } from "./icons";
import { usePicture } from "./picture";
import { storySpans, type StoryWordEntry } from "./selectors";

function Picture({ part, title, near }: { part: StoryPart; title: string; near: boolean }) {
  const { url, error } = usePicture(near ? part.imageRef : null);
  // The frame is always here, drawn or not: a picture that arrives into space already reserved
  // does not move the words under it.
  return <div className={`story-pic${url ? " is-ready" : ""}`}>
    {url
      ? <img src={url} alt={part.imagePrompt || `Picture for ${title}`} />
      : <span className="story-pic-note">
        {error ? "That picture could not be read."
          : part.failureReason ? "No picture for this part."
            // A picture that exists and has not arrived yet is not one being drawn.
            : part.imageRef ? "" : "Drawing…"}
      </span>}
  </div>;
}

function PartPage({ story, part, number, words, near, revealed, onReveal, onHide }: {
  story: Story;
  part: StoryPart;
  number: number;
  words: StoryWord[];
  near: boolean;
  revealed: boolean;
  onReveal(): void;
  onHide(): void;
}) {
  const spans = useMemo(() => storySpans(part.text, words), [part.text, words]);
  // The same word in the reader's own language, where the translator said what it became.
  const translated = useMemo(
    () => storySpans(part.translation, words, "translationForms"), [part.translation, words]);
  return <article className="card story-card" aria-label={`Part ${number}`}>
    <div className="story-body">
      <Picture part={part} title={story.title || "this story"} near={near} />
      <div className="story-copy">
        <Hedera side="above" />
        {part.heading && <h3 className="story-head"><span className="story-no">{number}</span> · {part.heading}</h3>}
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
            ? <>
              <p className="story-tr">
                {part.headingTranslation && <span className="story-tr-head">{part.headingTranslation}. </span>}
                {translated.map((span, position) => (
                  span.lexemeId
                    ? <b key={position} className="story-mark">{span.text}</b>
                    : <span key={position}>{span.text}</span>
                ))}
              </p>
              {/* A way back to the withheld state: reading it again is the point of the app, and a
                  translation that could only ever be revealed would be there for the rest of the
                  visit. A button and not a tap on the text, so the text can still be selected. */}
              <button className="story-hide" onClick={onHide} aria-label="Hide the translation">Hide</button>
            </>
            : <button className="story-reveal" onClick={onReveal} disabled={!part.translation}>
              {part.translation ? "Tap to read it in your own language" : "Not translated yet"}
            </button>}
        </div>
        <Hedera side="below" />
      </div>
    </div>
  </article>;
}

/**
 * The last page: the words the story was made from, each as it looks in the word list. It is the
 * one place a story says what it was for, and a word it could not work in is shown, dimmed, rather
 * than left out — asked for and not used is a fact about the story.
 */
function WordsPage({ entries }: { entries: StoryWordEntry[] }) {
  return <article className="card story-card story-words-page" aria-label="Words in this story">
    <div className="story-body">
      <div className="story-copy">
        <Hedera side="above" />
        <h3 className="story-head">Words</h3>
        <div className="rows">
          {entries.map((entry) => <div key={entry.lexemeId} className={`row${entry.used ? "" : " unused"}`}>
            <span className="plate" aria-hidden="true">{entry.emoji}</span>
            <span>
              <span className="word">{entry.headword}</span>
              {entry.gloss && <span className="gloss">{entry.gloss}</span>}
            </span>
          </div>)}
        </div>
        <Hedera side="below" />
      </div>
    </div>
  </article>;
}

export default function StoryReader({ story, title, parts, words, entries, onBack }: {
  story: Story;
  /** What the header calls it: its own title, or the words it was asked to teach. */
  title: string;
  parts: StoryPart[];
  words: StoryWord[];
  entries: StoryWordEntry[];
  onBack(): void;
}) {
  const pages = parts.length ? parts.length + 1 : 0;
  const { root, track, at, go, beside, onScroll } = useDeck(story.id);
  /* Which parts have been turned over. Per part rather than one switch for the story, because
     revealing one answer must not reveal the next — and it is deliberately *not* remembered
     between visits: coming back to a story you have read is reading it again. */
  const [shown, setShown] = useState<Set<string>>(() => new Set());
  const reveal = (id: string) => setShown((current) => new Set(current).add(id));
  const hide = (id: string) => setShown((current) => {
    const next = new Set(current);
    next.delete(id);
    return next;
  });

  return <div className={`cards story-read${beside ? " edges-beside" : ""}`} ref={root}>
    {/* Where you are, and what it is, in the line the back arrow already owns: the way back on the
        left, the title in the middle of the view, the counter on the right. The title gives way (it
        is cut short) before either side does. */}
    <div className="loops-back story-bar">
      <span className="story-bar-side">
        <button className="icon-btn" onClick={onBack} aria-label="Back to the stories"><BackIcon /></button>
        <span className="label">Stories</span>
      </span>
      <span className="story-bar-title">{title}</span>
      {/* An empty cell when there is no counter, so the title stays in the middle column. */}
      {pages > 0
        ? <span className="story-bar-count">{Math.min(at + 1, pages)} / {pages}</span>
        : <span />}
    </div>

    {parts.length === 0
      ? <p className="empty">This story has not been written yet.</p>
      : <div className="cards-stage">
        <div className="cards-track" ref={track} onScroll={onScroll}>
          {parts.map((part, index) => <PartPage
            key={part.id} story={story} part={part} number={index + 1} words={words}
            near={Math.abs(index - at) <= 1}
            revealed={shown.has(part.id)} onReveal={() => reveal(part.id)} onHide={() => hide(part.id)}
          />)}
          <WordsPage entries={entries} />
        </div>
      </div>}

    {parts.length > 0
      && <DeckEdges at={at} count={pages} go={go} previous="The part before" next="The next part" />}
  </div>;
}
