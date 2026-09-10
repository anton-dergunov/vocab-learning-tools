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

import { useEffect, useState } from "react";
import { AcervoApiError, backendSession, type ImageSettings } from "./api";

export default function ImagePanel({ onNotify }: { onNotify(message: string): void }) {
  const [settings, setSettings] = useState<ImageSettings | null>(null);
  const [working, setWorking] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    void backendSession.imageSettings()
      .then(setSettings)
      .catch((error: unknown) => setFailed(
        error instanceof AcervoApiError
          ? error.message
          : "These settings live on the server, which could not be reached."
      ));
  }, []);

  const save = async (changes: Partial<Pick<ImageSettings, "sweepEnabled" | "stylesOff" | "boostVariety">>) => {
    setWorking(true);
    try {
      // The answer is the server's, not this screen's optimism — a refused change must not leave a
      // switch showing a state the server does not hold.
      setSettings(await backendSession.saveImageSettings(changes));
    } catch (error) {
      onNotify(error instanceof AcervoApiError ? error.message : "That change was not saved.");
    } finally {
      setWorking(false);
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
    const next = new Set(off);
    if (on) next.delete(styleId); else next.add(styleId);
    void save({ stylesOff: [...next] });
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
        type="checkbox" checked={settings.sweepEnabled} disabled={working}
        onChange={(event) => void save({ sweepEnabled: event.target.checked })}
      />
      <span>
        <strong>Draw pictures unattended</strong>
        <span>
          Lets the server work through words that have none — including ones added by a script.
          Off, only the pictures you ask for by hand are drawn.
        </span>
      </span>
    </label>

    <label className="config-switch">
      <input
        type="checkbox" checked={settings.boostVariety} disabled={working}
        onChange={(event) => void save({ boostVariety: event.target.checked })}
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
    <div className="style-grid">
      {settings.styles.map((style) => <label key={style.id} className="style-switch">
        <input
          type="checkbox" checked={!off.has(style.id)} disabled={working}
          onChange={(event) => toggle(style.id, event.target.checked)}
        />
        <span>{style.label}{style.mono && <span className="label"> mono</span>}</span>
      </label>)}
    </div>

    {working && <p className="config-help" role="status">Saving…</p>}
    {!settings.chosen && <p className="config-help">
      Nothing has been chosen yet, so this server’s own defaults are in force.
    </p>}
  </section>;
}
