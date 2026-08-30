import { useEffect, useState } from "react";
import { TopicEditor, VocabularyEditor } from "./Configuration";
import { fetchMacRelease, type MacRelease } from "./macRelease";
import { installUpdate, isNativeHost, type UpdateStage } from "./pwa";
import type { ReplicaSnapshot } from "./repository";
import { syncEngine, type SyncStatus } from "./sync";
import { SyncPanel } from "./SyncStatus";
import { appVersionLabel } from "./version";
import { editorPreferences, setEditorPreference, type EditorPreferences } from "./YamlPane";

/** Typing the word is the point: this is the one action that cannot be undone by re-syncing. */
const CONFIRMATION = "DELETE";

type Page = "general" | "vocabularies" | "topics" | "editor" | "sync" | "data";

export default function Settings({ update, email, status, snapshot, language, onSignOut, onClose, onNotify, onChanged }: {
  update?: UpdateStage;
  email: string;
  status: SyncStatus;
  snapshot: ReplicaSnapshot | null;
  /** Which vocabulary the topic counts are shown for — the one the list is currently filtered to. */
  language: string;
  onSignOut(): void;
  onClose(): void;
  onNotify(message: string): void;
  onChanged(): void;
}) {
  /* On the Mac the app updates itself and remembers its own server address, so repeating either
     here would offer a second, conflicting control for something this window does not own. What
     stays is everything about the vocabulary, which the native host deliberately does not own. */
  const native = isNativeHost();
  const [macRelease, setMacRelease] = useState<MacRelease | null>();
  const [releaseError, setReleaseError] = useState(false);
  const [page, setPage] = useState<Page>("general");
  const [editor, setEditor] = useState(editorPreferences);

  function changeEditor(name: keyof EditorPreferences, value: boolean) {
    setEditorPreference(name, value);
    setEditor(editorPreferences());
  }

  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState("");
  const [working, setWorking] = useState(false);

  const liveLexemes = snapshot?.lexemes.filter((lexeme) => !lexeme.deleted).length ?? 0;
  const liveTopics = snapshot?.topics.filter((topic) => !topic.deleted).length ?? 0;

  async function run(action: () => Promise<void>, failure: string) {
    setWorking(true);
    try { await action(); }
    catch (error) { onNotify(error instanceof Error ? error.message : failure); }
    finally { setWorking(false); }
  }

  /**
   * `syncNow` reports by resolving, not by throwing, so `run` would show nothing either way. On a
   * server that fails every request the panel's text never changes, and the button looked broken.
   */
  async function refresh() {
    setWorking(true);
    try {
      const result = await syncEngine.syncNow(true);
      onNotify(result.state === "idle"
        ? "Up to date with the server."
        : result.message ?? "The vocabulary could not be refreshed.");
    } finally { setWorking(false); }
  }

  async function deleteEverything() {
    await run(() => syncEngine.resetVocabulary(), "The vocabulary could not be deleted.");
    setConfirming(false);
    setTyped("");
  }

  useEffect(() => {
    if (native) return;
    const controller = new AbortController();
    void fetchMacRelease(controller.signal)
      .then(setMacRelease)
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setReleaseError(true);
      });
    return () => controller.abort();
  }, [native]);

  const pages: { id: Page; label: string }[] = [
    { id: "general", label: "General" },
    { id: "vocabularies", label: "Vocabularies" },
    { id: "topics", label: "Topics" },
    { id: "editor", label: "Editor" },
    { id: "sync", label: "Sync" },
    { id: "data", label: "Data" }
  ];

  return <div className="modal-backdrop" role="presentation"
    onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="settings" role="dialog" aria-modal="true" aria-labelledby="settings-title">
      <header><h2 id="settings-title">Settings</h2><button className="close" onClick={onClose} aria-label="Close settings">×</button></header>

      {/* One page at a time. Everything here used to be one column, which grew past the window the
          moment topics and vocabularies became editable — and the dialog could not scroll, so the
          controls at the bottom were simply unreachable. */}
      <nav className="settings-nav" role="tablist" aria-label="Settings sections">
        {pages.map((entry) => <button
          key={entry.id} role="tab" id={`settings-tab-${entry.id}`}
          aria-selected={page === entry.id} aria-controls="settings-panel"
          className={page === entry.id ? "on" : ""}
          onClick={() => setPage(entry.id)}
        >{entry.label}</button>)}
      </nav>

      <div className="settings-body" id="settings-panel" role="tabpanel" aria-labelledby={`settings-tab-${page}`}>
        {page === "general" && <>
          <div className="update-status">
            <strong>Signed in as {email}</strong>
            <span>{liveLexemes} {liveLexemes === 1 ? "entry" : "entries"} across {liveTopics} {liveTopics === 1 ? "topic" : "topics"} on this device.</span>
          </div>
          {!native && update === "ready" && <button className="update-action" onClick={() => void installUpdate()}><strong>Update Acervo</strong><span>The update is ready. Acervo will reopen with the new version.</span></button>}
          {!native && update === "downloading" && <div className="update-status"><strong>Downloading an update…</strong><span>You can keep using Acervo while it finishes.</span></div>}
          {!native && !update && <div className="update-status"><strong>Acervo is up to date</strong><span>This is the newest version available from this server.</span></div>}
          {!native && macRelease && <a className="download-action" href={macRelease.url} download={macRelease.file}>
            <strong>Download Acervo for macOS</strong>
            <span>Version {macRelease.version}, build {macRelease.build}</span>
          </a>}
          {!native && macRelease === null && <div className="update-status"><strong>macOS application</strong><span>No native release has been published by this server yet.</span></div>}
          {!native && macRelease === undefined && !releaseError && <div className="update-status"><strong>macOS application</strong><span>Checking for a native release…</span></div>}
          {!native && releaseError && <div className="update-status"><strong>macOS application</strong><span>The native release could not be checked right now.</span></div>}
          {native && <div className="update-status">
            <strong>Updates and server address</strong>
            <span>Acervo ▸ Settings, in the menu bar.</span>
          </div>}
          <button className="tb-btn" onClick={onSignOut}>Sign out</button>
          <p className="version">Version {appVersionLabel()}</p>
        </>}

        {page === "editor" && <section className="config-section">
          <h3>YAML editor</h3>
          <p className="config-help">
            How entries are shown when you read or edit them as YAML. These describe this device,
            not your vocabulary, so they are not shared with your other devices.
          </p>
          <label className="config-switch">
            <input
              type="checkbox" checked={editor.wrap}
              onChange={(event) => changeEditor("wrap", event.target.checked)}
            />
            <span>
              <strong>Wrap long lines</strong>
              <span>Off, a long definition runs past the edge and the editor scrolls sideways to it.</span>
            </span>
          </label>
          <label className="config-switch">
            <input
              type="checkbox" checked={editor.numbers}
              onChange={(event) => changeEditor("numbers", event.target.checked)}
            />
            <span>
              <strong>Show line numbers</strong>
              <span>Useful when a document is refused: the reason names the line it is on.</span>
            </span>
          </label>
        </section>}

        {page === "vocabularies" && snapshot && <VocabularyEditor snapshot={snapshot} onNotify={onNotify} onChanged={onChanged} />}
        {page === "topics" && snapshot && <TopicEditor snapshot={snapshot} language={language} onNotify={onNotify} onChanged={onChanged} />}

        {page === "sync" && <SyncPanel
          status={status}
          lexemeCount={liveLexemes}
          onSyncNow={() => void refresh()}
          onDownloadAgain={() => void run(() => syncEngine.downloadAgain(), "The vocabulary could not be downloaded again.")}
        />}

        {page === "data" && <div className="danger-zone">
          <h3>Delete all vocabulary</h3>
          {!confirming && <>
            <p>Removes every entry from the server and from every device you use. This needs a
              connection to the server, like any other change.</p>
            <button className="tb-btn danger" onClick={() => setConfirming(true)}>Delete all vocabulary…</button>
          </>}
          {confirming && <>
            <p role="alert">
              This deletes <strong>{liveLexemes} {liveLexemes === 1 ? "entry" : "entries"}</strong> and
              everything attached to them — senses, examples, the sentences you captured, and study
              history. Your other devices are emptied the next time they sync.
            </p>
            <label htmlFor="delete-confirmation">Type {CONFIRMATION} to confirm</label>
            <input
              id="delete-confirmation" value={typed} autoComplete="off"
              onChange={(event) => setTyped(event.target.value)}
            />
            <div className="sync-actions">
              <button className="tb-btn" onClick={() => { setConfirming(false); setTyped(""); }}>Cancel</button>
              <button
                className="tb-btn danger" disabled={typed.trim() !== CONFIRMATION || working}
                onClick={() => void deleteEverything()}
              >Delete everything</button>
            </div>
          </>}
        </div>}

        {(page === "vocabularies" || page === "topics") && !snapshot
          && <p className="config-help">Opening your vocabulary…</p>}
      </div>
    </section>
  </div>;
}
