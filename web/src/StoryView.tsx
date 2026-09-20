/**
 * The Stories surface: the stories you have, and the one you are reading.
 *
 * Modelled on `LoopView.tsx` down to the right-click menu, because it is the same shape of thing:
 * a list of made objects, each of which can be open, still being made, or asked for and never made.
 *
 * **One back arrow, and its meaning follows the level**: on an open story it returns to the
 * stories, and on the stories it returns to your words. Present at every width for the reason the
 * loops one is — a surface that replaces the list has to carry the way back out of itself.
 *
 * A story's state is derived and there is no status column: having no parts is the whole of what
 * "not written yet" means, and the job says how far along it is. So a story whose writing failed
 * simply reads as one that was asked for and not written, and Try again queues another.
 */

import { useEffect, useState, useSyncExternalStore, type CSSProperties } from "react";
import { jobFor, jobStream, isOpen as jobIsOpen } from "./jobs";
import { stripOf } from "./ProgressStrip";
import type { VocabularyGraph } from "./domain";
import { BackIcon, HourglassIcon, PlusIcon } from "./icons";
import StoryReader from "./StoryReader";
import {
  storiesIn, storyIsWritten, storyPartsOf, storyPictures, storyTitle, storyWordEntries, storyWordsOf
} from "./selectors";

function count(amount: number, noun: string): string {
  return `${amount} ${noun}${amount === 1 ? "" : "s"}`;
}

export default function StoryView({ graph, language, onMake, onClose, onDelete }: {
  graph: VocabularyGraph;
  language: string;
  onMake(): void;
  /** Back to the words. */
  onClose(): void;
  /** Online-only and loud when it fails, like every other write. */
  onDelete(storyId: string): void;
}) {
  const live = useSyncExternalStore(jobStream.subscribe, jobStream.getStatus);
  const stories = storiesIn(graph, language);
  const [openId, setOpenId] = useState<string | null>(null);
  const open = stories.find((story) => story.id === openId) ?? null;
  /* Which row has been right-clicked, and where within it, so the menu opens under the pointer —
     `LoopView`'s arrangement, and the finger gets the row's second snap point instead. */
  const [menu, setMenu] = useState<{ id: string; x: number; y: number } | null>(null);
  const menuId = menu?.id ?? null;

  useEffect(() => {
    if (!menuId) return;
    const away = (event: PointerEvent) => {
      if (event.target instanceof Element && event.target.closest(".loop-menu")) return;
      setMenu(null);
    };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setMenu(null); };
    window.addEventListener("pointerdown", away);
    window.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener("pointerdown", away);
      window.removeEventListener("keydown", escape);
    };
  }, [menuId]);

  if (open) {
    /* `reading` widens the column: a story is read beside its picture where there is room, and that
       is wider than the list's measure. The reader owns its own header, where the counter lives. */
    return <section className="loops stories reading">
      <StoryReader
        story={open}
        title={storyTitle(graph, open)}
        parts={storyPartsOf(graph, open.id)}
        words={storyWordsOf(graph, open.id)}
        entries={storyWordEntries(graph, open.id)}
        onBack={() => setOpenId(null)}
      />
    </section>;
  }

  return <section className="loops stories">
    <div className="loops-back">
      <button className="icon-btn" onClick={onClose} aria-label="Back to the list"><BackIcon /></button>
      <span className="label">Your words</span>
      <span className="spacer" />
    </div>

    <div className="loops-head">
      <h2>Stories</h2>
      <span className="spacer" />
      <button className="tb-btn primary" onClick={onMake}><PlusIcon /><span>Make a story</span></button>
    </div>

    {stories.length === 0 && <p className="empty">
      No stories yet. A story takes a few of your words and tells them back to you as something
      worth reading, which is how they stick.
    </p>}

    <div className="loops-list">
      {stories.map((story) => {
        const written = storyIsWritten(graph, story.id);
        const pictures = storyPictures(graph, story.id);
        const words = storyWordsOf(graph, story.id);
        const job = jobFor(live, "story", story.id);
        const making = jobIsOpen(job);
        const failure = job?.state === "failed"
          ? job.message || stripOf(job)?.failure || job.error || ""
          : "";
        const remove = () => { setMenu(null); onDelete(story.id); };
        return <div
          key={story.id} className="loop-item"
          onContextMenu={(event) => {
            event.preventDefault();
            const box = event.currentTarget.getBoundingClientRect();
            setMenu({ id: story.id, x: event.clientX - box.left, y: event.clientY - box.top });
          }}
        >
          <div className="loop-shell">
            <button
              className="loop-row" aria-disabled={!written}
              onClick={() => { if (written) setOpenId(story.id); }}
            >
              <span className={`loop-go story-go${written ? "" : " pending"}`}>
                {written ? (story.emoji || "📖") : <HourglassIcon />}
              </span>
              <span className="loop-main">
                <span className="loop-title">{storyTitle(graph, story)}</span>
                <span className="loop-sub">
                  {written
                    /* The words it was made from, on one line: what a story *is about* is what tells
                       two of them apart, and the ones that do not fit are simply cut off. */
                    ? <span className="story-words">{words.map((word) => word.sourceText).join(" · ")}</span>
                    : making
                      /* What it is *doing*, in the job's own words — this takes a minute, and
                         "being made" says nothing you could not already see. */
                      ? <span className="doing">{stripOf(job)?.phases.map((phase) => phase.text).join(" · ") || "Being written…"}</span>
                      /* Why, not only that: the reason is on the job the whole time. */
                      : <span className="warn">{failure ? `Never written · ${failure}` : "Never written"}</span>}
                </span>
              </span>
              {written && <span className="story-meta">
                <span>{count(pictures.total, "part")} · {count(words.length, "word")}</span>
                {pictures.drawn < pictures.total
                  && <span className="warn">{pictures.drawn} of {pictures.total} drawn</span>}
              </span>}
            </button>
            <div className="loop-swipe">
              <button className="loop-delete" onClick={remove}>Delete</button>
            </div>
          </div>
          {menu?.id === story.id && <div
            className="menu open loop-menu" role="menu"
            style={{ "--menu-x": `${menu.x}px`, "--menu-y": `${menu.y}px` } as CSSProperties}
          >
            <button role="menuitem" className="danger" onClick={remove}>Delete this story</button>
          </div>}
        </div>;
      })}
    </div>
  </section>;
}
