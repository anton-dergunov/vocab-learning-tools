/**
 * Settings ▸ Pronunciation: what is recorded in advance, whether examples carry their emotion, which
 * voice each model uses, and whether clips are kept on this device.
 *
 * Two kinds of setting on one page, and they are kept apart on it. The first three are owner-scoped
 * **server** state, because the recording happens on the server: a phone that has never opened this
 * screen still gets the voices chosen here. Keeping clips is a **device** fact, like wrapping in the
 * editor — a laptop with room and a phone without want different answers — so it is stored on the
 * device and never leaves it.
 *
 * Which models read, and in what order, is Settings ▸ Providers, beside every other order. This page
 * says what those models are to do.
 */

import { useEffect, useRef, useState } from "react";
import { AcervoApiError, backendSession, type PronunciationModel, type PronunciationPregenerate, type PronunciationSettings } from "./api";
import { setPronunciationCacheEnabled, usePronunciationCache } from "./editorPreferences";
import { languageOf } from "./languages";
import { forgetPronunciations, keptPronunciationBytes } from "./pronunciation";

type Changes = Partial<{ pregenerate: Partial<PronunciationPregenerate>; expressive: boolean; voices: PronunciationSettings["voices"] }>;

const ADVANCE: { id: keyof PronunciationPregenerate; title: string; help: string }[] = [
  { id: "headword", title: "The word itself", help: "A few kilobytes a word." },
  { id: "definitions", title: "Definitions", help: "Only where a vocabulary defines words in the language you are learning." },
  { id: "examples", title: "Example sentences", help: "In the language you are learning, with their emotion where the voice can take it." }
];

function megabytes(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function PronunciationPanel({ onNotify }: { onNotify(message: string): void }) {
  const [settings, setSettings] = useState<PronunciationSettings | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const intended = useRef<PronunciationSettings | null>(null);
  const newest = useRef(0);
  const keeping = usePronunciationCache();
  const [kept, setKept] = useState<number | null>(null);

  const commit = (next: PronunciationSettings) => {
    intended.current = next;
    setSettings(next);
  };

  useEffect(() => {
    void backendSession.pronunciationSettings()
      .then(commit)
      .catch((error: unknown) => setFailed(error instanceof AcervoApiError
        ? error.message
        : "These settings live on the server, which could not be reached."));
    void keptPronunciationBytes().then(setKept);
  }, []);

  /* Move the control at once, then reconcile with what the server stored — `ImagePanel`'s rule. */
  const apply = async (changes: Changes, optimistic: PronunciationSettings) => {
    const before = intended.current;
    if (!before) return;
    const token = ++newest.current;
    commit(optimistic);
    try {
      const stored = await backendSession.savePronunciationSettings(changes);
      if (newest.current === token) commit(stored);
    } catch (error) {
      if (newest.current === token) commit(before);
      onNotify(error instanceof AcervoApiError ? error.message : "That change was not saved.");
    }
  };

  const keep = async (on: boolean) => {
    setPronunciationCacheEnabled(on);
    if (!on) {
      await forgetPronunciations();
      setKept(0);
    }
  };

  const device = <>
    <h4 className="provider-heading">On this device</h4>
    <label className="config-switch">
      <input type="checkbox" checked={keeping} onChange={(event) => void keep(event.target.checked)} />
      <span>
        <strong>Keep pronunciations on this device</strong>
        <span>
          A clip heard once plays again with no connection, and clips recorded elsewhere are brought
          here after each sync. Off, every press asks the server, and what was kept is forgotten.
        </span>
      </span>
    </label>
    <div className="sync-actions">
      <button
        className="tb-btn" disabled={!kept}
        onClick={() => void forgetPronunciations().then(() => { setKept(0); onNotify("Pronunciations forgotten on this device"); })}
      >Forget pronunciations on this device</button>
      {kept !== null && <span className="config-help">{kept ? `${megabytes(kept)} kept` : "Nothing kept"}</span>}
    </div>
  </>;

  if (failed) return <section className="config-section">
    <h3>Pronunciation</h3>
    <p className="config-help warn">{failed}</p>
    {device}
  </section>;

  if (!settings) return <section className="config-section">
    <h3>Pronunciation</h3>
    <p className="config-help" role="status">Reading your settings…</p>
  </section>;

  const chooseVoice = (model: PronunciationModel, language: string, voice: string) => {
    const voices = structuredClone(intended.current?.voices ?? {});
    const forModel = { ...(voices[model.provider]?.[model.model] ?? {}) };
    if (voice) forModel[language] = voice; else delete forModel[language];
    voices[model.provider] = { ...(voices[model.provider] ?? {}), [model.model]: forModel };
    void apply({ voices }, { ...intended.current!, voices, chosen: true });
  };

  /* One model appears in both orders more often than not, and its voice is one choice, not two. */
  const models = [...settings.orders.plain, ...settings.orders.expressive]
    .filter((model, index, all) => all.findIndex((other) => other.provider === model.provider && other.model === model.model) === index)
    .filter((model) => Object.keys(model.voices).length > 0);

  return <section className="config-section">
    <h3>Pronunciation</h3>
    <p className="config-help">
      Every play button reads its text in that text’s own language. The first press records the clip
      on the server and every press after plays the same one; after you hear a bad one, Record again
      in the message that appears replaces it.
    </p>

    <h4 className="provider-heading">Record in advance</h4>
    <p className="config-help">
      When a word is saved, record these straight away rather than on the first press — so they play
      offline on a device that has never heard them.
    </p>
    {ADVANCE.map((entry) => <label key={entry.id} className="config-switch">
      <input
        type="checkbox" checked={settings.pregenerate[entry.id]}
        onChange={(event) => {
          const pregenerate = { ...intended.current!.pregenerate, [entry.id]: event.target.checked };
          void apply({ pregenerate: { [entry.id]: event.target.checked } }, { ...intended.current!, pregenerate, chosen: true });
        }}
      />
      <span><strong>{entry.title}</strong><span>{entry.help}</span></span>
    </label>)}

    <h4 className="provider-heading">Delivery</h4>
    <label className="config-switch">
      <input
        type="checkbox" checked={settings.expressive}
        onChange={(event) => void apply({ expressive: event.target.checked }, { ...intended.current!, expressive: event.target.checked, chosen: true })}
      />
      <span>
        <strong>Speak examples with their emotion</strong>
        <span>
          A sentence heard the way somebody would say it is easier to remember. Only a voice that
          takes directions can do this; the others read every sentence plainly. A clip already
          recorded keeps the delivery it has until you record it again.
        </span>
      </span>
    </label>

    <h4 className="provider-heading">Voices</h4>
    <p className="config-help">
      One voice per model and language, held steady so you learn it. A change applies to the next
      recording, not to clips you already have.
    </p>
    {models.length === 0 && <p className="config-help">No model in your pronunciation orders speaks your vocabularies’ languages.</p>}
    {models.map((model) => <div key={`${model.provider}/${model.model}`} className="voice-model">
      <strong>{model.providerLabel} · {model.model}{!model.available && <span className="label"> not configured</span>}</strong>
      {Object.entries(model.voices).map(([language, voices]) => <label key={language} className="config-field">
        <span>{languageOf(language).name}</span>
        <select
          value={settings.voices[model.provider]?.[model.model]?.[language] ?? ""}
          onChange={(event) => chooseVoice(model, language, event.target.value)}
        >
          <option value="">Default · {voices[0]}</option>
          {voices.map((voice) => <option key={voice} value={voice}>{voice}</option>)}
        </select>
      </label>)}
    </div>)}

    {device}
  </section>;
}
