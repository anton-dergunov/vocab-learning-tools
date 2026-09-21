/**
 * Changing one sense's picture: read the brief, edit it, draw it, replace it, or rule it out.
 *
 * This is the flow for the hard cases. Ordinary words come out well and get their pictures without
 * anyone being asked — the whole point of the server enriching a word behind the article. What is here is
 * for the sense that is difficult to picture, where seeing the description that produced the bad
 * image is the only way to fix it.
 *
 * Three actions, named for what they cost, rather than one button that guesses:
 *
 * - **Draw** — one image call. With the text edited, that is the whole cost; the brief is used as
 *   it stands and no model is asked to write one.
 * - **Write a new brief** — one *text* call, for the whole word, because the writer sees every
 *   sense at once and that batching is what makes two senses of one word look different. So it
 *   rewrites this word's other senses too, and says so.
 * - **Use my own picture** — no call at all.
 *
 * The composed prompt is shown but not editable: it is brief + style + frame, rebuilt by the server
 * from what is stored, and the editable half of it is the brief above. Copying it is the point —
 * it is what you paste into a provider's own console when you want to iterate by hand.
 */

import { useEffect, useState } from "react";
import { backendSession, type ImageStyle } from "./api";
import type { ImagePrompt } from "./domain";
import { useFilePicker } from "./SenseImage";

export function ImageDialog({
  prompt, headword, styles, briefing, onClose, onRebrief, onDraw, onAttach, onRemove
}: {
  /** The sense's row as the replica holds it now. Null for a sense that has none yet. */
  prompt: ImagePrompt | null;
  headword: string;
  styles: ImageStyle[];
  /** Whether a new brief for this word is being written on the server right now. */
  briefing: boolean;
  onClose(): void;
  /**
   * Ask the server for a new brief for the whole word. A job: the dialog may be closed, and the new
   * brief arrives in the field whenever it lands.
   */
  onRebrief(): void;
  /**
   * Hand a drawing to the caller, and expect nothing back.
   *
   * Drawing is 30-60 seconds and providers meter roughly one a minute, so awaiting it here would
   * be a button that hangs. The dialog closes instead and the picture itself says it is being
   * redrawn.
   */
  onDraw(overrides: { prompt: string; styleId: string }): void;
  /** Put this file where the drawn picture would go. Also not awaited — see `onDraw`. */
  onAttach(file: File): void;
  /** Remove the picture and rule the sense out. */
  onRemove(): void;
}) {
  const [brief, setBrief] = useState(prompt?.prompt ?? "");
  const [styleId, setStyleId] = useState(prompt?.styleId ?? "");
  const [composed, setComposed] = useState<string | null>(null);

  /* A new brief lands in the replica while the dialog is open, and the fields follow it. */
  useEffect(() => {
    setBrief(prompt?.prompt ?? "");
    setStyleId(prompt?.styleId ?? "");
  }, [prompt?.id, prompt?.prompt, prompt?.styleId]);

  /* The whole prompt is composed on the server and never stored, so it is read for the row on show. */
  useEffect(() => {
    setComposed(null);
    if (!prompt?.id || !prompt.prompt) return;
    let live = true;
    backendSession.imagePrompt(prompt.id)
      .then((row) => { if (live) setComposed(row.composedPrompt); })
      .catch(() => undefined);
    return () => { live = false; };
  }, [prompt?.id, prompt?.revision, prompt?.prompt]);

  const working = briefing;

  const draw = () => {
    if (!prompt) return;
    onDraw({ prompt: brief, styleId });
    onClose();
  };

  /* Attaching and removing close the dialog the way Draw does, and for the same reason: you have
     said what you want, and the article is where the answer belongs. The caller does the work and
     marks the picture while it runs. */
  const attach = (file: File) => {
    onAttach(file);
    onClose();
  };

  const remove = () => {
    if (!prompt) return;
    onRemove();
    onClose();
  };

  const picker = useFilePicker(attach);

  return <div className="modal-backdrop" role="presentation"
    onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="settings image-dialog" role="dialog" aria-modal="true" aria-labelledby="image-dialog-title">
      <header>
        <h2 id="image-dialog-title">Picture for “{headword}”</h2>
        {/* Always closes, even mid-brief. The brief is a server job and finishes either way. */}
        <button className="close" onClick={onClose} aria-label="Close">×</button>
      </header>

      <div className="settings-body">
        <label className="config-field">
          <span>What the picture shows</span>
          <textarea
            className="image-brief"
            rows={5}
            value={brief}
            onChange={(event) => setBrief(event.target.value)}
            placeholder="No description yet. Write a new brief, or type one here."
          />
        </label>

        <label className="config-field">
          <span>Style</span>
          <select value={styleId} onChange={(event) => setStyleId(event.target.value)}>
            <option value="">Choose a style</option>
            {styles.map((style) => <option key={style.id} value={style.id}>{style.label}</option>)}
          </select>
        </label>

        {composed && <details className="fold">
          <summary><span className="label">The whole prompt that was sent</span></summary>
          <div className="fold-body">
            <p className="hint">
              Brief, style and the constraints every picture carries. Rebuilt from what is stored
              rather than kept twice — copy it if you want to iterate in a provider’s own console.
            </p>
            <pre className="image-composed">{composed}</pre>
          </div>
        </details>}

        {prompt?.failureReason && <p className="config-help warn">{prompt.failureReason}</p>}
        {prompt?.suppressed && !prompt.imageRef && <p className="config-help">
          This sense is set to have no picture. Drawing one, or writing a new brief, turns that off.
        </p>}

        <div className="image-actions">
          <button className="primary" onClick={draw} disabled={working || !prompt || !brief.trim() || !styleId}>
            Draw
          </button>
          <button onClick={onRebrief} disabled={working}>
            {briefing ? "Writing…" : "Write a new brief"}
          </button>
          <button onClick={picker.choose} disabled={working}>Use my own picture…</button>
          <button className="danger" onClick={remove} disabled={working || !prompt}>
            No picture here
          </button>
          {picker.element}
        </div>

        <p className="config-help">
          A new brief costs one call to the language model and rewrites <em>every</em> sense of this
          word — the writer sees them together, which is what keeps two senses from looking alike.
          Drawing with the text above costs only the picture.
        </p>
      </div>
    </section>
  </div>;
}
