/**
 * Where a dictionary this device holds actually lives.
 *
 * A separate IndexedDB database from the replica, on purpose. Dictionary data is bulk, it is
 * replaceable from the server, and it is not the owner's vocabulary — so deleting every dictionary
 * must not go near `localDatabase.ts`, and wiping a replica that belongs to another account must
 * not throw away 40 MiB of downloads that are still perfectly good.
 *
 * **One record per file, never one per entry.** The artifact is already DEFLATE-compressed in
 * frames, and IndexedDB stores a Blob as opaque bytes, so the compaction survives storage intact —
 * but only because there are three records per dictionary rather than eight hundred thousand.
 * Per-record overhead is the thing that would undo the whole container decision, and it is entirely
 * a function of how many records there are. A Blob is also read lazily: `blob.slice(offset, length)`
 * fetches that range from disk instead of materialising the file, which is what lets the reader
 * hold only a few hundred KiB of any dictionary at a time.
 */

const DATABASE_NAME = "acervo-dictionaries";
const DATABASE_VERSION = 1;
const STORE = "artifacts";

/** What the artifact's own `<id>.json` says. Repeated here so a row renders without the blob. */
export interface DictionaryMetadata {
  id: string;
  name: string;
  sourceLang: string;
  targetLang: string;
  tier: "fields" | "html";
  licence: string;
  attribution: string;
  entryCount: number;
  keyCount: number;
  sourceDate?: string;
  builtAt?: string;
  schemaVersion: number;
  blobBytes: number;
  indexBytes: number;
}

export interface StoredDictionary {
  id: string;
  metadata: DictionaryMetadata;
  blob: Blob;
  index: Blob;
  installedAt: string;
  bytes: number;
}

/** A row without its payload, for listing what is installed without touching the data. */
export type InstalledDictionary = Omit<StoredDictionary, "blob" | "index">;

export interface DictionaryStore {
  list(): Promise<InstalledDictionary[]>;
  read(id: string): Promise<StoredDictionary | null>;
  save(record: Omit<StoredDictionary, "installedAt" | "bytes">): Promise<void>;
  remove(id: string): Promise<void>;
  clear(): Promise<void>;
}

function request<T>(value: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    value.onsuccess = () => resolve(value.result);
    value.onerror = () => reject(value.error);
  });
}

function settled(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error);
  });
}

class IndexedDictionaryStore implements DictionaryStore {
  private handle: Promise<IDBDatabase> | null = null;

  private open(): Promise<IDBDatabase> {
    if (this.handle) return this.handle;
    this.handle = new Promise((resolve, reject) => {
      const opening = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
      opening.onupgradeneeded = () => {
        const database = opening.result;
        if (!database.objectStoreNames.contains(STORE)) database.createObjectStore(STORE, { keyPath: "id" });
      };
      opening.onsuccess = () => resolve(opening.result);
      opening.onerror = () => reject(opening.error);
    });
    return this.handle;
  }

  async list(): Promise<InstalledDictionary[]> {
    const database = await this.open();
    const records = await request(database.transaction(STORE, "readonly").objectStore(STORE).getAll());
    return (records as StoredDictionary[])
      .map(({ blob: _blob, index: _index, ...rest }) => rest)
      .sort((left, right) => left.id.localeCompare(right.id));
  }

  async read(id: string): Promise<StoredDictionary | null> {
    const database = await this.open();
    const record = await request(database.transaction(STORE, "readonly").objectStore(STORE).get(id));
    return (record as StoredDictionary | undefined) ?? null;
  }

  async save(record: Omit<StoredDictionary, "installedAt" | "bytes">): Promise<void> {
    const database = await this.open();
    const transaction = database.transaction(STORE, "readwrite");
    transaction.objectStore(STORE).put({
      ...record,
      installedAt: new Date().toISOString(),
      bytes: record.blob.size + record.index.size
    });
    return settled(transaction);
  }

  async remove(id: string): Promise<void> {
    const database = await this.open();
    const transaction = database.transaction(STORE, "readwrite");
    transaction.objectStore(STORE).delete(id);
    return settled(transaction);
  }

  async clear(): Promise<void> {
    const database = await this.open();
    const transaction = database.transaction(STORE, "readwrite");
    transaction.objectStore(STORE).clear();
    return settled(transaction);
  }
}

/** Used where IndexedDB is unavailable, so a lookup degrades to the server rather than throwing. */
export class MemoryDictionaryStore implements DictionaryStore {
  private records = new Map<string, StoredDictionary>();

  async list(): Promise<InstalledDictionary[]> {
    return [...this.records.values()]
      .map(({ blob: _blob, index: _index, ...rest }) => rest)
      .sort((left, right) => left.id.localeCompare(right.id));
  }

  async read(id: string) { return this.records.get(id) ?? null; }

  async save(record: Omit<StoredDictionary, "installedAt" | "bytes">) {
    this.records.set(record.id, {
      ...record,
      installedAt: new Date().toISOString(),
      bytes: record.blob.size + record.index.size
    });
  }

  async remove(id: string) { this.records.delete(id); }
  async clear() { this.records.clear(); }
}

export const createDictionaryStore = (): DictionaryStore => {
  try {
    return typeof indexedDB !== "undefined" ? new IndexedDictionaryStore() : new MemoryDictionaryStore();
  } catch {
    return new MemoryDictionaryStore();
  }
};

export interface StorageReport {
  usedBytes: number | null;
  quotaBytes: number | null;
  persisted: boolean;
}

/**
 * What the browser will admit about storage, and whether this origin is exempt from eviction.
 *
 * The exemption is the part that matters. An origin with no interaction for seven days of browser
 * use has its storage deleted, and a dictionary someone waited to download is exactly the thing
 * that should not silently vanish. `persist()` is asked for once, after an install succeeds, which
 * is the moment the browser is most likely to grant it.
 */
export async function storageReport(): Promise<StorageReport> {
  const storage = typeof navigator !== "undefined" ? navigator.storage : undefined;
  if (!storage?.estimate) return { usedBytes: null, quotaBytes: null, persisted: false };
  try {
    const estimate = await storage.estimate();
    return {
      usedBytes: estimate.usage ?? null,
      quotaBytes: estimate.quota ?? null,
      persisted: (await storage.persisted?.()) ?? false
    };
  } catch {
    return { usedBytes: null, quotaBytes: null, persisted: false };
  }
}

export async function requestPersistence(): Promise<boolean> {
  try {
    return (await navigator.storage?.persist?.()) ?? false;
  } catch {
    return false;
  }
}
