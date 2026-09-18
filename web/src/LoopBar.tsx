/**
 * The way in to Loops, and what is playing — in two shapes, because the two widths want different
 * things.
 *
 * **On a phone or a tablet it is a bar at the foot of the window**, which is where a player belongs
 * on a device held in one hand. It is drawn over the list and nowhere else: the article column
 * already carries the view segments, the delete control, the progress strip and the ask dock, and a
 * second dock there is prohibited (design §2.13). There is deliberately no mini-player over an
 * article.
 *
 * **On a desktop it is a button in the top bar**, beside Add, which widens into a chip while
 * something is playing. A bar across the foot of a wide window is a lot of furniture for one line of
 * text, and the top bar is already where everything you can reach from anywhere lives.
 *
 * Both are the same component in two skins, so what they say can never disagree.
 */

import type { VocabularyGraph } from "./domain";
import { NoteIcon, PauseIcon, PlayIcon, PlusIcon } from "./icons";
import * as player from "./loops";
import { loopItemsOf, loopMomentAt, loopsIn, loopTitle } from "./selectors";

function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export default function LoopBar({ graph, language, chip, onOpen, onMake }: {
  graph: VocabularyGraph;
  language: string;
  /** True in the top bar, false at the foot of the window. */
  chip: boolean;
  onOpen(): void;
  onMake(): void;
}) {
  const playback = player.usePlayback();
  const loops = loopsIn(graph, language);
  const loop = playback.loopId ? loops.find((one) => one.id === playback.loopId) ?? null : null;
  const items = loop ? loopItemsOf(graph, loop.id) : [];
  // The word being taught, so the bar says what you are hearing rather than which file is open.
  const word = loop ? loopMomentAt(items, playback.at).item?.sourceText : null;
  const fraction = loop && playback.duration ? playback.at / playback.duration : 0;

  const toggle = () => {
    if (!loop) return;
    if (playback.playing) player.pause();
    else void player.play(loop, items, { at: playback.at });
  };

  if (chip) {
    if (!loop) return <button className="tb-btn loop-chip" onClick={onOpen} title="Loops" aria-label="Loops">
      <NoteIcon />
      {loops.length > 0 && <span className="wide-only">{loops.length}</span>}
    </button>;
    return <span className="tb-btn loop-chip playing">
      <button className="loop-chip-play" onClick={toggle} aria-label={playback.playing ? "Pause" : "Play"}>
        {playback.playing ? <PauseIcon /> : <PlayIcon />}
      </button>
      <button className="loop-chip-what" onClick={onOpen}>
        <span className="loop-chip-word">{word ?? loopTitle(graph, loop, 1)}</span>
        <span className="loop-chip-at">{clock(playback.at)}</span>
      </button>
    </span>;
  }

  if (!loop) return <div className="loopbar">
    <span className="loopbar-note"><NoteIcon /></span>
    <button className="loopbar-main" onClick={onOpen}>
      <span className="loopbar-title">Loops</span>
      <span className="loopbar-sub">{loops.length} · {language.toUpperCase()}</span>
    </button>
    <button className="tb-btn loopbar-make" onClick={onMake}>
      <PlusIcon /><span className="wide-only">Make a loop</span>
    </button>
  </div>;

  return <div className="loopbar">
    {/* The hairline sits on the bar's own top rule, so a bar that is playing reads as a progress
        line rather than as a bar with a widget in it. */}
    <span className="loopbar-line" style={{ width: `${Math.max(0, Math.min(1, fraction)) * 100}%` }} />
    <button className="loopbar-play" onClick={toggle} aria-label={playback.playing ? "Pause" : "Play"}>
      {playback.playing ? <PauseIcon /> : <PlayIcon />}
    </button>
    <button className="loopbar-main" onClick={onOpen}>
      <span className="loopbar-title">{word ?? loopTitle(graph, loop, 2)}</span>
      <span className="loopbar-sub">{clock(playback.at)} / {clock(playback.duration)}</span>
    </button>
  </div>;
}
