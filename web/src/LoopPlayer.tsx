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
 *
 * **The music is changed from its own name.** The style under the transport is a button: it opens
 * `MusicMenu` — new music in this style, a kept favourite, or another style — and choosing one asks
 * the server to render the loop again. The old track goes on playing until the new one lands, and
 * then the player starts it from the beginning. The star beside the name keeps this music as a
 * favourite, so it is offered the next time a loop is made; nothing asks you to keep the music you
 * are replacing, because replacing it is usually the reason you did not.
 */

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { LoopMusic } from "./api";
import type { Loop, LoopItem, VocabularyGraph } from "./domain";
import { setLoopAutoplay, setLoopRepeat, useLoopAutoplay, useLoopRepeat } from "./editorPreferences";
import { ContinueIcon, DownIcon, NextIcon, PauseIcon, PlayIcon, PreviousIcon, RepeatIcon, StarIcon } from "./icons";
import { isOpen as jobIsOpen, jobFor, jobStream } from "./jobs";
import { MusicMenu, useLoopSchema } from "./LoopMusic";
import * as player from "./loops";
import { stripOf } from "./ProgressStrip";
import { bedOfLoop, favouriteBeds, loopIsReady, loopMomentAt, styleLabel } from "./selectors";

function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export default function LoopPlayer({ loop, items, graph, onChangeMusic, onToggleKeep }: {
  loop: Loop;
  items: LoopItem[];
  graph: VocabularyGraph;
  /** Online-only and loud when it fails, like every other write. */
  onChangeMusic(music: LoopMusic): void;
  onToggleKeep(): void;
}) {
  const playback = player.usePlayback();
  const repeat = useLoopRepeat();
  const autoplay = useLoopAutoplay();
  const lyric = useRef<HTMLDivElement>(null);
  const here = playback.loopId === loop.id;
  const at = here ? playback.at : 0;
  const total = (here && playback.duration) || loop.durationSeconds || 0;
  const moment = loopMomentAt(items, at);
  const { schema } = useLoopSchema();
  const live = useSyncExternalStore(jobStream.subscribe, jobStream.getStatus);
  const job = jobFor(live, "loop", loop.id);
  const making = jobIsOpen(job);
  const kept = Boolean(bedOfLoop(graph, loop));
  const [choosing, setChoosing] = useState(false);
  const heard = useRef(loop.audioRef);

  /* A new track has landed for this loop. The old one is what the element holds, so it is stopped,
     its bytes forgotten — nothing names them any more — and the new one started from the top if the
     old one was playing. Its words are timed afresh, so "from where you were" would be a guess. */
  useEffect(() => {
    const previous = heard.current;
    heard.current = loop.audioRef;
    if (!previous || previous === loop.audioRef) return;
    const wasPlaying = player.nowPlaying()?.loop.id === loop.id && player.playback().playing;
    if (player.nowPlaying()?.loop.id === loop.id) player.stop();
    void player.forget(previous);
    if (wasPlaying) void player.play(loop, items);
  }, [loop.audioRef]);

  useEffect(() => {
    if (!choosing) return;
    const away = (event: PointerEvent) => {
      if (event.target instanceof Element && event.target.closest(".music-menu, .bed-name")) return;
      setChoosing(false);
    };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setChoosing(false); };
    window.addEventListener("pointerdown", away);
    window.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener("pointerdown", away);
      window.removeEventListener("keydown", escape);
    };
  }, [choosing]);

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

      <div className="player-bed">
        {/* What is happening to the music, when something is: a track being fetched, new music being
            made — in the generator's own words — or why the last attempt did not work. */}
        {playback.failed
          ? <span className="bed-status warn">{playback.failed}</span>
          : making
            ? <span className="bed-status label">Making new music · {stripOf(job)?.phases.map((phase) => phase.text).join(" · ") || "queued"}</span>
            : job?.state === "failed" && loopIsReady(loop)
              ? <span className="bed-status warn">New music could not be made · {job.message || job.error || "no reason given"}</span>
              : playback.loading && here
                ? <span className="bed-status label">Fetching the track…</span>
                : null}
        <span className="bed-line">
          {/* The bed's own name, as the generator's catalogue writes it. Whether this deployment has
              the sample pack is a question about the server rather than about one loop, and it is
              answered where it can be acted on: Settings ▸ Loops, and the make dialog. */}
          <button
            className="bed-name label" aria-haspopup="menu" aria-expanded={choosing}
            disabled={!loopIsReady(loop) || making}
            title="Choose other music for this loop"
            onClick={() => setChoosing(!choosing)}
          >{styleLabel(schema?.families, loop.styleId)}<DownIcon /></button>
          <button
            className={`bed-star${kept ? " on" : ""}`} aria-pressed={kept}
            disabled={!loop.styleId}
            aria-label={kept ? "No longer keep this music" : "Keep this music as a favourite"}
            title={kept ? "Kept as a favourite" : "Keep this music as a favourite"}
            onClick={onToggleKeep}
          ><StarIcon filled={kept} /></button>
          <span className="label">· {items.length} words</span>
          {choosing && <MusicMenu
            graph={graph} loop={loop} families={schema?.families ?? []}
            favourites={favouriteBeds(graph)}
            onChoose={(music) => { setChoosing(false); onChangeMusic(music); }}
          />}
        </span>
      </div>
    </div>
  </div>;
}
