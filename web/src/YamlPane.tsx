import { Fragment, useEffect, useState } from "react";
import Composer from "./Composer";
import { CloseIcon } from "./icons";
import type { YamlProblem } from "./yaml";

const escapeHtml = (value: string) =>
  value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

/** Minimal YAML colouring for the read and edit surfaces. Input is escaped first. */
export function highlightYaml(text: string): string {
  return escapeHtml(text)
    .replace(/(#.*)$/gm, '<span class="y-com">$1</span>')
    .replace(/^(\s*)(-?\s*)([A-Za-z_][\w]*)(:)/gm, '$1<span class="y-dash">$2</span><span class="y-key">$3</span>$4')
    .replace(/(:\s)(&quot;[^&]*?&quot;)/g, '$1<span class="y-str">$2</span>')
    .replace(/(:\s)(-?\d+(?:\.\d+)?)$/gm, '$1<span class="y-num">$2</span>');
}

/**
 * How the YAML surfaces present text, remembered per device.
 *
 * These describe this screen, not the vocabulary — a phone and a desktop want different answers —
 * so they live in local storage rather than the replicated graph, and they are set in Settings
 * rather than above the editor, where they were controls you had to step over on the way to work.
 *
 * Wrapping is the default: these documents are mostly prose, and a definition running off the right
 * edge is the common case. Scrolling stays available because YAML indentation is meaningful.
 */
export interface EditorPreferences {
  wrap: boolean;
  numbers: boolean;
}

const PREFERENCE_KEYS = { wrap: "acervo-editor-wrap", numbers: "acervo-editor-numbers" } as const;
const PREFERENCES_EVENT = "acervo-editor-preferences";

function readPreference(key: string, fallback: boolean): boolean {
  try {
    const stored = localStorage.getItem(key);
    return stored === null ? fallback : stored === "on";
  } catch {
    return fallback;
  }
}

export function editorPreferences(): EditorPreferences {
  return {
    wrap: readPreference(PREFERENCE_KEYS.wrap, true),
    numbers: readPreference(PREFERENCE_KEYS.numbers, false)
  };
}

export function setEditorPreference(name: keyof EditorPreferences, value: boolean): void {
  try { localStorage.setItem(PREFERENCE_KEYS[name], value ? "on" : "off"); } catch { /* a preference, not data */ }
  // Settings and the editor are different trees, so a change in one has to reach the other.
  window.dispatchEvent(new CustomEvent(PREFERENCES_EVENT));
}

export function useEditorPreferences(): EditorPreferences {
  const [preferences, setPreferences] = useState(editorPreferences);
  useEffect(() => {
    const refresh = () => setPreferences(editorPreferences());
    window.addEventListener(PREFERENCES_EVENT, refresh);
    return () => window.removeEventListener(PREFERENCES_EVENT, refresh);
  }, []);
  return preferences;
}

/**
 * The editing surface: a highlighted copy of the text with a transparent textarea laid over it.
 *
 * Both layers live in one grid, occupying the same cells, so the *content* decides the height and
 * the textarea stretches to it. That is the whole trick, and it is what the previous version got
 * wrong: it measured `scrollHeight` and set the height in an effect keyed on the text, so resizing
 * the window rewrapped the content without rewrapping the box around it. The highlight was then
 * clipped to a stale height — invisible text you could still select, because the textarea above it
 * had laid out correctly all along.
 *
 * One line per row means a wrapped line is a row several lines tall, so a number beside it points
 * at the line it belongs to whether the text wraps or scrolls.
 */
export function EditorSurface({ value, onChange, wrap = true, numbers = false, readOnly = false }: {
  value: string; onChange(value: string): void; wrap?: boolean; numbers?: boolean; readOnly?: boolean;
}) {
  const lines = value.split("\n");
  return <div className={`code-scroll${wrap ? " wrap" : ""}${numbers ? " numbered" : ""}`}>
    <div className="editor-grid">
      {lines.map((line, index) => <Fragment key={index}>
        {numbers && <span className="ln-no" style={{ gridRow: index + 1 }}>{index + 1}</span>}
        <div
          className="ln" aria-hidden="true" style={{ gridRow: index + 1 }}
          dangerouslySetInnerHTML={{ __html: highlightYaml(line) }}
        />
      </Fragment>)}
      <textarea
        value={value} spellCheck={false} autoCapitalize="off" autoCorrect="off" readOnly={readOnly}
        style={{ gridRow: `1 / ${lines.length + 1}`, gridColumn: numbers ? 2 : 1 }}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  </div>;
}

export function YamlView({ name, yaml }: { name: string; yaml: string }) {
  const { wrap, numbers } = useEditorPreferences();
  return <div className="code-wrap">
    <div className="code-head">
      <span className="label">{name}.yaml</span>
      <span className="spacer" />
      <span className="label">read-only — press Edit to change</span>
    </div>
    {/* The same surface as the editor, so the projection you read and the one you edit cannot
        disagree about how a long line is shown. */}
    <EditorSurface value={yaml} onChange={() => undefined} wrap={wrap} numbers={numbers} readOnly />
  </div>;
}

/** Parse problems, a refusal from the server, or the confirmation that a save landed. */
export function ValidationPanel({ problems, notice }: {
  problems: YamlProblem[]; notice: string | null;
}) {
  if (!problems.length) {
    return notice ? <div className="validation ok" role="status">{notice}</div> : null;
  }
  return <div className="validation bad" role="alert">
    <strong>{problems.length === 1 ? "This document was not saved:" : `${problems.length} problems, so nothing was saved:`}</strong>
    <ul>
      {problems.map((problem, index) => <li key={index}>
        {problem.line !== null && <code>line {problem.line}</code>} {problem.message}
      </li>)}
    </ul>
  </div>;
}

/**
 * The draft is seeded once and then belongs to whoever is typing. It deliberately does not follow
 * the `yaml` prop: that is recomputed from the replica on every render, so a sync landing mid-edit
 * would otherwise wipe the draft and throw the caret to the end. Remounting on a different entry
 * (a `key`) is what replaces it.
 */
export function YamlEditor({ name, yaml, problems, notice, busy, onCancel, onSave }: {
  name: string;
  yaml: string;
  problems: YamlProblem[];
  notice: string | null;
  busy: boolean;
  onCancel(): void;
  onSave(draft: string): void;
}) {
  const [draft, setDraft] = useState(yaml);
  const { wrap, numbers } = useEditorPreferences();
  return <Composer
    label={`Edit ${name}`}
    fill
    head={<>
      <h2>{name}</h2>
      <span className="label">{name}.yaml</span>
      <span className="spacer" />
      <button className="icon-btn" aria-label="Close" onClick={onCancel}><CloseIcon /></button>
    </>}
    actions={<>
      <ValidationPanel problems={problems} notice={notice} />
      <div className="composer-buttons">
        <span className="spacer" />
        <button className="tb-btn" onClick={onCancel}>Cancel</button>
        <button className="tb-btn primary" disabled={busy} onClick={() => onSave(draft)}>
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
    </>}
  >
    <div className="code-wrap">
      <EditorSurface value={draft} onChange={setDraft} wrap={wrap} numbers={numbers} />
    </div>
  </Composer>;
}
