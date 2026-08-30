import { useMemo, useState } from "react";
import type { CaptureRequest, CaptureResult } from "./api";
import Composer from "./Composer";
import type { VocabularyGraph } from "./domain";
import { CaretIcon, CloseIcon } from "./icons";
import LexemeArticle from "./LexemeArticle";
import { articleFromDraft, type Article } from "./selectors";
import { EditorSurface, useEditorPreferences, ValidationPanel } from "./YamlPane";
import { parseArticle, YAML_TEMPLATE, yamlForDraft, YamlProblems, type YamlProblem } from "./yaml";

export type AddTab = "capture" | "article" | "yaml";

/**
 * Capture (§05), the rendered proposal, and the YAML escape hatch — one view, because they are three
 * views of one thing.
 *
 * A view rather than a dialog: composing an entry is work, not an interruption, and it wants the
 * whole content area — which is also the only shape that survives a phone, where a centred overlay
 * never had room for a header, an editor and its buttons at once.
 *
 * Processing does not save anything. It returns a proposal, which is rendered as an ordinary
 * article — the same component a stored entry uses, so approving a generated entry is reading the
 * thing you will get rather than reading its serialization. YAML sits behind it as the edit surface
 * and stays the document of record here: the Article tab is derived from the editor text on every
 * keystroke, so the preview and the editor cannot drift apart. Saving goes by exactly the path a
 * hand-written document takes, so there is one writer, one validator and one diff.
 */
export default function AddView({
  tab, onTab, graph, problems, busy, onClose, onCreate, onCapture, onOpenLexeme, onNotify
}: {
  tab: AddTab;
  onTab(tab: AddTab): void;
  /** The replica, for resolving the topic names a document carries. Null only during startup. */
  graph: VocabularyGraph | null;
  problems: YamlProblem[];
  busy: boolean;
  onClose(): void;
  onCreate(draft: string): void;
  onCapture(request: CaptureRequest): Promise<CaptureResult>;
  onOpenLexeme(id: string): void;
  onNotify(message: string): void;
}) {
  const [capture, setCapture] = useState("");
  const [headword, setHeadword] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceTitle, setSourceTitle] = useState("");
  const [note, setNote] = useState("");
  const [draft, setDraft] = useState(YAML_TEMPLATE);
  const [working, setWorking] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [duplicates, setDuplicates] = useState<CaptureResult["duplicates"]>([]);
  const { wrap, numbers } = useEditorPreferences();

  /** Nothing has been proposed or written yet, so there is nothing to render. */
  const untouched = draft === YAML_TEMPLATE;

  /**
   * The preview is derived from the editor text rather than kept beside it. That is what makes
   * "read it, then go fix it in YAML, then read it again" work without the two ever disagreeing.
   */
  const preview = useMemo<{ article: Article | null; problems: YamlProblem[] }>(() => {
    if (!graph || untouched) return { article: null, problems: [] };
    try {
      return { article: articleFromDraft(graph, parseArticle(draft)), problems: [] };
    } catch (error) {
      if (error instanceof YamlProblems) return { article: null, problems: error.problems };
      return { article: null, problems: [{ line: null, message: String(error) }] };
    }
  }, [graph, draft, untouched]);

  async function process() {
    setWorking(true);
    setFailure(null);
    setDuplicates([]);
    try {
      const result = await onCapture({
        // The word alone is a complete capture. Sending it as the text too keeps that from needing
        // its own request shape — the server resolves what it is given, and here that is the word.
        text: capture.trim() || headword.trim(),
        headword: headword.trim() || null,
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
      // The proposal becomes an ordinary editable document from here on, and is read as an article.
      setDraft(yamlForDraft(result.draft));
      onTab("article");
    } catch (error) {
      setFailure(error instanceof Error ? error.message : "That text could not be processed.");
    } finally {
      setWorking(false);
    }
  }

  const head = <>
    <h2>Add a word</h2>
    <span className="spacer" />
    <div className="seg">
      <button className={tab === "capture" ? "on" : ""} onClick={() => onTab("capture")}>Capture</button>
      <button className={tab === "article" ? "on" : ""} onClick={() => onTab("article")}>Article</button>
      <button className={tab === "yaml" ? "on" : ""} onClick={() => onTab("yaml")}>YAML</button>
    </div>
    <button className="icon-btn" aria-label="Close" onClick={onClose}><CloseIcon /></button>
  </>;

  if (tab === "capture") {
    return <Composer
      label="Add a word"
      head={head}
      fill={false}
      actions={<>
        {/* Pinned with the buttons on purpose: a refusal you have to go looking for is one you miss. */}
        {duplicates.length > 0 && <div className="validation ok" role="status">
          <strong>{duplicates.length === 1 ? "You already have this word." : "You already have these."}</strong>
          <ul>
            {duplicates.map((duplicate) => <li key={duplicate.id}>
              <button className="link-btn" onClick={() => onOpenLexeme(duplicate.id)}>{duplicate.headword}</button>
              {duplicate.shortGloss ? ` — ${duplicate.shortGloss}` : ""}
            </li>)}
          </ul>
          <span>Nothing was created. Open the entry to see what it already says.</span>
        </div>}
        {failure && <div className="validation bad" role="alert"><strong>{failure}</strong></div>}
        <div className="composer-buttons">
          <span className="spacer" />
          <button className="tb-btn" onClick={() => onTab("yaml")}>Write YAML instead</button>
          <button
            className="tb-btn primary" disabled={(!capture.trim() && !headword.trim()) || working}
            onClick={() => void process()}
          >
            {working ? "Building…" : "Process"}
          </button>
        </div>
      </>}
    >
      <label className="label" htmlFor="captureText">Paste a word, or the sentence you met it in</label>
      <textarea
        className="capture-area" id="captureText" style={{ marginTop: 8 }} value={capture}
        onChange={(event) => { setCapture(event.target.value); setDuplicates([]); setFailure(null); }}
        placeholder="Se pican las verduras en dados de un centímetro y se reservan."
      />

      <label className="label" htmlFor="captureWord" style={{ marginTop: 14 }}>
        Which word? <span className="opt">optional</span>
      </label>
      <input
        className="capture-word" id="captureWord" value={headword} autoComplete="off"
        placeholder="picar" onChange={(event) => { setHeadword(event.target.value); setFailure(null); }}
      />

      <p className="hint">
        Share the whole sentence — the word is picked out for you unless you name it above, and the
        sentence is kept as the place you met it. The entry is built for review and lands in{" "}
        <b>Inbox</b>.{!untouched && " Processing again replaces the draft you have."}
      </p>

      <details className="fold capture-fold">
        <summary>
          <span className="caret"><CaretIcon /></span>
          <span className="label">Where it came from, and what to ask for</span>
        </summary>
        <div className="fold-body capture-details">
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
        </div>
      </details>
    </Composer>;
  }

  if (tab === "article") {
    return <Composer
      label="Add a word"
      head={head}
      fill={false}
      actions={<>
        <ValidationPanel problems={preview.problems.length ? preview.problems : problems} notice={null} />
        <div className="composer-buttons">
          <span className="spacer" />
          <button className="tb-btn" onClick={onClose}>Cancel</button>
          <button className="tb-btn" onClick={() => onTab("yaml")}>Edit YAML</button>
          <button
            className="tb-btn primary" disabled={busy || !preview.article}
            onClick={() => onCreate(draft)}
          >
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </>}
    >
      {preview.article
        ? <div className="article-preview">
            {/* No delete, and no storage footer: there is nothing stored to delete or describe. */}
            <LexemeArticle article={preview.article} onUnsupported={onNotify} meta={false} />
          </div>
        : <p className="empty">
            {untouched
              ? "Nothing to preview yet — process a capture, or write the document yourself."
              : "This document cannot be read, so there is nothing to show. Fix it in YAML."}
          </p>}
    </Composer>;
  }

  return <Composer
    label="Add a word"
    head={head}
    fill
    actions={<>
      <ValidationPanel problems={problems} notice={null} />
      <div className="composer-buttons">
        <span className="spacer" />
        <button className="tb-btn" onClick={onClose}>Cancel</button>
        <button className="tb-btn primary" disabled={busy} onClick={() => onCreate(draft)}>
          {busy ? "Saving…" : "Validate & save"}
        </button>
      </div>
    </>}
  >
    <div className="code-wrap">
      <div className="code-head"><span className="label">new-entry.yaml</span></div>
      <EditorSurface value={draft} onChange={setDraft} wrap={wrap} numbers={numbers} />
    </div>
  </Composer>;
}
