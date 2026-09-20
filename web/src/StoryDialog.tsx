/**
 * Make a story: how many words, what kind of story, and what it should look like.
 *
 * **The words come from what you are looking at**, exactly as for a loop: the scope on screen —
 * this language, this topic, this search — is sampled here and posted as a list of ids, and the
 * server never re-derives it. Which is what makes choosing words by hand later the same route with
 * a different list, and no server change at all.
 *
 * The kinds and the styles are the server's tracked config, read from `GET /stories/types` and
 * never copied into this file: a kind added to `config/story-types.yaml` appears here with nothing
 * changing on this side.
 *
 * The default is **three words**, not twelve. A story has to weave every word it is given into
 * twenty sentences, and the prose buckles long before a loop's dozen would.
 */

import { useEffect, useState } from "react";
import { AcervoApiError, backendSession, type StoryTypes } from "./api";
import type { VocabularyGraph } from "./domain";
import { BookIcon } from "./icons";
import { languageOf } from "./languages";
import { sampleLexemeIds, storyCandidates, type ListQuery } from "./selectors";

const DEFAULT_WORDS = 3;

export default function StoryDialog({ graph, query, deviceId, onClose, onMade, onNotify }: {
  graph: VocabularyGraph;
  /** The scope on screen, exactly as the list is drawing it. */
  query: ListQuery;
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
  const eligible = storyCandidates(graph, query).length;
  const most = Math.min(offered?.maxWords ?? 8, Math.max(1, eligible));
  const [words, setWords] = useState(Math.min(DEFAULT_WORDS, Math.max(1, eligible)));

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
        lexemeIds: sampleLexemeIds(graph, query, Math.min(words, eligible), Date.now()),
        ...(kind === "auto" ? {} : { typeId: kind }),
        ...(style === "auto" ? {} : { styleId: style })
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

        <p className="config-help">
          Every word you choose has to earn its place in the story, so a few work better than many.
          All the pictures are drawn in one style, so the story looks like one thing.
        </p>

        {trouble && <p className="config-help warn">{trouble}</p>}

        <div className="loop-actions">
          <button className="tb-btn" onClick={onClose}>Cancel</button>
          <button
            className="tb-btn primary"
            disabled={asking || eligible === 0 || Boolean(trouble) || !offered}
            onClick={() => void make()}
          >{asking ? "Asking…" : "Make the story"}</button>
        </div>
      </div>
    </section>
  </div>;
}
