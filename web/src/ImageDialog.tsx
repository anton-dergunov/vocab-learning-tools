/**
 * Changing one sense's picture: read the brief, edit it, draw it, replace it, or rule it out.
 *
 * This is the flow for the hard cases. Ordinary words come out well and get their pictures without
 * anyone being asked — the whole point of enrichment happening behind the article. What is here is
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
import { AcervoApiError, backendSession, type ImagePromptRow, type ImageStyle } from "./api";
import type { ImagePrompt } from "./domain";
import { forget } from "./media";
import { useFilePicker } from "./SenseImage";

type Busy = "" | "drawing" | "briefing" | "attaching" | "removing";

export function ImageDialog({
  prompt, senseId, lexemeId, headword, styles, deviceId, onClose, onChanged, onNotify
}: {
  /** Null for a sense that has no prompt row yet: the only action is to write one. */
  prompt: ImagePrompt | null;
  /** The sense that was clicked. Not read off `prompt`, which is null for a sense with no row. */
  senseId: string;
  /** Likewise the word: a brief is written for the whole lexeme, row or no row. */
  lexemeId: string;
  headword: string;
  styles: ImageStyle[];
  deviceId: string;
  onClose(): void;
  /** Called after any write, so the caller can pull and re-render. */
  onChanged(row: ImagePromptRow | null): void;
  onNotify(message: string): void;
}) {
  const [brief, setBrief] = useState(prompt?.prompt ?? "");
  const [styleId, setStyleId] = useState(prompt?.styleId ?? "");
  const [busy, setBusy] = useState<Busy>("");
  const [composed, setComposed] = useState<string | null>(null);

  useEffect(() => {
    setBrief(prompt?.prompt ?? "");
    setStyleId(prompt?.styleId ?? "");
  }, [prompt?.id, prompt?.prompt, prompt?.styleId]);

  const working = busy !== "";

  const run = async (what: Busy, action: () => Promise<ImagePromptRow | null>) => {
    setBusy(what);
    try {
      const row = await action();
      if (row) {
        setBrief(row.prompt);
        setStyleId(row.styleId);
        setComposed(row.composedPrompt);
      }
      onChanged(row);
    } catch (error) {
      onNotify(error instanceof AcervoApiError ? error.message : "That did not work.");
    } finally {
      setBusy("");
    }
  };

  const draw = () => prompt && run("drawing", async () => {
    // The reference does not change across a regeneration — it is derived from the record — so the
    // cached bytes have to go or the article keeps showing the picture that was just replaced.
    if (prompt.imageRef) await forget(prompt.imageRef);
    return backendSession.renderImage(prompt.id, deviceId, { prompt: brief, styleId });
  });

  const rewrite = () => run("briefing", async () => {
    const { imagePrompts } = await backendSession.briefLexeme(lexemeId, deviceId);
    // The row for *this* sense out of the word's whole set, so the field shows the brief that was
    // just written rather than going blank while the others are updated too.
    return imagePrompts.find((row) => row.senseId === senseId) ?? null;
  });

  const attach = (file: File) => run("attaching", async () => {
    if (prompt?.imageRef) await forget(prompt.imageRef);
    return backendSession.attachImage(senseId, deviceId, file);
  });

  const remove = () => prompt && run("removing", async () => {
    if (prompt.imageRef) await forget(prompt.imageRef);
    return backendSession.removeImage(prompt.id, deviceId);
  });

  const picker = useFilePicker(attach);

  return <div className="modal-backdrop" role="presentation"
    onMouseDown={(event) => { if (event.target === event.currentTarget && !working) onClose(); }}>
    <section className="settings image-dialog" role="dialog" aria-modal="true" aria-labelledby="image-dialog-title">
      <header>
        <h2 id="image-dialog-title">Picture for “{headword}”</h2>
        <button className="close" onClick={onClose} disabled={working} aria-label="Close">×</button>
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
          This sense is set to have no picture. Drawing one turns that off.
        </p>}

        <div className="image-actions">
          <button className="primary" onClick={draw} disabled={working || !prompt || !brief.trim() || !styleId}>
            {busy === "drawing" ? "Drawing…" : "Draw"}
          </button>
          <button onClick={rewrite} disabled={working}>
            {busy === "briefing" ? "Writing…" : "Write a new brief"}
          </button>
          <button onClick={picker.choose} disabled={working}>
            {busy === "attaching" ? "Adding…" : "Use my own picture…"}
          </button>
          <button className="danger" onClick={remove} disabled={working || !prompt}>
            {busy === "removing" ? "Removing…" : "No picture here"}
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
