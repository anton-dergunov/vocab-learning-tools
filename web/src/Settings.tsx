import { useEffect, useState } from "react";
import { formatDay } from "./format";
import { fetchMacRelease, type MacRelease } from "./macRelease";
import { installUpdate, type UpdateStage } from "./pwa";
import { appVersionLabel } from "./version";

export default function Settings({ update, email, syncedAt, onSignOut, onClose }: {
  update?: UpdateStage;
  email: string;
  syncedAt: string | null;
  onSignOut(): void;
  onClose(): void;
}) {
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

  return <div className="modal-backdrop" role="presentation"
    onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="settings" role="dialog" aria-modal="true" aria-labelledby="settings-title">
      <header><h2 id="settings-title">Settings</h2><button className="close" onClick={onClose} aria-label="Close settings">×</button></header>
      <div className="settings-body">
        {update === "ready" && <button className="update-action" onClick={() => void installUpdate()}><strong>Update Acervo</strong><span>The update is ready. Acervo will reopen with the new version.</span></button>}
        {update === "downloading" && <div className="update-status"><strong>Downloading an update…</strong><span>You can keep using Acervo while it finishes.</span></div>}
        {!update && <div className="update-status"><strong>Acervo is up to date</strong><span>This is the newest version available from this server.</span></div>}
        <div className="update-status">
          <strong>Signed in as {email}</strong>
          <span>{syncedAt ? `Vocabulary last received ${formatDay(syncedAt)}.` : "Showing the copy stored on this device."}</span>
        </div>
        {macRelease && <a className="download-action" href={macRelease.url} download={macRelease.file}>
          <strong>Download Acervo for macOS</strong>
          <span>Version {macRelease.version}, build {macRelease.build}</span>
        </a>}
        {macRelease === null && <div className="update-status"><strong>macOS application</strong><span>No native release has been published by this server yet.</span></div>}
        {macRelease === undefined && !releaseError && <div className="update-status"><strong>macOS application</strong><span>Checking for a native release…</span></div>}
        {releaseError && <div className="update-status"><strong>macOS application</strong><span>The native release could not be checked right now.</span></div>}
        <button className="tb-btn" onClick={onSignOut}>Sign out</button>
        <p className="version">Version {appVersionLabel()}</p>
      </div>
    </section>
  </div>;
}
