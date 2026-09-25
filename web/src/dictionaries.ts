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
 * rule of `docs/architecture/sync.md`: an external dictionary is not the replica, so a failure here degrades a
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
import { glossOf, type ExternalRow, type RawHit } from "./externalEntries";

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

const DISABLED_KEY = "acervo-dictionaries-off";
const CHANGED_EVENT = "acervo-dictionaries-changed";

/* ── per-device preferences ─────────────────────────────────────────────
   Which dictionaries are on describes *this device*, like the editor preferences and unlike the
   vocabulary — the phone and the laptop legitimately want different ones, and none of it is worth
   a round trip to the server.

   **What is stored is what is switched OFF.** It was the other way round, and that was a bug with
   a long fuse: an online source can never be "installed", so nothing ever added it to a set of
   switched-on ids, and a search that had just promised "press ⏎ to look this up online" then
   quietly found nothing to ask. Anything Acervo can actually reach — stored here, compiled on the
   server, or answerable online — is on until someone says otherwise, which is also the answer most
   people would expect after going to the trouble of storing a dictionary. */

function disabledSet(): Set<string> {
  try {
    const stored = localStorage.getItem(DISABLED_KEY);
    return new Set(stored ? (JSON.parse(stored) as string[]) : []);
  } catch {
    return new Set();
  }
}

export function isEnabled(id: string): boolean {
  return !disabledSet().has(id);
}

export function setEnabled(id: string, on: boolean): void {
  const disabled = disabledSet();
  if (on) disabled.delete(id); else disabled.add(id);
  try { localStorage.setItem(DISABLED_KEY, JSON.stringify([...disabled].sort())); }
  catch { /* a preference, not data */ }
  announce();
}

function announce(): void {
  // Which dictionaries can answer has just changed, so the held resolution is stale by definition.
  sourceCache = null;
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
  // Deliberately not switching anything on: a dictionary is on unless someone switched it off, so
  // storing one that had been switched off keeps that choice rather than quietly undoing it.
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
  /** The catalogue's own answer, for a source whose payload does not carry one. */
  sourceLang: string;
  /** Where the answer came from, which the interface says out loud so nothing looks offline that isn't. */
  origin: SearchTier;
  entry?: DictionaryEntry;
  articles?: OnlineArticle[];
}

/* ── where each dictionary would answer from, right now ─────────────────
   Resolution order lives here and nowhere else: this device, then the server, then an online
   source. Both the search list and the article read it, so a word can never be listed from one
   place and then opened from another. */

export type SearchTier = "device" | "server" | "online";

export interface DictionarySource {
  entry: CatalogueEntry;
  origin: SearchTier;
  /** Set only for `server`: what the server said about the artifact, which the reader needs to range-read it. */
  remote?: RemoteDictionary;
}

/**
 * Resolving this costs an IndexedDB listing and, when the device is missing something, a request to
 * the server. Search runs on a keystroke, so the answer is held briefly rather than recomputed each
 * time; installing, removing or switching a dictionary clears it through `announce`.
 */
let sourceCache: { language: string; at: number; value: Promise<DictionarySource[]> } | null = null;
const SOURCE_CACHE_MS = 3000;

export async function dictionarySources(language?: string): Promise<DictionarySource[]> {
  const key = language ?? "";
  const now = Date.now();
  if (sourceCache && sourceCache.language === key && now - sourceCache.at < SOURCE_CACHE_MS) {
    return sourceCache.value;
  }
  const value = (async (): Promise<DictionarySource[]> => {
    const disabled = disabledSet();
    const held = await installed();
    const rows = knownDictionaries(held).filter((entry) => !disabled.has(entry.id)
      && (!language || entry.sourceLang === ANY_LANGUAGE
          || primaryLanguage(entry.sourceLang) === primaryLanguage(language)));
    const local = new Set(held.map((record) => record.id));

    let remote: RemoteDictionary[] = [];
    if (rows.some((entry) => entry.kind === "offline" && !local.has(entry.id))) {
      // The server being unreachable is ordinary, not an error: what this device holds still answers.
      try { remote = await listOnServer(); } catch { remote = []; }
    }

    const sources: DictionarySource[] = [];
    for (const entry of rows) {
      if (entry.kind === "online") { sources.push({ entry, origin: "online" }); continue; }
      if (local.has(entry.id)) { sources.push({ entry, origin: "device" }); continue; }
      const description = remote.find((candidate) => candidate.id === entry.id);
      // A dictionary neither stored here nor compiled on the server cannot answer anything.
      if (description) sources.push({ entry, origin: "server", remote: description });
    }
    return sources;
  })();
  sourceCache = { language: key, at: now, value };
  return value;
}

/* ── online sources, and their manners ──────────────────────────────────
   §9: honour the terms, do not prefetch, do not circumvent a rate limit. The interface already
   waits for ⏎ before asking anything online; these two are the floor underneath that, so no amount
   of clicking about can turn into a burst. */

const ONLINE_CACHE_MS = 5 * 60 * 1000;
const ONLINE_CACHE_ENTRIES = 200;
const ONLINE_MINIMUM_INTERVAL_MS = 1000;

const onlineCache = new Map<string, { at: number; entries: OnlineArticle[] }>();
const onlineLastCall = new Map<string, number>();

async function lookupOnline(id: string, word: string, language?: string): Promise<OnlineArticle[]> {
  const key = `${id}:${language ?? ""}:${word.toLowerCase()}`;
  const cached = onlineCache.get(key);
  if (cached && Date.now() - cached.at < ONLINE_CACHE_MS) return cached.entries;

  const since = Date.now() - (onlineLastCall.get(id) ?? 0);
  if (since < ONLINE_MINIMUM_INTERVAL_MS) {
    await new Promise((resolve) => setTimeout(resolve, ONLINE_MINIMUM_INTERVAL_MS - since));
  }
  onlineLastCall.set(id, Date.now());

  const answer = await backendSession.lookupOnlineDictionary(id, word, language);
  onlineCache.set(key, { at: Date.now(), entries: answer.entries });
  // Insertion order is iteration order, so the oldest key is the first one.
  while (onlineCache.size > ONLINE_CACHE_ENTRIES) {
    onlineCache.delete(onlineCache.keys().next().value as string);
  }
  return answer.entries;
}

/**
 * Forget every held answer and every held resolution.
 *
 * Signing out is the case that matters: the next session may be a different account on a different
 * server, and an answer cached under the old one has no business surviving into it.
 */
export function forgetCachedLookups(): void {
  onlineCache.clear();
  onlineLastCall.clear();
  sourceCache = null;
  opened.clear();
}

/* ── searching ──────────────────────────────────────────────────────────
   Listing candidate headwords touches only the key section of an artifact, so it costs a fraction
   of reading one of them. The gloss beside each row is fetched afterwards and only for the rows
   that will actually be shown. */

/** How many headwords one dictionary may contribute before the list stops being a list. */
const HITS_PER_DICTIONARY = 12;

/**
 * Headwords beginning with `prefix`, from every enabled dictionary in the requested tiers.
 *
 * One dictionary failing never takes the others down: an unreadable artifact or a server that went
 * away mid-search costs its own rows and nothing else.
 */
export interface SearchOutcome {
  hits: RawHit[];
  /** How many sources in these tiers were available to ask at all. Zero is worth saying out loud. */
  asked: number;
  /** Sources that failed rather than having nothing to say — a different thing, and never silent. */
  failed: string[];
}

export async function searchDictionaries(
  prefix: string,
  { language, tiers, limit = HITS_PER_DICTIONARY }:
    { language?: string; tiers: SearchTier[]; limit?: number }
): Promise<SearchOutcome> {
  const query = prefix.trim();
  if (!query) return { hits: [], asked: 0, failed: [] };
  const wanted = new Set(tiers);
  const sources = (await dictionarySources(language)).filter((source) => wanted.has(source.origin));
  const failed: string[] = [];

  const found = await Promise.all(sources.map(async (source): Promise<RawHit[]> => {
    const shared = { dictionaryId: source.entry.id, name: source.entry.name, origin: source.origin };
    try {
      if (source.origin === "online") {
        // An online source answers a word, not a prefix, so there is nothing to list: the answer
        // itself is the row, and it arrives with its gloss already in hand. Both spellings, so the
        // online tier is no more case-sensitive than the compiled one — but as typed first, because
        // a proper noun is a word the source may only hold capitalised.
        const spellings = [query, query.toLowerCase()].filter((word, index, all) =>
          all.indexOf(word) === index);
        for (const spelling of spellings) {
          const entries = await lookupOnline(source.entry.id, spelling, language);
          if (entries.length) {
            return [{ ...shared, word: entries[0].headword || spelling,
                      gloss: entries[0].senses.map((sense) => sense.definition).slice(0, 3).join("; ") }];
          }
        }
        return [];
      }
      const dictionary = await openDictionary(source.entry.id, source.remote);
      const words = (await dictionary?.search(query, limit)) ?? [];
      return words.map((word) => ({ ...shared, word }));
    } catch {
      // Recorded rather than swallowed. "No dictionary holds this word" and "the dictionary could
      // not be reached" look identical on screen otherwise, and only one of them is the truth.
      failed.push(source.entry.name);
      return [];
    }
  }));
  return { hits: found.flat(), asked: sources.length, failed };
}

/**
 * The one-line meaning for each of the first few rows.
 *
 * Deliberately bounded and deliberately last. A prefix run usually lands inside one 256-entry
 * frame, so several glosses often cost a single decode — but a dictionary on the server is read
 * over byte ranges, and hydrating every candidate there would turn a keystroke into a download.
 */
export async function hydrateGlosses(rows: ExternalRow[], language?: string): Promise<ExternalRow[]> {
  const needed = rows.filter((row) => !row.gloss);
  if (!needed.length) return rows;
  // Resolved again rather than assumed: a dictionary the server holds needs its description to be
  // range-read, and relying on the search having left it in the open-dictionary cache would make
  // this quietly stop working the moment that cache was evicted.
  const sources = await dictionarySources(language);
  const tierOf = (id: string) => sources.find((candidate) => candidate.entry.id === id)?.entry.tier;

  const glosses = new Map<string, string>();
  await Promise.all(needed.map(async (row) => {
    /* Every dictionary holding the word is a candidate, mapped ones first. A `fields` source has
       the meaning in a field; an `html` one has it somewhere inside a rendered fragment, and
       reading that back gives a far worse line. Whichever answers first wins, so a row is only
       blank when nothing could say anything about it. */
    const candidates = row.sources
      .filter((candidate) => candidate.origin !== "online")
      .sort((left, right) => Number(tierOf(left.dictionaryId) === "html")
        - Number(tierOf(right.dictionaryId) === "html"));
    for (const candidate of candidates) {
      const source = sources.find((entry) => entry.entry.id === candidate.dictionaryId);
      try {
        const dictionary = await openDictionary(candidate.dictionaryId, source?.remote);
        const entry = await dictionary?.lookup(row.word);
        const gloss = entry ? glossOf(entry) : "";
        if (gloss) { glosses.set(row.word, gloss); return; }
      } catch { /* a missing gloss is a quiet row, not a failed search */ }
    }
  }));
  return rows.map((row) => {
    const gloss = glosses.get(row.word);
    return gloss ? { ...row, gloss } : row;
  });
}

/**
 * Every enabled dictionary that has something to say about `word`, best source first.
 *
 * One dictionary failing never takes the others down: a server that is unreachable simply means the
 * dictionaries this device holds answer alone, which is the behaviour the whole design is built for.
 */
export async function lookup(
  word: string,
  language?: string,
  tiers: SearchTier[] = ["device", "server", "online"],
  /**
   * Other spellings of the same word, tried in order until one answers.
   *
   * This is what `lemma` is for. Acervo stores `la azafata` as the headword because the article is
   * how a Spanish learner needs to see the word, and `azafata` as the lemma because that is "the
   * dictionary form" — which is exactly what a dictionary is keyed on. Looking up only the headword
   * therefore missed every gendered noun in the vocabulary. Deliberately not a rule about articles:
   * nothing here knows that `la` is one, and the same field answers for a verb stored conjugated or
   * a noun stored with its classifier.
   */
  also: string[] = []
): Promise<LookupResult[]> {
  const wanted = new Set(tiers);
  const sources = (await dictionarySources(language)).filter((source) => wanted.has(source.origin));
  const spellings = [word, ...also].map((spelling) => spelling.trim()).filter(Boolean)
    .filter((spelling, index, all) => all.indexOf(spelling) === index);

  const results = await Promise.all(sources.map(async (source): Promise<LookupResult | null> => {
    const { entry } = source;
    const shared = { dictionaryId: entry.id, name: entry.name, sourceLang: entry.sourceLang,
                     attribution: entry.attribution, licence: entry.licence };
    try {
      if (source.origin === "online") {
        for (const spelling of spellings) {
          const entries = await lookupOnline(entry.id, spelling, language);
          if (entries.length) return { ...shared, origin: "online", articles: entries };
        }
        return null;
      }
      const dictionary = await openDictionary(entry.id, source.remote);
      for (const spelling of spellings) {
        const found = await dictionary?.lookup(spelling);
        if (found) return { ...shared, origin: source.origin, entry: found };
      }
      return null;
    } catch {
      return null;
    }
  }));
  return results.filter((result): result is LookupResult => result !== null);
}
