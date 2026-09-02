import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ANY_LANGUAGE,
  catalogue,
  groupedByLanguage,
  install,
  installed,
  isEnabled,
  knownDictionaries,
  listOnServer,
  setEnabled,
  uninstall,
  type CatalogueEntry,
  type InstallProgress
} from "./dictionaries";
import { storageReport, type InstalledDictionary, type StorageReport } from "./dictionaryStore";
import { languageOf } from "./languages";
import type { RemoteDictionary } from "./api";

/**
 * The Dictionaries pane: what exists, which of it is switched on here, and what this device holds.
 *
 * Acervo ships the *list* and never the data (§9), so every row is a set of facts and a URL until
 * someone asks for it. Turning a source on is a preference about this device — the phone and the
 * laptop legitimately want different ones — while storing one downloads a compiled artifact from
 * the server that built it.
 *
 * Licence and attribution are shown on every row because the obligation attaches to displaying the
 * content, and this is where someone decides to display it.
 */

function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return "—";
  if (bytes >= 2 ** 30) return `${(bytes / 2 ** 30).toFixed(1)} GB`;
  if (bytes >= 2 ** 20) return `${Math.round(bytes / 2 ** 20)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function languageName(code: string): string {
  return code === ANY_LANGUAGE ? "Any language" : languageOf(code).name;
}

function languageFlag(code: string): string {
  return code === ANY_LANGUAGE ? "🌐" : languageOf(code).flag;
}

function direction(entry: CatalogueEntry): string {
  const from = entry.sourceLang === ANY_LANGUAGE ? "any" : entry.sourceLang;
  const to = entry.targetLang === ANY_LANGUAGE ? "any" : entry.targetLang;
  return from === to ? `${from}, monolingual` : `${from} → ${to}`;
}

function progressLabel(progress: InstallProgress): string {
  const stage = progress.stage === "index" ? "index"
    : progress.stage === "payloads" ? "entries"
    : progress.stage === "saving" ? "storing" : "details";
  if (progress.stage === "saving") return "Storing on this device…";
  if (!progress.totalBytes) return `Downloading the ${stage}… ${formatBytes(progress.receivedBytes)}`;
  const percent = Math.round((progress.receivedBytes / progress.totalBytes) * 100);
  return `Downloading the ${stage}… ${percent}%`;
}

function DictionaryRow({ entry, local, remote, busy, onToggle, onInstall, onRemove }: {
  entry: CatalogueEntry;
  local: InstalledDictionary | undefined;
  remote: RemoteDictionary | undefined;
  busy: InstallProgress | null;
  onToggle(on: boolean): void;
  onInstall(): void;
  onRemove(): void;
}) {
  const [enabled, setLocalEnabled] = useState(() => isEnabled(entry.id));

  // A link-out has nothing to switch on and nothing to store: §7's third tier is an address.
  if (entry.kind === "link") {
    return <div className="dictionary-row">
      <span className="dictionary-main">
        <strong>{entry.name}</strong>
        <span>{direction(entry)} · opens on the web · {entry.licence}</span>
        {entry.note && <span className="dictionary-note">{entry.note}</span>}
      </span>
      <a className="tb-btn" href={entry.url} target="_blank" rel="noreferrer noopener">Open</a>
    </div>;
  }

  const state = local
    ? `stored here · ${local.metadata.entryCount.toLocaleString()} entries · ${formatBytes(local.bytes)}`
    : entry.kind === "online" ? "looked up as you need it, through your server"
    : remote ? `on your server · ${remote.entryCount.toLocaleString()} entries`
    : "not compiled on your server yet";

  return <div className="dictionary-row">
    <label className="dictionary-switch">
      <input
        type="checkbox" checked={enabled}
        onChange={(event) => { setLocalEnabled(event.target.checked); onToggle(event.target.checked); }}
      />
      <span className="dictionary-main">
        <strong>{entry.name}</strong>
        <span>{direction(entry)} · {entry.licence} · {state}</span>
        {entry.note && <span className="dictionary-note">{entry.note}</span>}
        {busy && <span className="dictionary-progress" role="status">{progressLabel(busy)}</span>}
      </span>
    </label>
    {entry.kind === "offline" && !local && <button
      className="tb-btn" disabled={!!busy || !remote}
      title={remote ? undefined : "Your server has not compiled this dictionary yet."}
      onClick={onInstall}
    >Store on this device</button>}
    {entry.kind === "offline" && local
      && <button className="tb-btn danger" disabled={!!busy} onClick={onRemove}>Remove</button>}
  </div>;
}

export default function DictionaryPanel({ onNotify }: { onNotify(message: string): void }) {
  const [local, setLocal] = useState<InstalledDictionary[]>([]);
  const [remote, setRemote] = useState<RemoteDictionary[] | null>(null);
  const [storage, setStorage] = useState<StorageReport | null>(null);
  const [busy, setBusy] = useState<Record<string, InstallProgress>>({});

  const refresh = useCallback(async () => {
    setLocal(await installed());
    setStorage(await storageReport());
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  useEffect(() => {
    // What the server has compiled is the one thing here that needs it to be reachable. Failing is
    // ordinary: the rows still render, and the ones already stored here still work.
    let cancelled = false;
    void listOnServer()
      .then((found) => { if (!cancelled) setRemote(found); })
      .catch(() => { if (!cancelled) setRemote([]); });
    return () => { cancelled = true; };
  }, []);

  // The catalogue plus anything already stored here, because a server can compile a dictionary the
  // shipped list does not name and it would be strange for the pane to deny it exists.
  const groups = useMemo(
    () => groupedByLanguage([...knownDictionaries(local),
                             ...catalogue.filter((entry) => entry.kind === "link")]),
    [local]);

  async function storeLocally(entry: CatalogueEntry) {
    try {
      await install(entry.id, (progress) => setBusy((current) => ({ ...current, [entry.id]: progress })));
      onNotify(`${entry.name} is stored on this device.`);
    } catch (error) {
      onNotify(error instanceof Error ? error.message : "That dictionary could not be stored.");
    } finally {
      setBusy(({ [entry.id]: _done, ...rest }) => rest);
      await refresh();
    }
  }

  async function removeLocally(entry: CatalogueEntry) {
    await uninstall(entry.id);
    onNotify(`${entry.name} was removed from this device. Every other dictionary is untouched.`);
    await refresh();
  }

  const storedCount = local.length;
  const storedBytes = local.reduce((total, record) => total + record.bytes, 0);

  return <section className="config-section">
    <h3>Dictionaries</h3>
    <p className="config-help">
      Acervo ships this list, not the dictionaries themselves — each one is downloaded from whoever
      publishes it. Switching one on is a choice about <em>this</em> device, so your phone and your
      laptop can carry different ones. A dictionary stored here keeps working with the server
      unreachable; one that is only on the server needs a connection.
    </p>

    <div className="update-status">
      <strong>
        {storedCount === 0 ? "Nothing stored on this device yet"
          : `${storedCount} ${storedCount === 1 ? "dictionary" : "dictionaries"} on this device · ${formatBytes(storedBytes)}`}
      </strong>
      <span>
        {storage?.quotaBytes
          ? `${formatBytes(storage.usedBytes)} of about ${formatBytes(storage.quotaBytes)} used by Acervo on this device.`
          : "This browser does not say how much room it will give Acervo."}
        {storage?.persisted
          ? " Storage here is protected from being cleared automatically."
          : " Storage here may be cleared if you do not use Acervo for a while."}
      </span>
    </div>

    {remote === null && <p className="config-help">Asking your server which dictionaries it has compiled…</p>}
    {remote?.length === 0 && <p className="config-help">
      Your server has not compiled any dictionaries yet, so nothing can be stored on this device.
      Build one on the server with <code>acervo-worker dictionary build --id &lt;name&gt;</code>.
    </p>}

    {groups.map(([code, entries]) => <div key={code} className="dictionary-group">
      <h4>{languageFlag(code)} {languageName(code)}</h4>
      {entries.map((entry) => <DictionaryRow
        key={entry.id}
        entry={entry}
        local={local.find((record) => record.id === entry.id)}
        remote={remote?.find((record) => record.id === entry.id)}
        busy={busy[entry.id] ?? null}
        onToggle={(on) => setEnabled(entry.id, on)}
        onInstall={() => void storeLocally(entry)}
        onRemove={() => void removeLocally(entry)}
      />)}
    </div>)}
  </section>;
}
