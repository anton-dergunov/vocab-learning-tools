import type { VocabularyGraph } from "./domain";

const DATABASE_NAME = "acervo";
const DATABASE_VERSION = 2;
export const RECORD_STORES = ["topics", "lexemes", "senses", "attestations", "examples", "imagePrompts", "studyStates"] as const;
const STORES = [...RECORD_STORES, "pending", "meta"] as const;
export type RecordStore = typeof RECORD_STORES[number];

export interface ReplicaMeta {
  ownerId: string;
  deviceId: string;
  schemaVersion: number;
}

export interface DatabaseContents extends VocabularyGraph {
  pending: string[];
  meta: Partial<ReplicaMeta>;
}

export interface DatabaseWrite extends Partial<VocabularyGraph> {
  /** Empties every record store before the supplied records are written, in the same transaction. */
  replaceRecords?: boolean;
  addPending?: string[];
  clearPending?: string[];
  meta?: Partial<ReplicaMeta>;
}

export interface LocalDatabase {
  read(): Promise<DatabaseContents>;
  write(changes: DatabaseWrite): Promise<void>;
  wipe(): Promise<void>;
}

export const pendingKey = (store: RecordStore, id: string) => `${store}:${id}`;

function request<T>(value: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    value.onsuccess = () => resolve(value.result);
    value.onerror = () => reject(value.error);
  });
}

class IndexedDatabase implements LocalDatabase {
  private handle: Promise<IDBDatabase> | null = null;

  private open(): Promise<IDBDatabase> {
    if (this.handle) return this.handle;
    this.handle = new Promise((resolve, reject) => {
      const opening = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
      opening.onupgradeneeded = () => {
        const database = opening.result;
        STORES.forEach((store) => {
          if (!database.objectStoreNames.contains(store)) database.createObjectStore(store);
        });
      };
      opening.onsuccess = () => resolve(opening.result);
      opening.onerror = () => reject(opening.error);
    });
    return this.handle;
  }

  async read(): Promise<DatabaseContents> {
    const database = await this.open();
    const transaction = database.transaction(STORES, "readonly");
    const records = await Promise.all(RECORD_STORES.map((store) => request(transaction.objectStore(store).getAll())));
    const [pending, metaKeys, metaValues] = await Promise.all([
      request(transaction.objectStore("pending").getAllKeys()),
      request(transaction.objectStore("meta").getAllKeys()),
      request(transaction.objectStore("meta").getAll())
    ]);
    const meta: Record<string, unknown> = {};
    metaKeys.forEach((key, index) => { meta[String(key)] = metaValues[index]; });
    return {
      topics: records[0] as VocabularyGraph["topics"],
      lexemes: records[1] as VocabularyGraph["lexemes"],
      senses: records[2] as VocabularyGraph["senses"],
      attestations: records[3] as VocabularyGraph["attestations"],
      examples: records[4] as VocabularyGraph["examples"],
      imagePrompts: records[5] as VocabularyGraph["imagePrompts"],
      studyStates: records[6] as VocabularyGraph["studyStates"],
      pending: pending.map(String),
      meta: meta as Partial<ReplicaMeta>
    };
  }

  async write(changes: DatabaseWrite): Promise<void> {
    const database = await this.open();
    const transaction = database.transaction(STORES, "readwrite");
    RECORD_STORES.forEach((store) => {
      if (changes.replaceRecords) transaction.objectStore(store).clear();
      changes[store]?.forEach((record) => transaction.objectStore(store).put(record, record.id));
    });
    changes.addPending?.forEach((key) => transaction.objectStore("pending").put(true, key));
    changes.clearPending?.forEach((key) => transaction.objectStore("pending").delete(key));
    Object.entries(changes.meta ?? {}).forEach(([key, value]) => transaction.objectStore("meta").put(value, key));
    return new Promise((resolve, reject) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  }

  async wipe(): Promise<void> {
    const database = await this.open();
    const transaction = database.transaction(STORES, "readwrite");
    STORES.forEach((store) => transaction.objectStore(store).clear());
    return new Promise((resolve, reject) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  }
}

export class MemoryDatabase implements LocalDatabase {
  private contents: DatabaseContents = {
    topics: [], lexemes: [], senses: [], attestations: [], examples: [], imagePrompts: [], studyStates: [], pending: [], meta: {}
  };

  async read(): Promise<DatabaseContents> {
    return structuredClone(this.contents);
  }

  async write(changes: DatabaseWrite): Promise<void> {
    const replace = <T extends { id: string }>(current: T[], updates?: T[]) => {
      const result = changes.replaceRecords ? [] : [...current];
      updates?.forEach((update) => {
        const index = result.findIndex((record) => record.id === update.id);
        if (index < 0) result.push(update); else result[index] = update;
      });
      return result;
    };
    const pending = new Set(this.contents.pending);
    changes.addPending?.forEach((key) => pending.add(key));
    changes.clearPending?.forEach((key) => pending.delete(key));
    this.contents = {
      topics: replace(this.contents.topics, changes.topics),
      lexemes: replace(this.contents.lexemes, changes.lexemes),
      senses: replace(this.contents.senses, changes.senses),
      attestations: replace(this.contents.attestations, changes.attestations),
      examples: replace(this.contents.examples, changes.examples),
      imagePrompts: replace(this.contents.imagePrompts, changes.imagePrompts),
      studyStates: replace(this.contents.studyStates, changes.studyStates),
      pending: [...pending],
      meta: { ...this.contents.meta, ...changes.meta }
    };
  }

  async wipe(): Promise<void> {
    this.contents = { topics: [], lexemes: [], senses: [], attestations: [], examples: [], imagePrompts: [], studyStates: [], pending: [], meta: {} };
  }
}

function indexedDatabaseAvailable(): boolean {
  try { return typeof indexedDB !== "undefined"; } catch { return false; }
}

export const createLocalDatabase = (): LocalDatabase => indexedDatabaseAvailable() ? new IndexedDatabase() : new MemoryDatabase();
