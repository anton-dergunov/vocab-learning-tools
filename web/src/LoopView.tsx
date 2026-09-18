/**
 * The Loops surface: the loops you have, and the one you are playing.
 *
 * A player is a place you go to, so it takes the column rather than sitting over the list — and it
 * takes the whole height, so the controls are a footer that cannot scroll away. The topic rail is
 * hidden while this is open: a topic files a *word*, and nothing here is filed.
 *
 * A loop's state is derived and there is no status column: an empty `audioRef` is the whole of what
 * "not rendered yet" means, and the job says how far along it is. So a loop whose render failed
 * simply reads as one that was asked for and not made, and Try again queues another.
 */

import { useEffect, useState, useSyncExternalStore } from "react";
import { jobFor, jobStream, isOpen as jobIsOpen } from "./jobs";
import type { VocabularyGraph } from "./domain";
import { BackIcon, HourglassIcon, PauseIcon, PlayIcon, PlusIcon } from "./icons";
import * as player from "./loops";
import LoopPlayer from "./LoopPlayer";
import { loopIsReady, loopItemsOf, loopTitle, loopsIn } from "./selectors";

function clock(seconds: number | null): string {
  const whole = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export default function LoopView({ graph, language, onMake }: {
  graph: VocabularyGraph;
  language: string;
  onMake(): void;
}) {
  const playback = player.usePlayback();
  const live = useSyncExternalStore(jobStream.subscribe, jobStream.getStatus);
  const loops = loopsIn(graph, language);
  const [openId, setOpenId] = useState<string | null>(playback.loopId);
  const open = loops.find((loop) => loop.id === openId) ?? null;

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
        <span className="label">{loopTitle(graph, open, 2)}</span>
      </div>
      <LoopPlayer loop={open} items={items} />
    </section>;
  }

  return <section className="loops">
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
        const here = playback.loopId === loop.id && playback.playing;
        return <button
          key={loop.id} className={`loop-row${playback.loopId === loop.id ? " on" : ""}`}
          disabled={!ready}
          onClick={() => {
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
              {ready
                ? `${items.length} words · ${clock(loop.durationSeconds)}`
                : making
                  ? <span className="doing">Being made…</span>
                  : <span className="warn">Never made · Try again in Settings ▸ Activity</span>}
            </span>
          </span>
        </button>;
      })}
    </div>

    {playback.failed && <p className="config-help warn">{playback.failed}</p>}
  </section>;
}
