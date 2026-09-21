import { useEffect, useState } from "react";
import { AcervoApiError, backendSession, type PromptRules } from "./api";

/**
 * Settings ▸ Rules: free text the models are given with everything they write for you.
 *
 * Saved with a button rather than on every keystroke: this is prose, and a rule saved half-typed
 * would reach the next entry written while you were still typing it.
 */
export default function RulesPanel({ onNotify }: { onNotify(message: string): void }) {
  const [stored, setStored] = useState<PromptRules | null>(null);
  const [draft, setDraft] = useState("");
  const [failed, setFailed] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    backendSession.promptRules()
      .then((rules) => { setStored(rules); setDraft(rules.rules); })
      .catch((error: unknown) => setFailed(error instanceof AcervoApiError
        ? error.message : "This setting lives on the server, which could not be reached."));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const saved = await backendSession.savePromptRules(draft);
      setStored(saved);
      setDraft(saved.rules);
      onNotify(saved.rules ? "Rules saved." : "Rules cleared.");
    } catch (error) {
      onNotify(error instanceof AcervoApiError ? error.message : "Your rules were not saved.");
    } finally {
      setSaving(false);
    }
  };

  if (failed) return <section className="config-section">
    <h3>Rules</h3>
    <p className="config-help warn">{failed}</p>
  </section>;

  if (!stored) return <section className="config-section">
    <h3>Rules</h3>
    <p className="config-help" role="status">Reading your rules…</p>
  </section>;

  const over = draft.trim().length > stored.limit;
  const unchanged = draft.trim() === stored.rules;
  return <section className="config-section">
    <h3>Rules</h3>
    <p className="config-help">
      Added to everything the models write for you — entries, examples, the article conversation,
      picture descriptions, stories and the clips chosen for a word. Anything already written stays
      as it is; ask again to have it rewritten.
    </p>
    <textarea
      className="rules-text"
      aria-label="Rules for generated content"
      value={draft}
      onChange={(event) => setDraft(event.target.value)}
      placeholder={"For example:\nI am vegan, so never show or mention meat or fish as food.\n"
        + "I read Spanish at about B2; keep examples at that level."}
    />
    <div className="rules-foot">
      <span className={`rules-count${over ? " warn" : ""}`}>
        {draft.trim().length} / {stored.limit}
      </span>
      <button className="tb-btn primary" disabled={saving || over || unchanged} onClick={() => void save()}>
        {saving ? "Saving…" : "Save"}
      </button>
    </div>
  </section>;
}
