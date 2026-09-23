/**
 * The Loops surface: the loops you have, and the one you are playing.
 *
 * A player is a place you go to, so it takes the column rather than sitting over the list — and it
 * takes the whole height, so the controls are a footer that cannot scroll away.
 *
 * **One back arrow, and its meaning follows the level**: on an open loop it returns to the loops,
 * and on the loops it returns to your words. Modelled on the article's `.art-bar`, and present at
 * every width for the reason that one is — a surface that replaces the list has to carry the way
 * back out of itself, and a phone has no rail to fall back on.
 *
 * A loop's state is derived and there is no status column: an empty `audioRef` is the whole of what
 * "not rendered yet" means, and the job says how far along it is. So a loop whose render failed
 * simply reads as one that was asked for and not made, and Try again queues another.
 */

import { useEffect, useState, useSyncExternalStore, type CSSProperties } from "react";
import type { LoopMusic } from "./api";
import { jobFor, jobStream, isOpen as jobIsOpen } from "./jobs";
import { stripOf } from "./ProgressStrip";
import type { Loop, VocabularyGraph } from "./domain";
import { BackIcon, HourglassIcon, PauseIcon, PlayIcon, PlusIcon } from "./icons";
import * as player from "./loops";
import LoopPlayer from "./LoopPlayer";
import { loopIsReady, loopItemsOf, loopTitle, loopsIn } from "./selectors";

function clock(seconds: number | null): string {
  const whole = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export default function LoopView({ graph, language, onMake, onClose, onDelete, onChangeMusic, onToggleKeep }: {
  graph: VocabularyGraph;
  language: string;
  onMake(): void;
  /** Back to the words. The loop keeps playing; the bar and the chip are what it plays behind. */
  onClose(): void;
  /** Online-only and loud when it fails, like every other write. */
  onDelete(loopId: string): void;
  onChangeMusic(loopId: string, music: LoopMusic): void;
  /** Keep this loop's music as a favourite, or stop keeping it. */
  onToggleKeep(loop: Loop): void;
}) {
  const playback = player.usePlayback();
  const live = useSyncExternalStore(jobStream.subscribe, jobStream.getStatus);
  const loops = loopsIn(graph, language);
  const [openId, setOpenId] = useState<string | null>(playback.loopId);
  const open = loops.find((loop) => loop.id === openId) ?? null;
  /* Which row has been right-clicked, and where within it, so the menu opens under the pointer. A
     pointer has a gesture for this and a finger does not, so the finger gets the row itself: the
     list below is two snap points wide and Delete is the second. */
  const [menu, setMenu] = useState<{ id: string; x: number; y: number } | null>(null);
  const menuId = menu?.id ?? null;

  useEffect(() => {
    if (!menuId) return;
    /* A press inside the menu is left alone: it is the first half of the click that chooses Delete,
       and closing on it unmounts the button before the click can arrive. */
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

  /* The queue the player moves through when Next, or Play the next one, asks for another. Kept in
     the player rather than here, so leaving this surface does not end it: a loop goes on playing
     while you read a word, which is most of the point of having one. */
  useEffect(() => {
    player.setQueue(loops.map((loop) => ({ loop, items: loopItemsOf(graph, loop.id) })));
  }, [graph, loops.map((loop) => loop.id).join()]);

  if (open) {
    const items = loopItemsOf(graph, open.id);
    return <section className="loops">
      <div className="loops-back">
        <button className="icon-btn" onClick={() => setOpenId(null)} aria-label="Back to the loops"><BackIcon /></button>
        <span className="label">Loops</span>
        <span className="spacer" />
      </div>
      <LoopPlayer
        loop={open} items={items} graph={graph}
        onChangeMusic={(music) => onChangeMusic(open.id, music)}
        onToggleKeep={() => onToggleKeep(open)}
      />
    </section>;
  }

  return <section className="loops">
    <div className="loops-back">
      <button className="icon-btn" onClick={onClose} aria-label="Back to the list"><BackIcon /></button>
      <span className="label">Your words</span>
      <span className="spacer" />
    </div>

    <div className="loops-head">
      <h2>Loops</h2>
      <span className="spacer" />
      <button className="tb-btn primary" onClick={onMake}><PlusIcon /><span>Make a loop</span></button>
    </div>

    {loops.length === 0 && <p className="empty">
      No loops yet. A loop takes a handful of your words and sets them to music, so they are learned
      while you are doing something else.
    </p>}

    <div className="loops-list">
      {loops.map((loop) => {
        const items = loopItemsOf(graph, loop.id);
        const ready = loopIsReady(loop);
        const job = jobFor(live, "loop", loop.id);
        const making = jobIsOpen(job);
        const failure = job?.state === "failed"
          ? job.message || stripOf(job)?.failure || job.error || ""
          : "";
        const here = playback.loopId === loop.id && playback.playing;
        const remove = () => { setMenu(null); onDelete(loop.id); };
        /* The shell is the scroller, and Delete is its second snap point. The row itself is not
           `disabled` even when there is nothing to play: a loop that was never made is the one you
           most want rid of, and a disabled button answers no gesture at all. */
        return <div
          key={loop.id} className="loop-item"
          onContextMenu={(event) => {
            event.preventDefault();
            const box = event.currentTarget.getBoundingClientRect();
            setMenu({ id: loop.id, x: event.clientX - box.left, y: event.clientY - box.top });
          }}
        >
          <div className="loop-shell">
            <button
              className={`loop-row${playback.loopId === loop.id ? " on" : ""}`}
              aria-disabled={!ready}
              onClick={() => {
                if (!ready) return;
                setOpenId(loop.id);
                if (!here) void player.play(loop, items);
              }}
            >
              <span className={`loop-go${ready ? "" : " pending"}`}>
                {ready ? (here ? <PauseIcon /> : <PlayIcon />) : <HourglassIcon />}
              </span>
              <span className="loop-main">
                <span className="loop-title">{loopTitle(graph, loop)}</span>
                <span className="loop-sub">
                  {ready && making
                    /* New music being made for a loop that already plays: it goes on playing the
                       old track until this finishes, so the row says both. */
                    ? <span className="doing">New music · {stripOf(job)?.phases.map((phase) => phase.text).join(" · ") || "queued"}</span>
                    : ready
                    ? `${items.length} words · ${clock(loop.durationSeconds)}`
                    : making
                      /* What it is *doing*, in the generator's own words — this is a four-minute
                         operation and "being made" says nothing you could not already see. */
                      ? <span className="doing">{stripOf(job)?.phases.map((phase) => phase.text).join(" · ") || "Being made…"}</span>
                      /* Why, not only that. The reason is on the job the whole time; saying "never
                         made" and nothing else is what left a failure with no next step. */
                      : <span className="warn">{failure ? `Never made · ${failure}` : "Never made"}</span>}
                </span>
              </span>
            </button>
            <div className="loop-swipe">
              <button className="loop-delete" onClick={remove}>Delete</button>
            </div>
          </div>
          {menu?.id === loop.id && <div
            className="menu open loop-menu" role="menu"
            style={{ "--menu-x": `${menu.x}px`, "--menu-y": `${menu.y}px` } as CSSProperties}
          >
            <button role="menuitem" className="danger" onClick={remove}>Delete this loop</button>
          </div>}
        </div>;
      })}
    </div>

    {playback.failed && <p className="config-help warn">{playback.failed}</p>}
  </section>;
}
