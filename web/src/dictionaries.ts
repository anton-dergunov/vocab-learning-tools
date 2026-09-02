/**
 * External dictionaries: what exists, what this device holds, and where a lookup is answered.
 *
 * The same shape as `sync.ts` and for the same reason — one module owns every call to the server's
 * dictionary routes and the schedule around them, so nothing else has to know whether a word came
 * off this device, off the server, or off the network.
 *
 * **Resolution order is: this device, then the server, then an online source.** A dictionary the
 * device has not stored is still usable when the server holds it and is reachable. This is the one
 * place Acervo reads through the network on purpose, and it does not contradict the offline-first
 * rule of design §04: an external dictionary is not the replica, so a failure here degrades a
 * reference surface rather than losing anything the owner wrote.
 */

import catalogueDocument from "../../dictionaries/catalogue.json";
import { AcervoApiError, backendSession, type OnlineArticle, type RemoteDictionary } from "./api";
import { Dictionary, blobSource, rangeSource, type DictionaryEntry } from "./dictionary";
import {
  createDictionaryStore,
  requestPersistence,
  type DictionaryMetadata,
  type InstalledDictionary
} from "./dictionaryStore";

export type DictionaryKind = "offline" | "online" | "link";

/** A row of `dictionaries/catalogue.json`. Acervo ships this list and never the data (§9). */
export interface CatalogueEntry {
  id: string;
  name: string;
  kind: DictionaryKind;
  tier: "fields" | "html";
  format?: string;
  sourceLang: string;
  targetLang: string;
  url: string;
  licence: string;
  attribution: string;
  approxDownloadBytes?: number;
  approxInstalledBytes?: number;
  options?: Record<string, unknown>;
  note?: string;
}

export const catalogue: CatalogueEntry[] = (catalogueDocument as { dictionaries: CatalogueEntry[] })
  .dictionaries;

const ENABLED_KEY = "acervo-dictionaries-enabled";
const CHANGED_EVENT = "acervo-dictionaries-changed";

/* ── per-device preferences ─────────────────────────────────────────────
   Which dictionaries are on describes *this device*, like the editor preferences and unlike the
   vocabulary — the phone and the laptop legitimately want different ones, and none of it is worth
   a round trip to the server. */

function enabledSet(): Set<string> {
  try {
    const stored = localStorage.getItem(ENABLED_KEY);
    return new Set(stored ? (JSON.parse(stored) as string[]) : []);
  } catch {
    return new Set();
  }
}

export function isEnabled(id: string): boolean {
  return enabledSet().has(id);
}

export function setEnabled(id: string, on: boolean): void {
  const enabled = enabledSet();
  if (on) enabled.add(id); else enabled.delete(id);
  try { localStorage.setItem(ENABLED_KEY, JSON.stringify([...enabled].sort())); }
  catch { /* a preference, not data */ }
  announce();
}

function announce(): void {
  try { window.dispatchEvent(new CustomEvent(CHANGED_EVENT)); } catch { /* not in a document */ }
}

export function onDictionariesChanged(handler: () => void): () => void {
  window.addEventListener(CHANGED_EVENT, handler);
  return () => window.removeEventListener(CHANGED_EVENT, handler);
}

/* ── grouping, for the Settings pane ────────────────────────────────────
   By primary subtag, so `zh`, `zh-Hans` and `zh-Hant` are one group rather than three. A source
   that serves any language — the two online ones, and most link-outs — sorts last under its own
   heading rather than being repeated under every language. */

export const ANY_LANGUAGE = "*";

export function primaryLanguage(tag: string): string {
  return tag === ANY_LANGUAGE ? ANY_LANGUAGE : tag.split("-")[0];
}

export function groupedByLanguage(entries: CatalogueEntry[] = catalogue): [string, CatalogueEntry[]][] {
  const groups = new Map<string, CatalogueEntry[]>();
  for (const entry of entries) {
    const key = primaryLanguage(entry.sourceLang);
    const group = groups.get(key);
    if (group) group.push(entry); else groups.set(key, [entry]);
  }
  return [...groups.entries()].sort(([left], [right]) => {
    if (left === ANY_LANGUAGE) return 1;
    if (right === ANY_LANGUAGE) return -1;
    return left.localeCompare(right);
  });
}

/* ── installing ─────────────────────────────────────────────────────────
   A download, three records written, and one request for storage persistence. Failure leaves every
   other dictionary untouched: nothing is written until all three files have arrived. */

const store = createDictionaryStore();

export interface InstallProgress {
  receivedBytes: number;
  totalBytes: number | null;
  stage: "metadata" | "index" | "payloads" | "saving";
}

export class DictionaryInstallError extends Error {
  constructor(message: string, readonly cause?: unknown) { super(message); }
}

async function fetchArtifact(
  id: string,
  extension: "dict" | "idx" | "json",
  onBytes?: (received: number, total: number | null) => void
): Promise<Blob> {
  const response = await fetch(backendSession.dictionaryFileUrl(id, extension), {
    headers: backendSession.dictionaryHeaders(),
    cache: "no-store"
  });
  if (response.status === 404) {
    throw new DictionaryInstallError("This server has not compiled that dictionary yet.");
  }
  if (!response.ok) {
    throw new DictionaryInstallError(`The dictionary could not be downloaded (${response.status}).`);
  }
  const declared = Number(response.headers.get("Content-Length"));
  const total = Number.isFinite(declared) && declared > 0 ? declared : null;
  if (!response.body || !onBytes) return response.blob();

  // Streamed rather than awaited whole, so a 40 MiB download can show progress instead of looking
  // frozen. The chunks are collected into one Blob because the store holds whole files.
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    received += value.length;
    onBytes(received, total);
  }
  return new Blob(chunks as BlobPart[]);
}

/**
 * Download a compiled dictionary onto this device.
 *
 * Deliberately all-or-nothing. A half-written dictionary would be indistinguishable from a whole
 * one at the point a lookup failed, so the store is only touched once every file has arrived.
 */
export async function install(id: string, onProgress?: (progress: InstallProgress) => void): Promise<InstalledDictionary> {
  const report = (stage: InstallProgress["stage"]) =>
    (receivedBytes: number, totalBytes: number | null) => onProgress?.({ receivedBytes, totalBytes, stage });
  try {
    onProgress?.({ receivedBytes: 0, totalBytes: null, stage: "metadata" });
    const metadata = JSON.parse(await (await fetchArtifact(id, "json")).text()) as DictionaryMetadata;
    const index = await fetchArtifact(id, "idx", report("index"));
    const blob = await fetchArtifact(id, "dict", report("payloads"));

    onProgress?.({ receivedBytes: blob.size + index.size, totalBytes: blob.size + index.size, stage: "saving" });
    await store.save({ id, metadata, blob, index });
  } catch (error) {
    if (error instanceof DictionaryInstallError) throw error;
    if (error instanceof AcervoApiError) throw new DictionaryInstallError(error.message, error);
    // A quota failure is the expected way this goes wrong on a phone, and it must say so rather
    // than surfacing as an opaque DOM exception.
    if (error instanceof DOMException && error.name === "QuotaExceededError") {
      throw new DictionaryInstallError(
        "There is not enough room on this device for that dictionary. Remove another one and try again.",
        error);
    }
    throw new DictionaryInstallError(
      "The dictionary could not be stored on this device. Nothing else was changed.", error);
  }
  // Asked for once, after a successful install: an origin with no interaction for seven days of
  // browser use is otherwise evicted, and a dictionary someone waited for should not evaporate.
  await requestPersistence();
  setEnabled(id, true);
  opened.delete(id);
  const saved = (await store.list()).find((record) => record.id === id);
  if (!saved) throw new DictionaryInstallError("The dictionary was downloaded but could not be read back.");
  announce();
  return saved;
}

export async function uninstall(id: string): Promise<void> {
  await store.remove(id);
  opened.delete(id);
  announce();
}

export const installed = (): Promise<InstalledDictionary[]> => store.list();

export async function listOnServer(): Promise<RemoteDictionary[]> {
  const { dictionaries } = await backendSession.listDictionaries();
  return dictionaries;
}

/* ── looking a word up ──────────────────────────────────────────────────
   The reader is the same either way; only the byte source differs. */

const opened = new Map<string, Promise<Dictionary>>();

async function openLocal(id: string): Promise<Dictionary | null> {
  const record = await store.read(id);
  if (!record) return null;
  return Dictionary.open(id, blobSource(record.blob), blobSource(record.index));
}

function openRemote(id: string, remote: RemoteDictionary): Promise<Dictionary> {
  const headers = backendSession.dictionaryHeaders();
  return Dictionary.open(
    id,
    rangeSource(backendSession.dictionaryFileUrl(id, "dict"), remote.blobBytes, headers),
    rangeSource(backendSession.dictionaryFileUrl(id, "idx"), remote.indexBytes, headers)
  );
}

/**
 * Open a dictionary, preferring the copy on this device.
 *
 * Cached by id, because what an open dictionary holds — the frame table and the restart table — is
 * a few hundred KiB, and re-reading it per lookup would be the only expensive part of a lookup.
 */
export async function openDictionary(id: string, remote?: RemoteDictionary): Promise<Dictionary | null> {
  const existing = opened.get(id);
  if (existing) return existing;
  const opening = (async () => {
    const local = await openLocal(id);
    if (local) return local;
    if (!remote) throw new DictionaryInstallError("That dictionary is not on this device.");
    return openRemote(id, remote);
  })();
  opened.set(id, opening);
  try {
    return await opening;
  } catch (error) {
    opened.delete(id);
    if (remote) throw error;
    return null;
  }
}

/**
 * Everything that could answer a lookup on this device: the shipped catalogue, plus anything
 * actually installed.
 *
 * The two are not the same set and treating them as one was a bug. The catalogue is a starting
 * list, not an allow-list — a server can compile a dictionary nobody added a row for — and an
 * installed artifact carries its own name, licence and languages, so it can describe itself.
 */
export function knownDictionaries(local: InstalledDictionary[]): CatalogueEntry[] {
  const known = new Map(catalogue.filter((entry) => entry.kind !== "link")
    .map((entry) => [entry.id, entry]));
  for (const record of local) {
    if (known.has(record.id)) continue;
    known.set(record.id, {
      id: record.id,
      name: record.metadata.name || record.id,
      kind: "offline",
      tier: record.metadata.tier,
      sourceLang: record.metadata.sourceLang,
      targetLang: record.metadata.targetLang,
      url: "",
      licence: record.metadata.licence,
      attribution: record.metadata.attribution,
      note: "Stored on this device, and not in the list Acervo ships."
    });
  }
  return [...known.values()];
}

export interface LookupResult {
  dictionaryId: string;
  name: string;
  attribution: string;
  licence: string;
  /** Where the answer came from, which the interface says out loud so nothing looks offline that isn't. */
  origin: "device" | "server" | "online";
  entry?: DictionaryEntry;
  articles?: OnlineArticle[];
}

/**
 * Every enabled dictionary that has something to say about `word`, best source first.
 *
 * One dictionary failing never takes the others down: a server that is unreachable simply means the
 * dictionaries this device holds answer alone, which is the behaviour the whole design is built for.
 */
export async function lookup(word: string, language?: string): Promise<LookupResult[]> {
  const enabled = enabledSet();
  const held = await installed();
  const rows = knownDictionaries(held).filter((entry) => enabled.has(entry.id)
    && (!language || entry.sourceLang === ANY_LANGUAGE
        || primaryLanguage(entry.sourceLang) === primaryLanguage(language)));
  const local = new Set(held.map((record) => record.id));

  let remote: RemoteDictionary[] = [];
  if (rows.some((entry) => entry.kind === "offline" && !local.has(entry.id))) {
    try { remote = await listOnServer(); } catch { remote = []; }
  }

  const results = await Promise.all(rows.map(async (row): Promise<LookupResult | null> => {
    const shared = { dictionaryId: row.id, name: row.name, attribution: row.attribution, licence: row.licence };
    try {
      if (row.kind === "online") {
        const answer = await backendSession.lookupOnlineDictionary(row.id, word, language);
        return answer.entries.length ? { ...shared, origin: "online", articles: answer.entries } : null;
      }
      const held = local.has(row.id);
      const description = remote.find((candidate) => candidate.id === row.id);
      if (!held && !description) return null;
      const dictionary = await openDictionary(row.id, description);
      const entry = await dictionary?.lookup(word);
      return entry ? { ...shared, origin: held ? "device" : "server", entry } : null;
    } catch {
      return null;
    }
  }));
  return results.filter((result): result is LookupResult => result !== null);
}
