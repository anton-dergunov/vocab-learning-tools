import { useEffect, useState } from "react";
import { installUpdate, isNativeHost, UPDATE_EVENT, updateStage, type UpdateStage } from "./pwa";
import { appVersionLabel } from "./version";
import "./styles.css";

function GearIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z"/><path d="M19 13.3v-2.6l-2.1-.7a7 7 0 0 0-.7-1.6l1-2-1.8-1.8-2 1A7 7 0 0 0 11.7 5L11 3H8.5l-.7 2a7 7 0 0 0-1.7.7l-2-1-1.8 1.8 1 2a7 7 0 0 0-.7 1.6l-2.1.7v2.6l2.1.7c.2.6.4 1.1.7 1.6l-1 2 1.8 1.8 2-1c.5.3 1.1.6 1.7.7l.7 2H11l.7-2c.6-.2 1.1-.4 1.7-.7l2 1 1.8-1.8-1-2c.3-.5.6-1 .7-1.6l2.1-.8Z"/></svg>;
}

function Settings({ update, onClose }: { update?: UpdateStage; onClose(): void }) {
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="settings" role="dialog" aria-modal="true" aria-labelledby="settings-title">
      <header><h2 id="settings-title">Settings</h2><button className="close" onClick={onClose} aria-label="Close settings">×</button></header>
      <div className="settings-body">
        {update === "ready" && <button className="update-action" onClick={() => void installUpdate()}><strong>Update Acervo</strong><span>The update is ready. Acervo will reopen with the new version.</span></button>}
        {update === "downloading" && <div className="update-status"><strong>Downloading an update…</strong><span>You can keep using Acervo while it finishes.</span></div>}
        {!update && <div className="update-status"><strong>Acervo is up to date</strong><span>This is the newest version available from this server.</span></div>}
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
