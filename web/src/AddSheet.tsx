import { useState } from "react";
import { CloseIcon } from "./icons";
import { EditorSurface } from "./YamlPane";
import { YAML_TEMPLATE } from "./yaml";

export type AddTab = "capture" | "yaml";

export default function AddSheet({ tab, onTab, onClose, onUnsupported }: {
  tab: AddTab;
  onTab(tab: AddTab): void;
  onClose(): void;
  onUnsupported(message: string): void;
}) {
  const [capture, setCapture] = useState("");
  const [draft, setDraft] = useState(YAML_TEMPLATE);

  return <div className="sheet-back open" role="presentation"
    onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="sheet" role="dialog" aria-modal="true" aria-label="Add a word">
      <div className="sheet-head">
        <h2>Add a word</h2>
        <span className="spacer" />
        <div className="seg">
          <button className={tab === "capture" ? "on" : ""} onClick={() => onTab("capture")}>Capture</button>
          <button className={tab === "yaml" ? "on" : ""} onClick={() => onTab("yaml")}>YAML</button>
        </div>
        <button className="icon-btn" aria-label="Close" onClick={onClose}><CloseIcon /></button>
      </div>
      <div className="sheet-body">
        {tab === "capture" ? <>
          <label className="label" htmlFor="captureText">Paste a word, or the sentence you met it in</label>
          <textarea
            className="capture-area" id="captureText" style={{ marginTop: 8 }} value={capture}
            onChange={(event) => setCapture(event.target.value)}
            placeholder="Se pican las verduras en dados de un centímetro y se reservan."
          />
          <p className="hint">
            Share the sentence and pick the word here; the entry is generated in the background and lands
            in <b>Inbox</b> ready for review. Generation is not connected yet.
          </p>
          <div className="sheet-actions">
            <span className="stub">stub</span>
            <span className="spacer" />
            <button className="tb-btn" onClick={() => onTab("yaml")}>Write YAML instead</button>
            <button className="tb-btn primary" onClick={() => onUnsupported("Capture pipeline is not wired up yet")}>Process</button>
          </div>
        </> : <>
          <div className="code-wrap">
            <div className="code-head"><span className="label">new-entry.yaml</span></div>
            <EditorSurface value={draft} onChange={setDraft} minHeight="44vh" />
          </div>
          <div className="sheet-actions">
            <span className="spacer" />
            <button className="tb-btn" onClick={onClose}>Cancel</button>
            <button className="tb-btn primary" onClick={() => onUnsupported("Creating entries is not wired up yet")}>Validate &amp; save</button>
          </div>
        </>}
      </div>
    </div>
  </div>;
}
