import { useState } from "react";
import type { CaptureRequest, CaptureResult } from "./api";
import { CloseIcon } from "./icons";
import { EditorSurface, ValidationPanel } from "./YamlPane";
import { YAML_TEMPLATE, yamlForDraft, type YamlProblem } from "./yaml";

export type AddTab = "capture" | "yaml";

/**
 * Capture (§05) and the YAML escape hatch, in one sheet, because they are two ways to do one thing.
 *
 * Processing does not save anything. It returns a proposal, which is rendered into the YAML tab and
 * saved by exactly the path a hand-written document takes — so there is one writer, one validator
 * and one diff, and a generated entry cannot arrive by a route a typed one could not.
 */
export default function AddSheet({ tab, onTab, problems, busy, onClose, onCreate, onCapture, onOpenLexeme }: {
  tab: AddTab;
  onTab(tab: AddTab): void;
  problems: YamlProblem[];
  busy: boolean;
  onClose(): void;
  onCreate(draft: string): void;
  onCapture(request: CaptureRequest): Promise<CaptureResult>;
  onOpenLexeme(id: string): void;
}) {
  const [capture, setCapture] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceTitle, setSourceTitle] = useState("");
  const [note, setNote] = useState("");
  const [draft, setDraft] = useState(YAML_TEMPLATE);
  const [working, setWorking] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [duplicates, setDuplicates] = useState<CaptureResult["duplicates"]>([]);
  const [details, setDetails] = useState(false);

  async function process() {
    setWorking(true);
    setFailure(null);
    setDuplicates([]);
    try {
      const result = await onCapture({
        text: capture,
        sourceUrl: sourceUrl.trim() || null,
        sourceTitle: sourceTitle.trim() || null,
        note: note.trim() || null
      });
      if (result.duplicates.length) {
        setDuplicates(result.duplicates);
        return;
      }
      if (!result.draft) {
        setFailure("The server built nothing from that text, so there is nothing to review.");
        return;
      }
      // The proposal becomes an ordinary editable document from here on.
      setDraft(yamlForDraft(result.draft));
      onTab("yaml");
    } catch (error) {
      setFailure(error instanceof Error ? error.message : "That text could not be processed.");
    } finally {
      setWorking(false);
    }
  }

  const ready = capture.trim().length > 0 && !working;

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
            onChange={(event) => { setCapture(event.target.value); setDuplicates([]); setFailure(null); }}
            placeholder="Se pican las verduras en dados de un centímetro y se reservan."
          />
          <p className="hint">
            Share the whole sentence — the word is picked out for you, and the sentence is kept as
            the place you met it. The entry is built for review and lands in <b>Inbox</b>.
          </p>

          <button className="capture-more" aria-expanded={details} onClick={() => setDetails(!details)}>
            {details ? "Fewer options" : "Where it came from, and what to ask for"}
          </button>
          {details && <div className="capture-details">
            <label className="label" htmlFor="captureUrl">Source link</label>
            <input
              id="captureUrl" value={sourceUrl} autoComplete="off" spellCheck={false}
              placeholder="https://example.com/receta" onChange={(event) => setSourceUrl(event.target.value)}
            />
            <label className="label" htmlFor="captureTitle">Where it came from</label>
            <input
              id="captureTitle" value={sourceTitle} autoComplete="off"
              placeholder="Receta — pisto manchego" onChange={(event) => setSourceTitle(event.target.value)}
            />
            <label className="label" htmlFor="captureNote">Anything to ask the generator</label>
            <input
              id="captureNote" value={note} autoComplete="off"
              placeholder="contrast it with picante" onChange={(event) => setNote(event.target.value)}
            />
          </div>}

          {duplicates.length > 0 && <div className="validation ok" role="status">
            <strong>{duplicates.length === 1 ? "You already have this word." : "You already have these."}</strong>
            <ul>
              {duplicates.map((duplicate) => <li key={duplicate.id}>
                <button className="link-btn" onClick={() => onOpenLexeme(duplicate.id)}>
                  {duplicate.headword}
                </button>
                {duplicate.shortGloss ? ` — ${duplicate.shortGloss}` : ""}
              </li>)}
            </ul>
            <span>Nothing was created. Open the entry to see what it already says.</span>
          </div>}
          {failure && <div className="validation bad" role="alert"><strong>{failure}</strong></div>}

          <div className="sheet-actions">
            <span className="spacer" />
            <button className="tb-btn" onClick={() => onTab("yaml")}>Write YAML instead</button>
            <button className="tb-btn primary" disabled={!ready} onClick={() => void process()}>
              {working ? "Building…" : "Process"}
            </button>
          </div>
        </> : <>
          <div className="code-wrap">
            <div className="code-head"><span className="label">new-entry.yaml</span></div>
            <EditorSurface value={draft} onChange={setDraft} minHeight="44vh" />
          </div>
          <ValidationPanel problems={problems} notice={null} />
          <div className="sheet-actions">
            <span className="spacer" />
            <button className="tb-btn" onClick={onClose}>Cancel</button>
            <button className="tb-btn primary" disabled={busy} onClick={() => onCreate(draft)}>
              {busy ? "Saving…" : "Validate & save"}
            </button>
          </div>
        </>}
      </div>
    </div>
  </div>;
}
