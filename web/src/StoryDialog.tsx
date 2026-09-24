/**
 * Make a story: how many words, what kind of story, and what it should look like.
 *
 * **The words are the selection, or a draw from what you are looking at**, exactly as for a loop
 * (`MakeFrom.tsx`): either way a list of ids the server never re-derives. The draw is from the
 * words a *story* can use, which is most of them — it used to be from the ones a loop can, so a
 * scope with no single terms written down sent a story no words at all.
 *
 * The kinds and the styles are the server's tracked config, read from `GET /stories/types` and
 * never copied into this file: a kind added to `config/story-types.yaml` appears here with nothing
 * changing on this side.
 *
 * The default is **three words**, not twelve. A story has to weave every word it is given into
 * twenty sentences, and the prose buckles long before a loop's dozen would.
 *
 * The guidance box is the owner's own words to the writer, kept on the story so Try again writes the
 * story that was asked for. It is sent only when something is in it.
 */

import { useEffect, useState } from "react";
import { AcervoApiError, backendSession, type StoryTypes } from "./api";
import type { VocabularyGraph } from "./domain";
import { BookIcon } from "./icons";
import { languageOf } from "./languages";
import { ChosenWords, SourceSwitch, wordsCount, type WordSource } from "./MakeFrom";
import {
  chosenFor, sampleLexemeIds, storyCandidates, storyEligible, type ListQuery, type SelectedWord
} from "./selectors";

const DEFAULT_WORDS = 3;
/** The server's bound (`GUIDANCE_LIMIT`), so the box stops where the route would refuse. */
const GUIDANCE_LIMIT = 1000;

export default function StoryDialog({ graph, query, selection = [], from = "scope", deviceId, onClose, onMade, onNotify }: {
  graph: VocabularyGraph;
  /** The scope on screen, exactly as the list is drawing it. */
  query: ListQuery;
  /** The selected words in this language, in the order they were chosen. */
  selection?: SelectedWord[];
  /** Where the words start from: the selection bar opens this on the selection. */
  from?: WordSource;
  deviceId: string;
  onClose(): void;
  onMade(storyId: string): void;
  onNotify(message: string): void;
}) {
  const [offered, setOffered] = useState<StoryTypes | null>(null);
  const [trouble, setTrouble] = useState<string | null>(null);
  const [kind, setKind] = useState("auto");
  const [style, setStyle] = useState("auto");
  const [asking, setAsking] = useState(false);
  const [guidance, setGuidance] = useState("");
  const eligible = storyCandidates(graph, query).length;
  const most = Math.min(offered?.maxWords ?? 8, Math.max(1, eligible));
  const [words, setWords] = useState(Math.min(DEFAULT_WORDS, Math.max(1, eligible)));
  const [source, setSource] = useState<WordSource>(selection.length && from === "selection" ? "selection" : "scope");
  const fromSelection = source === "selection" && selection.length > 0;
  const chosen = chosenFor(graph, selection, {
    eligible: storyEligible, why: "nothing yet says what it means", max: offered?.maxWords ?? 8, noun: "story"
  });
  const usable = chosen.filter((word) => !word.skip).map((word) => word.id);

  useEffect(() => {
    void backendSession.storyTypes()
      .then(setOffered)
      .catch((error: unknown) => setTrouble(error instanceof AcervoApiError
        ? error.message
        : "The kinds of story could not be read."));
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const make = async () => {
    setAsking(true);
    try {
      const answer = await backendSession.makeStory({
        deviceId, language: query.language,
        lexemeIds: fromSelection ? usable
          : sampleLexemeIds(graph, query, Math.min(words, eligible), Date.now(), storyCandidates),
        ...(kind === "auto" ? {} : { typeId: kind }),
        ...(style === "auto" ? {} : { styleId: style }),
        ...(guidance.trim() ? { guidance: guidance.trim() } : {})
      });
      onMade(answer.story.id);
      onClose();
    } catch (error) {
      setAsking(false);
      onNotify(error instanceof AcervoApiError ? error.message : "That story could not be asked for.");
    }
  };

  const where = query.topic === "all" ? languageOf(query.language).name
    : query.topic === "inbox" ? `${languageOf(query.language).name} · Inbox`
      : `${languageOf(query.language).name} · ${graph.topics.find((topic) => topic.id === query.topic)?.name ?? "this topic"}`;

  return <div
    className="modal-backdrop" role="presentation"
    onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
  >
    <section className="settings loop-dialog" role="dialog" aria-modal="true" aria-labelledby="story-dialog-title">
      <header>
        <h2 id="story-dialog-title">Make a story</h2>
        <button className="close" onClick={onClose} aria-label="Close">×</button>
      </header>
      <div className="settings-body">
        <p className="config-help">
          A few of your words, told back to you as a short illustrated story you can read in a
          couple of minutes.
        </p>
        {selection.length > 0 && <SourceSwitch source={source} onSource={setSource} selected={selection.length} where={where} />}
        {fromSelection ? <ChosenWords words={chosen} language={query.language} noun="story" /> : <>
          <div className="loop-scope">
            <BookIcon />
            <span><strong>{where}</strong> · {eligible} {eligible === 1 ? "word can" : "words can"} be in a story</span>
          </div>

          <label className="config-field">
            <span>How many words</span>
            <span className="loop-count">
              <input
                type="range" min={1} max={most} value={Math.min(words, most)}
                disabled={eligible === 0}
                onChange={(event) => setWords(Number(event.target.value))}
              />
              <output>{Math.min(words, most)} {Math.min(words, most) === 1 ? "word" : "words"}</output>
            </span>
          </label>
        </>}

        <label className="config-field">
          <span>Kind of story</span>
          <select value={kind} onChange={(event) => setKind(event.target.value)}>
            <option value="auto">Surprise me</option>
            {(offered?.types ?? []).map((one) => (
              <option key={one.id} value={one.id}>{one.emoji ? `${one.emoji} ` : ""}{one.label}</option>
            ))}
          </select>
        </label>

        <label className="config-field">
          <span>Pictures</span>
          <select value={style} onChange={(event) => setStyle(event.target.value)}>
            {/* "To suit the story" rather than "Surprise me": the server picks from the styles
                this kind of story suggests, which is a judgement rather than a dice roll. */}
            <option value="auto">To suit the story</option>
            {(offered?.styles ?? []).map((one) => (
              <option key={one.id} value={one.id}>{one.label}</option>
            ))}
          </select>
        </label>

        <label className="config-field">
          <span>Anything else? <em>(optional)</em></span>
          <textarea
            value={guidance} maxLength={GUIDANCE_LIMIT} rows={3}
            placeholder="Set it on a night train, tell it from the dog’s side, keep it gentle…"
            onChange={(event) => setGuidance(event.target.value)}
          />
        </label>

        <p className="config-help">
          Every word you choose has to earn its place in the story, so a few work better than many.
          All the pictures are drawn in one style, so the story looks like one thing.
        </p>

        {trouble && <p className="config-help warn">{trouble}</p>}

        <div className="loop-actions">
          <button className="tb-btn" onClick={onClose}>Cancel</button>
          <button
            className="tb-btn primary"
            disabled={asking || (fromSelection ? usable.length === 0 : eligible === 0) || Boolean(trouble) || !offered}
            onClick={() => void make()}
          >{asking ? "Asking…" : fromSelection ? `Make the story from ${wordsCount(usable.length)}` : "Make the story"}</button>
        </div>
      </div>
    </section>
  </div>;
}
