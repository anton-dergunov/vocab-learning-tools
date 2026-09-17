/**
 * Settings ▸ Pictures: whether they are drawn unattended, and which styles are in play.
 *
 * Two settings and deliberately not a third. Rounds 1–7 of the prompt work tried per-style weights
 * and a sampled menu; what survived is that the owner should say *which styles exist for them* and
 * *how adventurously to choose among them*. A weight is a number nobody can set meaningfully
 * without running a few hundred pictures and counting, which is what the histogram in
 * `experiments/sense-images/` is for and not what a settings screen is for.
 *
 * Owner-scoped **server** state, unlike the editor's wrapping preference: the drawing happens on
 * the server, so a phone that has never opened this screen must still get the styles chosen here.
 */

import { useEffect, useRef, useState } from "react";
import { AcervoApiError, backendSession, type ImageSettings } from "./api";

type Changes = Partial<Pick<ImageSettings, "drawEnabled" | "stylesOff" | "boostVariety">>;

export default function ImagePanel({ onNotify }: { onNotify(message: string): void }) {
  const [settings, setSettings] = useState<ImageSettings | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  /**
   * What this screen believes, updated in the same breath as the state.
   *
   * `settings` is what React renders and lags a tick behind; this is what the *next* click has to
   * compute from. Switching off four styles in a row is one gesture, and each click has to add to
   * the previous one rather than to whatever the last render happened to hold.
   */
  const intended = useRef<ImageSettings | null>(null);
  /** Only the newest answer counts: two saves can return out of order. */
  const newest = useRef(0);

  const commit = (next: ImageSettings) => {
    intended.current = next;
    setSettings(next);
  };

  useEffect(() => {
    void backendSession.imageSettings()
      .then(commit)
      .catch((error: unknown) => setFailed(
        error instanceof AcervoApiError
          ? error.message
          : "These settings live on the server, which could not be reached."
      ));
  }, []);

  /**
   * Move the switch at once, then reconcile with what the server stored.
   *
   * The switch *is* the feedback, which is why there is no "Saving…" line: one appeared and
   * vanished on every click, and since the dialog is sized by its content that resized the whole
   * window and put it back. Nothing else in Settings announces a save either.
   *
   * Optimism with a way back: a refused change restores exactly what was showing before it, so a
   * switch never sits in a state the server does not hold.
   */
  const apply = async (changes: Changes) => {
    const before = intended.current;
    if (!before) return;
    const token = ++newest.current;
    commit({ ...before, ...changes, chosen: true });
    try {
      const stored = await backendSession.saveImageSettings(changes);
      if (newest.current === token) commit(stored);
    } catch (error) {
      if (newest.current === token) commit(before);
      onNotify(error instanceof AcervoApiError ? error.message : "That change was not saved.");
    }
  };

  if (failed) return <section className="config-section">
    <h3>Pictures</h3>
    <p className="config-help warn">{failed}</p>
  </section>;

  if (!settings) return <section className="config-section">
    <h3>Pictures</h3>
    <p className="config-help" role="status">Reading your settings…</p>
  </section>;

  const off = new Set(settings.stylesOff);
  const toggle = (styleId: string, on: boolean) => {
    const next = new Set(intended.current?.stylesOff ?? []);
    if (on) next.delete(styleId); else next.add(styleId);
    void apply({ stylesOff: [...next] });
  };

  return <section className="config-section">
    <h3>Pictures</h3>
    <p className="config-help">
      One picture per sense, drawn from a description a language model writes about that sense
      specifically. A word you save gets its pictures behind the article, one at a time; everything
      else is drawn on the server when nobody is watching.
    </p>

    {!settings.available && <p className="config-help warn">
      This server has no picture provider configured, so nothing will be drawn until one is set up
      in Providers.
    </p>}

    <label className="config-switch">
      <input
        type="checkbox" checked={settings.drawEnabled}
        onChange={(event) => void apply({ drawEnabled: event.target.checked })}
      />
      <span>
        <strong>Draw pictures</strong>
        <span>
          A word you save gets its pictures on its own, drawn on the server — including words added
          by a script, and whether or not the page stays open. Off, nothing is drawn until you ask
          for it on a sense, which is how you keep the ones you choose by hand and no others.
        </span>
      </span>
    </label>

    <label className="config-switch">
      <input
        type="checkbox" checked={settings.boostVariety}
        onChange={(event) => void apply({ boostVariety: event.target.checked })}
      />
      <span>
        <strong>Push for stylistic variety</strong>
        <span>
          Offers each style with a few of the subjects it suits, sampled per word, which nudges the
          writer toward styles it would otherwise pass over. Both settings produce good pictures;
          this one is less predictable.
        </span>
      </span>
    </label>

    <h4 className="provider-heading">Styles</h4>
    <p className="config-help">
      Every style switched on is offered for every sense, and the writer picks the one that suits
      the meaning — a style that cannot carry a sense is passed over rather than forced. Switch off
      the ones you do not want to see.
    </p>
    {/* Twenty-three switches, so the two bulk moves earn their place: the working gesture for
        "just these three" is clear-then-tick. Switching all on sends an empty off-list, which is
        also what a fresh account holds, so it doubles as the way back to the deployment's default. */}
    <div className="style-bulk">
      <button
        type="button"
        onClick={() => void apply({ stylesOff: [] })}
        disabled={off.size === 0}
      >Switch all on</button>
      <button
        type="button"
        // All but the first, which is `cinematic-photoreal`: the one register the template says can
        // carry any meaning at all, so it is the least bad thing to be left with.
        onClick={() => void apply({ stylesOff: settings.styles.slice(1).map((style) => style.id) })}
        disabled={off.size >= settings.styles.length - 1}
      >Switch all off</button>
      <span className="style-count">
        {settings.styles.length - off.size} of {settings.styles.length} on
      </span>
    </div>
    <p className="config-help">
      One style always stays on: with none there would be nothing to draw with, and “draw nothing”
      is the switch at the top of this page rather than an empty list here.
    </p>
    <div className="style-grid">
      {settings.styles.map((style) => <label key={style.id} className="style-switch">
        <input
          type="checkbox" checked={!off.has(style.id)}
          onChange={(event) => toggle(style.id, event.target.checked)}
        />
        <span>{style.label}{style.mono && <span className="label"> mono</span>}</span>
      </label>)}
    </div>

    {!settings.chosen && <p className="config-help">
      Nothing has been chosen yet, so this server’s own defaults are in force.
    </p>}
  </section>;
}
