import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { yaml as yamlLanguage } from "@codemirror/lang-yaml";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { Compartment, EditorState } from "@codemirror/state";
import { EditorView, keymap, lineNumbers } from "@codemirror/view";
import { tags } from "@lezer/highlight";
import { useEffect, useRef, useState } from "react";
import Composer from "./Composer";
import { CloseIcon } from "./icons";
import type { YamlProblem } from "./yaml";

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

/* ── the editing surface ────────────────────────────────────────────────
   CodeMirror owns the caret and the glyphs together, which is the whole reason it is here.

   This was hand-written before: a transparent `<textarea>` laid over a separately rendered copy of
   the same text. Two independent layouts had to agree pixel for pixel, and every way they could
   disagree was a bug you could see — text drawn over text, a selection that stopped short, typing
   that landed in the wrong place. Three attempts fixed three symptoms without fixing the cause. */

/** The document's own colours, mapped onto the palette the rest of the interface uses. */
const YAML_COLOURS = HighlightStyle.define([
  { tag: [tags.definition(tags.propertyName), tags.propertyName], color: "var(--core)" },
  { tag: [tags.string, tags.special(tags.string)], color: "var(--ink)" },
  { tag: [tags.number, tags.bool, tags.null], color: "var(--corpus)" },
  { tag: tags.comment, color: "var(--ink-3)", fontStyle: "italic" },
  { tag: [tags.punctuation, tags.separator, tags.bracket], color: "var(--ink-3)" }
]);

const THEME = EditorView.theme({
  "&": { color: "var(--ink-2)", backgroundColor: "transparent", height: "100%" },
  "&.cm-focused": { outline: "none" },
  ".cm-scroller": {
    fontFamily: "var(--mono)", fontSize: "12.5px", lineHeight: "18px",
    overflow: "auto", overscrollBehavior: "contain"
  },
  ".cm-content": { padding: "14px 0 18px", caretColor: "var(--core)" },
  ".cm-cursor, .cm-dropCursor": { borderLeftColor: "var(--core)" },
  ".cm-gutters": {
    backgroundColor: "var(--code-bg)", color: "var(--ink-3)", opacity: ".55",
    // Declared here rather than in the stylesheet: a theme rule outranks it, so the divider set
    // outside would be silently overridden by this block's own border.
    border: "none", borderRight: "1px solid var(--rule-soft)"
  },
  ".cm-lineNumbers .cm-gutterElement": { padding: "0 10px 0 16px", fontVariantNumeric: "tabular-nums" },
  ".cm-activeLine, .cm-activeLineGutter": { backgroundColor: "transparent" },
  // Semi-transparent on purpose: an opaque band hides the characters it is meant to be marking.
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection": {
    backgroundColor: "color-mix(in srgb, var(--core) 26%, transparent)"
  },
  ".cm-line": { padding: "0 16px" }
});

/* Reconfigured in place rather than by rebuilding the editor, so changing a preference does not
   throw away the undo history or the caret. */
const wrapping = new Compartment();
const numbering = new Compartment();
const editable = new Compartment();

export function EditorSurface({ value, onChange, wrap = true, numbers = false, readOnly = false }: {
  value: string; onChange(value: string): void; wrap?: boolean; numbers?: boolean; readOnly?: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  // Read through a ref so the editor is created once: rebuilding it on every keystroke would drop
  // the selection and the undo history with it.
  const notify = useRef(onChange);
  notify.current = onChange;

  useEffect(() => {
    if (!host.current) return;
    const editor = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: value,
        extensions: [
          history(),
          keymap.of([...defaultKeymap, ...historyKeymap]),
          yamlLanguage(),
          syntaxHighlighting(YAML_COLOURS),
          THEME,
          wrapping.of(wrap ? EditorView.lineWrapping : []),
          numbering.of(numbers ? lineNumbers() : []),
          editable.of([EditorState.readOnly.of(readOnly), EditorView.editable.of(!readOnly)]),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) notify.current(update.state.doc.toString());
          })
        ]
      })
    });
    view.current = editor;
    return () => { editor.destroy(); view.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    view.current?.dispatch({ effects: wrapping.reconfigure(wrap ? EditorView.lineWrapping : []) });
  }, [wrap]);
  useEffect(() => {
    view.current?.dispatch({ effects: numbering.reconfigure(numbers ? lineNumbers() : []) });
  }, [numbers]);
  useEffect(() => {
    view.current?.dispatch({ effects: editable.reconfigure([
      EditorState.readOnly.of(readOnly), EditorView.editable.of(!readOnly)
    ]) });
  }, [readOnly]);

  /* The document belongs to whoever is typing. It follows the prop only when the two have actually
     diverged — a projection recomputed from the replica after a sync must not wipe a draft or throw
     the caret to the end. */
  useEffect(() => {
    const editor = view.current;
    if (!editor || editor.state.doc.toString() === value) return;
    editor.dispatch({ changes: { from: 0, to: editor.state.doc.length, insert: value } });
  }, [value]);

  return <div className="code-scroll" ref={host} />;
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
