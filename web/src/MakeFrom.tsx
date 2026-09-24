/**
 * Where a make dialog's words come from: the selection, or a random draw from what is on screen.
 *
 * The switch is drawn only when there is a selection. Opened from the selection bar it starts on the
 * selection; opened from a surface's own Make button it starts on the random draw, which is what that
 * button always meant. Shared by `LoopDialog` and `StoryDialog`; `sourceBlock` in the prototype.
 *
 * **What is undimmed is exactly what is sent.** The selection is drawn as chips in the order it was
 * chosen. A word the kind cannot use, or one past the kind's limit, is struck through, and a sentence
 * names it and says why, because a strike-through alone explains nothing on a device with no hover.
 */

import type { ChosenWord } from "./selectors";

export type WordSource = "selection" | "scope";

export function wordsCount(count: number): string {
  return `${count} word${count === 1 ? "" : "s"}`;
}

export function SourceSwitch({ source, onSource, selected, where }: {
  source: WordSource;
  onSource(source: WordSource): void;
  /** How many words are selected, whatever the kind can use of them. */
  selected: number;
  /** The scope the random draw is from, as the dialog names it. */
  where: string;
}) {
  return <div className="config-field">
    <span>Words</span>
    <div className="seg make-source" role="radiogroup" aria-label="Which words">
      <button type="button" role="radio" aria-checked={source === "selection"}
        className={source === "selection" ? "on" : ""} onClick={() => onSource("selection")}
      >Your selection · {selected}</button>
      <button type="button" role="radio" aria-checked={source === "scope"}
        className={source === "scope" ? "on" : ""} onClick={() => onSource("scope")}
      >Random from {where}</button>
    </div>
  </div>;
}

export function ChosenWords({ words, language, noun }: {
  words: ChosenWord[];
  language: string;
  /** "loop" or "story", for the sentence under the chips. */
  noun: string;
}) {
  const used = words.filter((word) => !word.skip).length;
  const reasons = [...new Set(words.filter((word) => word.skip).map((word) => word.skip))];
  return <div>
    <div className="make-words">
      {words.map((word) => <span
        key={word.id} className={`make-chip${word.skip ? " skip" : ""}`} lang={language}
        title={word.skip ? `Left out: ${word.skip}` : undefined}
      >
        <span aria-hidden="true">{word.emoji || "📄"}</span>{word.headword}
      </span>)}
    </div>
    {reasons.length > 0 && <p className="config-help make-skip">
      {reasons.map((why) => <span key={why}>
        Left out, {why}: {words.filter((word) => word.skip === why).map((word, index) => <span key={word.id}>
          {index > 0 && ", "}<i lang={language}>{word.headword}</i>
        </span>)}.{" "}
      </span>)}
      {used ? `The ${noun} is made from the other ${used}.` : `There is nothing left to make a ${noun} from.`}
    </p>}
  </div>;
}
