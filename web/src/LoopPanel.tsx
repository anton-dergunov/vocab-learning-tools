/**
 * Settings ▸ Loops: whether tracks are kept on this device, and what the generator can do.
 *
 * Two kinds of thing, kept apart on the page as `PronunciationPanel` keeps them apart. Keeping a
 * track is a **device** fact — a laptop with room and a phone without want different answers, and it
 * never leaves the device. What the generator is and whether it has its sample pack is the
 * **deployment's**, read from the server and not settable here.
 *
 * Keeping is **off** by default, where keeping clips is on, and the difference is measured rather
 * than felt: a vocabulary's clips cost about what its text does, and one loop costs more than both.
 * With it off a loop still plays — the track is held for the session — it is simply not kept.
 */

import { useEffect, useState } from "react";
import { AcervoApiError, backendSession, type LoopSchema } from "./api";
import { setLoopCacheEnabled, useLoopCache } from "./editorPreferences";
import { forgetLoops, keptLoopBytes } from "./loops";

function megabytes(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function LoopPanel({ onNotify }: { onNotify(message: string): void }) {
  const [schema, setSchema] = useState<LoopSchema | null>(null);
  const [trouble, setTrouble] = useState<string | null>(null);
  const keeping = useLoopCache();
  const [kept, setKept] = useState<number | null>(null);

  useEffect(() => {
    void backendSession.loopSchema()
      .then(setSchema)
      .catch((error: unknown) => setTrouble(error instanceof AcervoApiError
        ? error.message
        : "The loop generator could not be reached."));
    void keptLoopBytes().then(setKept);
  }, []);

  const keep = async (on: boolean) => {
    setLoopCacheEnabled(on);
    if (!on) { await forgetLoops(); setKept(0); }
  };

  return <section className="config-section">
    <h3>Loops</h3>
    <p className="config-help">
      A loop takes a handful of your words and sets them to music, so they are learned while you are
      doing something else. Each word is said, then its translation, then that pair twice more.
    </p>

    <h4 className="provider-heading">The generator</h4>
    {trouble && <p className="config-help warn">{trouble}</p>}
    {!trouble && !schema && <p className="config-help" role="status">Asking what it can do…</p>}
    {schema && <>
      <p className="config-help">
        Engine {schema.engineVersion} · up to {schema.maxItems} words a loop ·{" "}
        {schema.families.length} {schema.families.length === 1 ? "kind" : "kinds"} of music.
      </p>
      {/* Worth saying plainly rather than only in a log: without the sample pack every bed is
          oscillators instead of recorded instruments, which is a different category of sound and
          not a plainer one. It installs on the server, so it is a thing to go and do. */}
      <p className={`config-help${schema.productionBundle ? "" : " warn"}`}>
        {schema.productionBundle
          ? "The sample pack is installed, so beds are built from recorded instruments."
          : "The sample pack is not installed on this server, so every bed is synthesised — audibly plainer than the recorded instruments a loop is meant to use."}
      </p>
    </>}

    <h4 className="provider-heading">On this device</h4>
    <label className="config-switch">
      <input type="checkbox" checked={keeping} onChange={(event) => void keep(event.target.checked)} />
      <span>
        <strong>Keep loops on this device</strong>
        <span>
          A loop heard once plays again with no connection. Off, a loop is fetched when you press
          play and held only until you close Acervo — a track is megabytes where a pronunciation is
          kilobytes, which is the whole reason this is a choice.
        </span>
      </span>
    </label>
    <div className="sync-actions">
      <button
        className="tb-btn" disabled={!kept}
        onClick={() => void forgetLoops().then(() => { setKept(0); onNotify("Loops forgotten on this device"); })}
      >Forget loops on this device</button>
      {kept !== null && <span className="config-help">{kept ? `${megabytes(kept)} kept` : "Nothing kept"}</span>}
    </div>
  </section>;
}
