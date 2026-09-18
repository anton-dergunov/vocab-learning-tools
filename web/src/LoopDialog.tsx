/**
 * Make a loop: how many words, and what it should sound like.
 *
 * **The words come from what you are looking at.** The scope on screen — this language, this topic,
 * this search — is sampled here and posted as a list of ids; the server never re-derives it. Which
 * is what makes choosing words by hand later the same route with a different list, and no server
 * change at all.
 *
 * The families are the generator's own catalogue, read from `GET /loops/schema` and never copied
 * into Acervo: a family added in a later version of it appears here with nothing changing on this
 * side.
 *
 * **Without the sample pack this refuses rather than warns.** Fifteen of the generator's sixteen bed
 * families name instruments loaded from its catalogue, so a pack-less render dies partway through on
 * a missing sample — after minutes of work, with a message about a file nobody has heard of. The
 * server refuses the same request for the same reason; this is only the earlier, kinder half of it.
 *
 * A word with no single term to say is not eligible — a loop has to choose one meaning — and the
 * count says how many there are rather than letting you ask for more than exist.
 */

import { useEffect, useState } from "react";
import { AcervoApiError, backendSession, type LoopSchema } from "./api";
import type { VocabularyGraph } from "./domain";
import { BookIcon } from "./icons";
import { languageOf } from "./languages";
import { loopCandidates, sampleLexemeIds, type ListQuery } from "./selectors";

const DEFAULT_WORDS = 12;

export default function LoopDialog({ graph, query, deviceId, onClose, onMade, onNotify }: {
  graph: VocabularyGraph;
  /** The scope on screen, exactly as the list is drawing it. */
  query: ListQuery;
  deviceId: string;
  onClose(): void;
  onMade(loopId: string): void;
  onNotify(message: string): void;
}) {
  const [schema, setSchema] = useState<LoopSchema | null>(null);
  const [trouble, setTrouble] = useState<string | null>(null);
  const [family, setFamily] = useState("auto");
  const eligible = loopCandidates(graph, query).length;
  const noSamples = Boolean(schema && !schema.productionBundle);
  const most = Math.min(schema?.maxItems ?? 24, Math.max(4, eligible));
  const [words, setWords] = useState(Math.min(DEFAULT_WORDS, Math.max(4, eligible)));
  const [asking, setAsking] = useState(false);

  useEffect(() => {
    void backendSession.loopSchema()
      .then(setSchema)
      .catch((error: unknown) => setTrouble(error instanceof AcervoApiError
        ? error.message
        : "The loop generator could not be reached."));
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const make = async () => {
    setAsking(true);
    try {
      const answer = await backendSession.makeLoop({
        deviceId, language: query.language,
        lexemeIds: sampleLexemeIds(graph, query, Math.min(words, eligible), Date.now()),
        ...(family === "auto" ? {} : { family })
      });
      onMade(answer.loop.id);
      onClose();
    } catch (error) {
      setAsking(false);
      onNotify(error instanceof AcervoApiError ? error.message : "That loop could not be asked for.");
    }
  };

  const where = query.topic === "all" ? languageOf(query.language).name
    : query.topic === "inbox" ? `${languageOf(query.language).name} · Inbox`
      : `${languageOf(query.language).name} · ${graph.topics.find((topic) => topic.id === query.topic)?.name ?? "this topic"}`;

  return <div
    className="modal-backdrop" role="presentation"
    onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
  >
    <section className="settings loop-dialog" role="dialog" aria-modal="true" aria-labelledby="loop-dialog-title">
      <header>
        <h2 id="loop-dialog-title">Make a loop</h2>
        <button className="close" onClick={onClose} aria-label="Close">×</button>
      </header>
      <div className="settings-body">
        <p className="config-help">
          Words are drawn from what you are looking at, and set to music with their translations.
        </p>
        <div className="loop-scope">
          <BookIcon />
          <span><strong>{where}</strong> · {eligible} {eligible === 1 ? "word can" : "words can"} be in a loop</span>
        </div>

        <label className="config-field">
          <span>How many words</span>
          <span className="loop-count">
            <input
              type="range" min={Math.min(4, most)} max={most} value={Math.min(words, most)}
              disabled={eligible === 0}
              onChange={(event) => setWords(Number(event.target.value))}
            />
            <output>{Math.min(words, most)} words</output>
          </span>
        </label>

        <label className="config-field">
          <span>Music</span>
          <select value={family} onChange={(event) => setFamily(event.target.value)}>
            <option value="auto">Surprise me</option>
            {(schema?.families ?? []).map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>

        <p className="config-help">
          A word with no single term to say is not eligible: a loop has to choose one meaning, and a
          word whose <em>one term</em> has not been written down has none to choose.
        </p>

        {noSamples && <p className="config-help warn">
          This server has no sample pack, so a loop cannot be made. Install it once with{" "}
          <code>./deploy.sh --install-samples</code>.
        </p>}

        <div className="loop-engine">
          {trouble
            ? <span className="warn">{trouble}</span>
            : schema
              ? `engine ${schema.engineVersion} · ${schema.productionBundle
                ? "sample pack installed"
                : "no sample pack"}`
              : "asking the generator what it can do…"}
        </div>

        <div className="loop-actions">
          <button className="tb-btn" onClick={onClose}>Cancel</button>
          <button
            className="tb-btn primary"
            disabled={asking || eligible === 0 || Boolean(trouble) || noSamples}
            onClick={() => void make()}
          >{asking ? "Asking…" : "Make the loop"}</button>
        </div>
      </div>
    </section>
  </div>;
}
