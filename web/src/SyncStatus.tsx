import { useState } from "react";
import { AlertIcon, CloudIcon, CloudOffIcon, SyncIcon } from "./icons";
import { relativeTime } from "./format";
import type { SyncStatus } from "./sync";

/** Typed, not clicked, when the copy being discarded may be the only complete one left. */
const CONFIRMATION = "REPLACE";

type Tone = "synced" | "syncing" | "offline" | "blocked";

const TONES: Record<SyncStatus["state"], Tone> = {
  idle: "synced", syncing: "syncing", offline: "offline", serverError: "blocked",
  blocked: "blocked", datasetChanged: "blocked", signedOut: "offline"
};

const LABELS: Record<SyncStatus["state"], string> = {
  idle: "Up to date with the server",
  syncing: "Checking the server for changes",
  offline: "Offline — showing the copy stored on this device",
  // Distinct from offline on purpose. The server answering and failing is a fault someone has to
  // go and fix; calling it "offline" points the owner at their network instead of at the server.
  serverError: "The server is reachable but returned an error",
  blocked: "Synchronisation stopped: this app needs updating",
  datasetChanged: "Synchronisation stopped: the server database changed",
  signedOut: "Not signed in"
};

/** The topbar indicator. Deliberately quiet: offline is a normal state here, not a failure. */
export function SyncChip({ status, onOpen }: { status: SyncStatus; onOpen(): void }) {
  const tone = TONES[status.state];
  return <button className={`tb-btn sync-chip ${tone}`} onClick={onOpen} aria-label={LABELS[status.state]} title={LABELS[status.state]}>
    {tone === "syncing" ? <SyncIcon /> : tone === "blocked" ? <AlertIcon /> : tone === "offline" ? <CloudOffIcon /> : <CloudIcon />}
  </button>;
}

/** The detail, shown inside Settings — where someone goes to find out why a device stopped. */
export function SyncPanel({ status, lexemeCount, onSyncNow, onDownloadAgain }: {
  status: SyncStatus;
  lexemeCount: number;
  onSyncNow(): void;
  onDownloadAgain(): void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState("");
  const stopped = status.state === "blocked" || status.state === "datasetChanged";
  // Normally this discards a cache the server can rebuild. After the server database changed
  // identity it may instead discard the most complete surviving copy, so the gate is raised.
  const irreversible = status.state === "datasetChanged";
  const ready = !irreversible || typed.trim() === CONFIRMATION;

  function download() {
    setConfirming(false);
    setTyped("");
    onDownloadAgain();
  }
  return <div className="sync-panel">
    <div className="update-status">
      <strong>{LABELS[status.state]}</strong>
      <span>
        Received {relativeTime(status.lastPulledAt)}
        {status.lastWroteAt ? ` · last change saved ${relativeTime(status.lastWroteAt)}` : ""}
        {status.cursor > 0 ? ` · revision ${status.cursor}` : ""}
      </span>
    </div>
    {!status.persistent && <p className="sync-warning" role="status">
      This device could not open its local storage, so the vocabulary is held in memory for this
      session only and will not be here after a reload.
    </p>}
    {status.state === "datasetChanged" && <p className="sync-warning" role="alert">
      Nothing has been changed on this device. Its copy may be more complete than the server's, so
      choose deliberately: download the server's copy over it, or rebuild the server from this
      device before continuing.
    </p>}
    {status.message && status.state !== "idle" && <p className="sync-message">{status.message}</p>}
    <div className="sync-actions">
      <button className="tb-btn" onClick={onSyncNow} disabled={status.state === "syncing" || stopped}>Sync now</button>
      {!confirming && <button className="tb-btn" onClick={() => setConfirming(true)}>
        Replace this device's copy with the server's…
      </button>}
    </div>
    {confirming && <div className="replace-copy">
      <p role="alert">
        This deletes the {lexemeCount} {lexemeCount === 1 ? "entry" : "entries"} held here and
        downloads the server's copy in their place.
        {irreversible
          ? " The server database was rebuilt, so it may hold fewer than this device does. Nothing here can be recovered afterwards."
          : " Nothing is lost: the server has everything this device does."}
      </p>
      {irreversible && <>
        <label htmlFor="replace-confirmation">Type {CONFIRMATION} to confirm</label>
        <input
          id="replace-confirmation" value={typed} autoComplete="off"
          onChange={(event) => setTyped(event.target.value)}
        />
      </>}
      <div className="sync-actions">
        <button className="tb-btn" onClick={() => { setConfirming(false); setTyped(""); }}>Cancel</button>
        <button className="tb-btn danger" disabled={!ready} onClick={download}>Replace this device's copy</button>
      </div>
    </div>}
  </div>;
}
