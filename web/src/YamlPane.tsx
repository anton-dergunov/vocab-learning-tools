import { useLayoutEffect, useRef, useState } from "react";
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

const gutterFor = (text: string) => text.split("\n").map((_, index) => index + 1).join("\n");

/** Gutter, highlight layer and textarea kept in lockstep, as in the prototype. */
export function EditorSurface({ value, onChange, minHeight }: {
  value: string; onChange(value: string): void; minHeight: string;
}) {
  const area = useRef<HTMLTextAreaElement>(null);
  const highlight = useRef<HTMLPreElement>(null);
  useLayoutEffect(() => {
    const element = area.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${element.scrollHeight}px`;
  }, [value]);
  /**
   * The textarea is the only layer that scrolls — it is on top, and it clips. The highlight beneath
   * it does not, so on any line long enough to scroll, the caret drifts away from the glyphs it is
   * supposed to sit between. Moving the two together is what keeps them in register.
   */
  const follow = () => {
    const element = area.current;
    const painted = highlight.current;
    if (!element || !painted) return;
    painted.scrollLeft = element.scrollLeft;
    painted.scrollTop = element.scrollTop;
  };
  return <div className="code-scroll">
    <div className="gutter">{gutterFor(value)}</div>
    <div className="editor-stack">
      <pre className="hl" ref={highlight} aria-hidden="true"><code dangerouslySetInnerHTML={{ __html: highlightYaml(value) }} /></pre>
      <textarea
        ref={area} value={value} spellCheck={false} autoCapitalize="off" autoCorrect="off"
        style={{ minHeight }} onScroll={follow}
        onChange={(event) => { onChange(event.target.value); follow(); }}
      />
    </div>
  </div>;
}

export function YamlView({ name, yaml }: { name: string; yaml: string }) {
  return <div className="code-wrap">
    <div className="code-head">
      <span className="label">{name}.yaml</span>
      <span className="spacer" />
      <span className="label">read-only — press Edit to change</span>
    </div>
    <div className="code-scroll">
      <div className="gutter">{gutterFor(yaml)}</div>
      <pre><code dangerouslySetInnerHTML={{ __html: highlightYaml(yaml) }} /></pre>
    </div>
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
  return <>
    <div className="code-wrap">
      <div className="code-head">
        <span className="label">{name}.yaml</span>
        <span className="spacer" />
        <button className="tb-btn" style={{ height: 28 }} onClick={onCancel}>Cancel</button>
        <button className="tb-btn primary" style={{ height: 28 }} disabled={busy} onClick={() => onSave(draft)}>
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
      <EditorSurface value={draft} onChange={setDraft} minHeight="40vh" />
    </div>
    <ValidationPanel problems={problems} notice={notice} />
  </>;
}
