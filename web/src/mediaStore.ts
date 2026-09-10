/**
 * Where the pictures this device has seen actually live.
 *
 * A **third** IndexedDB database, beside the replica and the dictionaries, for the reason each of
 * those is separate from the other: a picture is bulk, it is replaceable from the server, and it is
 * not the owner's vocabulary. Wiping a replica that belongs to another account must not throw away
 * a hundred megabytes of pictures that are still perfectly good, and clearing the pictures must not
 * go near `localDatabase.ts`.
 *
 * **One record per file, never one per record field.** The same rule `dictionaryStore.ts` states,
 * and here it is the difference between storing WebP bytes as WebP bytes and paying per-record
 * overhead on every one of a few thousand pictures.
 *
 * Keyed by `imageRef` — the path the record itself carries — rather than by the prompt id, because
 * a reference is what a component has in its hand and what the media route wants. A regeneration
 * overwrites in place, so the key is stable and the newest bytes win, which is exactly the
 * behaviour a cache should have and is why this needs no invalidation of its own.
 */

const DATABASE_NAME = "acervo-media";
const DATABASE_VERSION = 1;
const STORE = "pictures";

export interface StoredPicture {
  /** The `imageRef` the record carries, relative to the server's media directory. */
  reference: string;
  blob: Blob;
  fetchedAt: string;
}

export interface MediaStore {
  read(reference: string): Promise<StoredPicture | null>;
  save(reference: string, blob: Blob): Promise<void>;
  remove(reference: string): Promise<void>;
  clear(): Promise<void>;
  bytes(): Promise<number>;
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

class IndexedMediaStore implements MediaStore {
  private handle: Promise<IDBDatabase> | null = null;

  private open(): Promise<IDBDatabase> {
    if (this.handle) return this.handle;
    this.handle = new Promise((resolve, reject) => {
      const opening = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
      opening.onupgradeneeded = () => {
        const database = opening.result;
        if (!database.objectStoreNames.contains(STORE)) {
          database.createObjectStore(STORE, { keyPath: "reference" });
        }
      };
      opening.onsuccess = () => resolve(opening.result);
      opening.onerror = () => reject(opening.error);
    });
    return this.handle;
  }

  async read(reference: string): Promise<StoredPicture | null> {
    const database = await this.open();
    const record = await request(
      database.transaction(STORE, "readonly").objectStore(STORE).get(reference)
    );
    return (record as StoredPicture | undefined) ?? null;
  }

  async save(reference: string, blob: Blob): Promise<void> {
    const database = await this.open();
    const transaction = database.transaction(STORE, "readwrite");
    transaction.objectStore(STORE).put({ reference, blob, fetchedAt: new Date().toISOString() });
    return settled(transaction);
  }

  async remove(reference: string): Promise<void> {
    const database = await this.open();
    const transaction = database.transaction(STORE, "readwrite");
    transaction.objectStore(STORE).delete(reference);
    return settled(transaction);
  }

  async clear(): Promise<void> {
    const database = await this.open();
    const transaction = database.transaction(STORE, "readwrite");
    transaction.objectStore(STORE).clear();
    return settled(transaction);
  }

  async bytes(): Promise<number> {
    const database = await this.open();
    const records = await request(
      database.transaction(STORE, "readonly").objectStore(STORE).getAll()
    );
    return (records as StoredPicture[]).reduce((total, record) => total + record.blob.size, 0);
  }
}

/** Used where IndexedDB is unavailable, so a picture degrades to one fetch per view, not to none. */
export class MemoryMediaStore implements MediaStore {
  private records = new Map<string, StoredPicture>();

  async read(reference: string) { return this.records.get(reference) ?? null; }
  async save(reference: string, blob: Blob) {
    this.records.set(reference, { reference, blob, fetchedAt: new Date().toISOString() });
  }
  async remove(reference: string) { this.records.delete(reference); }
  async clear() { this.records.clear(); }
  async bytes() {
    return [...this.records.values()].reduce((total, record) => total + record.blob.size, 0);
  }
}

export function createMediaStore(): MediaStore {
  return typeof indexedDB === "undefined" ? new MemoryMediaStore() : new IndexedMediaStore();
}
