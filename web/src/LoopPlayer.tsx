/**
 * One loop, playing: its words above and its controls below.
 *
 * **It is an ordinary music player.** A seekable line with the elapsed and total time, the three
 * transport buttons everyone already knows, and two switches — play it again, and go on to the next
 * one. Where the artwork or the lyrics would be are the words themselves.
 *
 * **The one rule that is not a music player's: a translation is never drawn before it has been
 * spoken.** A word not yet reached shows its source and, where its translation will be, a short bar
 * of the same width for every word — fixed, so it leaks nothing about the length of the answer;
 * present, so the line does not jump when the answer arrives; visible, so you know one is coming.
 * Seeing "the raft" while you are still being asked what `la balsa` means is not a lesson, it is a
 * caption.
 *
 * Everything drawn here is a function of the clock, and nothing about the reveal is remembered —
 * which is what makes dragging the line backwards put an answer away again rather than leaving it
 * up because it was once shown. `loopMomentAt` is that function and it lives in `selectors.ts`,
 * so the whole rule is tested without an audio element.
 *
 * **The controls do not scroll.** This surface owns its height: the words scroll inside it and the
 * controls are a footer that cannot move. A player that drifts as you scroll is one you have to
 * chase to press pause.
 */

import { useEffect, useRef } from "react";
import type { Loop, LoopItem } from "./domain";
import { setLoopAutoplay, setLoopRepeat, useLoopAutoplay, useLoopRepeat } from "./editorPreferences";
import { ContinueIcon, NextIcon, PauseIcon, PlayIcon, PreviousIcon, RepeatIcon } from "./icons";
import * as player from "./loops";
import { loopMomentAt } from "./selectors";

function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export default function LoopPlayer({ loop, items }: { loop: Loop; items: LoopItem[] }) {
  const playback = player.usePlayback();
  const repeat = useLoopRepeat();
  const autoplay = useLoopAutoplay();
  const lyric = useRef<HTMLDivElement>(null);
  const here = playback.loopId === loop.id;
  const at = here ? playback.at : 0;
  const total = (here && playback.duration) || loop.durationSeconds || 0;
  const moment = loopMomentAt(items, at);

  /* Keep the word being taught in the middle of the column. `scrollIntoView` rather than arithmetic
     on `offsetTop`, which is measured from the offset parent and not from the scroller. */
  useEffect(() => {
    if (moment.index < 0) return;
    lyric.current?.querySelector(`[data-word="${moment.index}"]`)
      ?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [moment.index]);

  const scrub = (event: React.PointerEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const where = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width));
    player.seek(where * total);
  };

  const toggle = () => {
    if (here && playback.playing) player.pause();
    else void player.play(loop, items, here ? { at: playback.at } : undefined);
  };

  return <div className="loop-play">
    <div className="lyric" ref={lyric}>
      {items.map((item, index) => {
        const current = index === moment.index;
        const said = current && moment.revealed;
        return <button
          key={item.id} data-word={index}
          className={`lyric-row${current ? " now" : ""}${index < moment.index ? " past" : ""}`}
          onClick={() => void player.play(loop, items, { at: item.startSeconds })}
        >
          {/* The line last spoken is the one at full strength; the other steps back. No movement
              and no weight change, so nothing on this screen ever reflows — which is the same rule
              the article's change marks live by, and the reason it is calm enough to leave running. */}
          <span className={`lyric-source${current && moment.sounding === "source" ? " saying" : ""}`}>
            {item.sourceText}
          </span>
          <span className={`lyric-target${current && moment.sounding === "target" ? " saying" : ""}`}>
            {said || index < moment.index
              ? <span className="lyric-said">{item.targetText}</span>
              : <span className="lyric-held" aria-label="Not said yet" />}
          </span>
        </button>;
      })}
    </div>

    <div className="player">
      <div
        className="seek" role="slider" tabIndex={0}
        aria-label="Where you are in the loop"
        aria-valuemin={0} aria-valuemax={Math.round(total)} aria-valuenow={Math.round(at)}
        onPointerDown={(event) => { event.currentTarget.setPointerCapture(event.pointerId); scrub(event); }}
        onPointerMove={(event) => { if (event.currentTarget.hasPointerCapture(event.pointerId)) scrub(event); }}
        onKeyDown={(event) => {
          if (event.key === "ArrowRight") player.seek(at + 5);
          else if (event.key === "ArrowLeft") player.seek(at - 5);
        }}
      >
        <span className="seek-track" />
        {/* Where each word begins. A loop is twelve words, not an opaque four minutes, so the line
            says where they are and dragging lands on one rather than into the middle of a syllable. */}
        {total > 0 && items.map((item) => <span
          key={item.id} className="seek-tick" style={{ left: `${(item.startSeconds / total) * 100}%` }}
        />)}
        <span className="seek-fill" style={{ width: `${total ? (at / total) * 100 : 0}%` }} />
        <span className="seek-knob" style={{ left: `${total ? (at / total) * 100 : 0}%` }} />
      </div>
      <div className="seek-times"><span>{clock(at)}</span><span>{clock(total)}</span></div>

      <div className="transport">
        <button
          className={`switch${repeat ? " on" : ""}`} onClick={() => setLoopRepeat(!repeat)}
          aria-pressed={repeat} title="Play this loop again when it ends"
          aria-label="Play this loop again when it ends"
        ><RepeatIcon /></button>
        <button onClick={() => player.stepWord(-1)} aria-label="Previous word"><PreviousIcon /></button>
        <button
          className="big" onClick={toggle} disabled={playback.loading}
          aria-label={here && playback.playing ? "Pause" : "Play"}
        >{here && playback.playing ? <PauseIcon /> : <PlayIcon />}</button>
        <button onClick={() => player.stepWord(1)} aria-label="Next word"><NextIcon /></button>
        <button
          className={`switch${autoplay ? " on" : ""}`} onClick={() => setLoopAutoplay(!autoplay)}
          aria-pressed={autoplay} title="Go on to the next loop when this one ends"
          aria-label="Go on to the next loop when this one ends"
        ><ContinueIcon /></button>
      </div>

      <div className="player-bed label">
        {playback.failed
          ? <span className="warn">{playback.failed}</span>
          : playback.loading && here
            ? "Fetching the track…"
            /* The bed's own name, as the generator's catalogue writes it. Whether this deployment
               has the sample pack is a question about the server rather than about one loop, and it
               is answered where it can be acted on: Settings ▸ Loops, and the make dialog. */
            : `${(loop.styleId ?? "no bed").replace(/-/g, " ")} · ${items.length} words`}
      </div>
    </div>
  </div>;
}
