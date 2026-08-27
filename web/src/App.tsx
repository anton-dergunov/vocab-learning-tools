import { useEffect, useState } from "react";
import { fetchMacRelease, type MacRelease } from "./macRelease";
import { installUpdate, isNativeHost, UPDATE_EVENT, updateStage, type UpdateStage } from "./pwa";
import { appVersionLabel } from "./version";
import "./styles.css";

function GearIcon() {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M10.03 5.34 10.44 2.68h3.12l.41 2.66a6.95 6.95 0 0 1 1.35.55l2.17-1.58 2.2 2.2-1.58 2.17a6.95 6.95 0 0 1 .55 1.35l2.66.41v3.12l-2.66.41a6.95 6.95 0 0 1-.55 1.35l1.58 2.17-2.2 2.2-2.17-1.58a6.95 6.95 0 0 1-1.35.55l-.41 2.66h-3.12l-.41-2.66a6.95 6.95 0 0 1-1.35-.55l-2.17 1.58-2.2-2.2 1.58-2.17a6.95 6.95 0 0 1-.55-1.35l-2.66-.41v-3.12l2.66-.41a6.95 6.95 0 0 1 .55-1.35L4.31 6.51l2.2-2.2 2.17 1.58a6.95 6.95 0 0 1 1.35-.55Z" />
    <circle cx="12" cy="12" r="3.1" />
  </svg>;
}

function Settings({ update, onClose }: { update?: UpdateStage; onClose(): void }) {
  const [macRelease, setMacRelease] = useState<MacRelease | null>();
  const [releaseError, setReleaseError] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    void fetchMacRelease(controller.signal)
      .then(setMacRelease)
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setReleaseError(true);
      });
    return () => controller.abort();
  }, []);

  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="settings" role="dialog" aria-modal="true" aria-labelledby="settings-title">
      <header><h2 id="settings-title">Settings</h2><button className="close" onClick={onClose} aria-label="Close settings">×</button></header>
      <div className="settings-body">
        {update === "ready" && <button className="update-action" onClick={() => void installUpdate()}><strong>Update Acervo</strong><span>The update is ready. Acervo will reopen with the new version.</span></button>}
        {update === "downloading" && <div className="update-status"><strong>Downloading an update…</strong><span>You can keep using Acervo while it finishes.</span></div>}
        {!update && <div className="update-status"><strong>Acervo is up to date</strong><span>This is the newest version available from this server.</span></div>}
        {macRelease && <a className="download-action" href={macRelease.url} download={macRelease.file}>
          <strong>Download Acervo for macOS</strong>
          <span>Version {macRelease.version}, build {macRelease.build}</span>
        </a>}
        {macRelease === null && <div className="update-status"><strong>macOS application</strong><span>No native release has been published by this server yet.</span></div>}
        {macRelease === undefined && !releaseError && <div className="update-status"><strong>macOS application</strong><span>Checking for a native release…</span></div>}
        {releaseError && <div className="update-status"><strong>macOS application</strong><span>The native release could not be checked right now.</span></div>}
        <p className="version">Version {appVersionLabel()}</p>
      </div>
    </section>
  </div>;
}

export default function App() {
  const native = isNativeHost();
  const [settings, setSettings] = useState(false);
  const [update, setUpdate] = useState<UpdateStage | undefined>(() => updateStage());

  useEffect(() => {
    const changed = (event: Event) => setUpdate((event as CustomEvent<UpdateStage | undefined>).detail);
    window.addEventListener(UPDATE_EVENT, changed);
    return () => window.removeEventListener(UPDATE_EVENT, changed);
  }, []);

  return <main className="app-shell">
    {!native && <button className={`gear ${update === "ready" ? "has-update" : ""}`} onClick={() => setSettings(true)} aria-label={update === "ready" ? "Open settings; an update is ready" : "Open settings"}><GearIcon /></button>}
    <h1>Acervo</h1>
    {settings && <Settings update={update} onClose={() => setSettings(false)} />}
  </main>;
}
