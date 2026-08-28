import { useEffect, useLayoutEffect, useRef, useState } from "react";

const escapeHtml = (value: string) =>
  value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

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
  useLayoutEffect(() => {
    const element = area.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${element.scrollHeight}px`;
  }, [value]);
  return <div className="code-scroll">
    <div className="gutter">{gutterFor(value)}</div>
    <div className="editor-stack">
      <pre className="hl" aria-hidden="true"><code dangerouslySetInnerHTML={{ __html: highlightYaml(value) }} /></pre>
      <textarea
        ref={area} value={value} spellCheck={false} autoCapitalize="off" autoCorrect="off"
        style={{ minHeight }} onChange={(event) => onChange(event.target.value)}
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

export function YamlEditor({ name, yaml, onCancel, onSave }: {
  name: string; yaml: string; onCancel(): void; onSave(): void;
}) {
  const [draft, setDraft] = useState(yaml);
  useEffect(() => setDraft(yaml), [yaml]);
  return <div className="code-wrap">
    <div className="code-head">
      <span className="label">{name}.yaml</span>
      <span className="spacer" />
      <button className="tb-btn" style={{ height: 28 }} onClick={onCancel}>Cancel</button>
      <button className="tb-btn primary" style={{ height: 28 }} onClick={onSave}>Save</button>
    </div>
    <EditorSurface value={draft} onChange={setDraft} minHeight="40vh" />
  </div>;
}
