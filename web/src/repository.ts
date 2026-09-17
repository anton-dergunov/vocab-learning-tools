import {
  validateGraph,
  type Attestation, type AttestationInput, type EntityKind, type Example, type ExampleInput,
  type ImagePrompt, type ImagePromptInput, type Lexeme, type LexemeInput, type Pronunciation, type Sense, type SenseInput,
  type OwnedFields, type StudyState, type StudyStateInput, type SyncFields, type Topic, type TopicInput,
  type Vocabulary, type VocabularyInput, type VocabularyGraph
} from "./domain";
import { createLocalDatabase, MemoryDatabase, RECORD_STORES, type LocalDatabase, type ReplicaMeta } from "./localDatabase";
import { newDeviceId, newId, nowInstant } from "./ids";
import type { ArticleDraft } from "./yaml";

export const LOCAL_SCHEMA_VERSION = 10;

export const EMPTY_GRAPH = (): VocabularyGraph => ({
  vocabularies: [], topics: [], lexemes: [], senses: [], attestations: [], examples: [], imagePrompts: [],
  pronunciations: [], studyStates: []
});

export type Entity = Vocabulary | Topic | Lexeme | Sense | Attestation | Example | ImagePrompt | Pronunciation | StudyState;
type EntityInput = VocabularyInput | TopicInput | LexemeInput | SenseInput | AttestationInput | ExampleInput | ImagePromptInput | StudyStateInput;

/** What the server returns for a batch of applied records. */
export interface RemoteWrite {
  records: Partial<VocabularyGraph>;
  cursor: number;
  datasetId: string;
}

/**
 * The write half of the server transport. `sync.ts` owns the routes and attaches this; the
 * repository never reaches the network itself, and the interface never reaches past the repository.
 */
/**
 * `enrich: false` asks the server not to queue enrichment for words this write creates. Only a
 * bundle import says so, because it restores the bundle's pictures first and asks afterwards.
 */
export interface WriteOptions {
  enrich?: boolean;
}

export interface ArticleWrite extends RemoteWrite {
  lexemeId: string;
  /** The server job enriching what the save created, or null when it created nothing to enrich. */
  jobId: string | null;
}

export interface RemoteGraph {
  push(changes: Partial<VocabularyGraph>, options?: WriteOptions): Promise<RemoteWrite>;
  saveArticle(
    draft: ArticleDraft, minted: ReadonlySet<string>, base: Record<string, number>, options?: WriteOptions
  ): Promise<ArticleWrite>;
}

export interface ReplicaSnapshot extends VocabularyGraph {
  ready: boolean;
  ownerId: string;
  deviceId: string;
  datasetId: string;
  cursor: number;
  lastPulledAt: string | null;
  lastWroteAt: string | null;
  persistent: boolean;
}

export interface AcervoRepository {
  load(ownerId: string): Promise<void>;
  clear(): Promise<void>;
  snapshot(): ReplicaSnapshot;
  attachRemote(remote: RemoteGraph | null): void;
  applyRemote(changes: Partial<VocabularyGraph>, cursor: number, datasetId: string): Promise<number>;
  writeGraph(changes: Partial<VocabularyGraph>): Promise<void>;
  saveArticle(draft: ArticleDraft, minted?: ReadonlySet<string>, options?: WriteOptions): Promise<string>;
  saveVocabulary(input: VocabularyInput, id?: string): Promise<Vocabulary>;
  saveTopic(input: TopicInput, id?: string): Promise<Topic>;
  saveLexeme(input: LexemeInput, id?: string): Promise<Lexeme>;
  saveSense(input: SenseInput, id?: string): Promise<Sense>;
  saveAttestation(input: AttestationInput, id?: string): Promise<Attestation>;
  saveExample(input: ExampleInput, id?: string): Promise<Example>;
  saveImagePrompt(input: ImagePromptInput, id?: string): Promise<ImagePrompt>;
  saveStudyState(input: StudyStateInput, id?: string): Promise<StudyState>;
  delete(kind: EntityKind, id: string): Promise<void>;
}

const EMPTY_META = (): ReplicaMeta => ({
  ownerId: "", deviceId: "", schemaVersion: LOCAL_SCHEMA_VERSION,
  datasetId: "", cursor: 0, lastPulledAt: null, lastWroteAt: null
});

export class LocalAcervoRepository implements AcervoRepository {
  private graph = EMPTY_GRAPH();
  private meta: ReplicaMeta = EMPTY_META();
  private ready = false;
  private persistent = true;
  private lastInstant = "";
  private remote: RemoteGraph | null = null;
  private queue: Promise<unknown> = Promise.resolve();

  constructor(private database: LocalDatabase = createLocalDatabase()) {}

  async load(ownerId: string): Promise<void> {
    try {
      await this.open(ownerId);
    } catch {
      this.database = new MemoryDatabase();
      this.persistent = false;
      await this.open(ownerId);
    }
  }

  private async open(ownerId: string) {
    const contents = await this.database.read();
    const deviceId = contents.meta.deviceId || newDeviceId();
    const stale = contents.meta.ownerId !== ownerId || contents.meta.schemaVersion !== LOCAL_SCHEMA_VERSION;
    if (stale) {
      await this.database.wipe();
      this.graph = EMPTY_GRAPH();
      this.meta = { ...EMPTY_META(), ownerId, deviceId };
      await this.database.write({ meta: this.meta });
    } else {
      const graph: VocabularyGraph = {
        vocabularies: contents.vocabularies,
        topics: contents.topics,
        lexemes: contents.lexemes,
        senses: contents.senses,
        attestations: contents.attestations,
        examples: contents.examples,
        imagePrompts: contents.imagePrompts,
        pronunciations: contents.pronunciations,
        studyStates: contents.studyStates
      };
      validateGraph(graph);
      const allRecords: Entity[][] = [
        graph.vocabularies, graph.topics, graph.lexemes, graph.senses, graph.attestations, graph.examples, graph.imagePrompts, graph.pronunciations, graph.studyStates
      ];
      const hasForeignRecord = allRecords.some((records) => records.some((record) => record.ownerId !== ownerId));
      if (hasForeignRecord) throw new Error("Replica records do not belong to the authenticated owner.");
      this.graph = graph;
      this.meta = {
        ...EMPTY_META(),
        ownerId,
        deviceId,
        datasetId: contents.meta.datasetId ?? "",
        cursor: contents.meta.cursor ?? 0,
        lastPulledAt: contents.meta.lastPulledAt ?? null,
        lastWroteAt: contents.meta.lastWroteAt ?? null
      };
    }
    this.ready = true;
  }

  async clear(): Promise<void> {
    await this.database.wipe();
    this.graph = EMPTY_GRAPH();
    this.meta = EMPTY_META();
    this.ready = false;
  }

  snapshot(): ReplicaSnapshot {
    return {
      ...structuredClone(this.graph), ready: this.ready, ownerId: this.meta.ownerId,
      deviceId: this.meta.deviceId, datasetId: this.meta.datasetId, cursor: this.meta.cursor,
      lastPulledAt: this.meta.lastPulledAt, lastWroteAt: this.meta.lastWroteAt,
      persistent: this.persistent
    };
  }

  attachRemote(remote: RemoteGraph | null): void {
    this.remote = remote;
  }

  /**
   * Serialises everything that reads and then rewrites the graph. A pull and a write each take a
   * copy on entry and install it on exit, so interleaving them would silently drop whichever
   * finished first. Both round trips are seconds at worst, and neither is on a render path.
   */
  private serialize<T>(work: () => Promise<T>): Promise<T> {
    const result = this.queue.then(work, work);
    this.queue = result.catch(() => undefined);
    return result;
  }

  /**
   * Applies a delta the server sent, newest wins by revision. Only the server mints revisions, so
   * they totally order the versions of a record — there is no timestamp comparison and no merge.
   * Records and the cursor that covers them land in one transaction. Returns how many were applied.
   */
  applyRemote(changes: Partial<VocabularyGraph>, cursor: number, datasetId: string): Promise<number> {
    return this.serialize(() => this.merge(changes, cursor, datasetId));
  }

  private async merge(
    changes: Partial<VocabularyGraph>, cursor: number, datasetId: string, wroteAt?: string
  ): Promise<number> {
    if (!this.ready) throw new Error("Load the Acervo repository before applying remote records.");
    const next = structuredClone(this.graph);
    const write: Partial<VocabularyGraph> = {};
    let applied = 0;
    RECORD_STORES.forEach((kind) => {
      const incoming = changes[kind] as Entity[] | undefined;
      if (!incoming?.length) return;
      const target = next[kind] as Entity[];
      const accepted: Entity[] = [];
      incoming.forEach((record) => {
        if (record.ownerId !== this.meta.ownerId) throw new Error("Cannot apply a record owned by another account.");
        const index = target.findIndex((candidate) => candidate.id === record.id);
        // A reply that lost a race with a newer version of the same record must not undo it.
        if (index >= 0 && record.revision <= target[index].revision) return;
        if (index < 0) target.push(structuredClone(record)); else target[index] = structuredClone(record);
        accepted.push(record);
      });
      if (!accepted.length) return;
      write[kind] = structuredClone(accepted) as never;
      applied += accepted.length;
    });
    validateGraph(next);
    // A push is not a pull: only a pull moves the "last received" stamp.
    const meta: Partial<ReplicaMeta> = wroteAt
      ? { cursor, datasetId, lastWroteAt: wroteAt }
      : { cursor, datasetId, lastPulledAt: this.instant() };
    await this.database.write({ ...write, meta });
    this.graph = next;
    this.meta = { ...this.meta, ...meta } as ReplicaMeta;
    return applied;
  }

  private instant(): string {
    const current = nowInstant();
    const next = current > this.lastInstant ? current : new Date(Date.parse(this.lastInstant) + 1).toISOString();
    this.lastInstant = next;
    return next;
  }

  private stamp(existing?: Entity): SyncFields & OwnedFields {
    const editedAt = this.instant();
    return {
      ownerId: this.meta.ownerId,
      deleted: false,
      createdAt: existing?.createdAt ?? editedAt,
      editedAt,
      editedBy: this.meta.deviceId,
      // The revision the edit is based on. The server refuses the write if it has moved on, and
      // replaces this with the one it allocates.
      revision: existing?.revision ?? 0
    };
  }

  /**
   * Sends a change set to the server and stores what comes back. Nothing local moves until the
   * server has accepted it: offline, this throws and the replica is exactly as it was.
   */
  private commit(changes: Partial<VocabularyGraph>, options?: WriteOptions): Promise<void> {
    return this.serialize(() => this.send(changes, options));
  }

  private async send(changes: Partial<VocabularyGraph>, options?: WriteOptions): Promise<void> {
    if (!this.ready) throw new Error("Load the Acervo repository before writing.");
    const proposed = structuredClone(this.graph);
    (Object.entries(changes) as [EntityKind, Entity[]][]).forEach(([kind, records]) => {
      records?.forEach((record) => {
        if (record.ownerId !== this.meta.ownerId) throw new Error("Cannot write a record owned by another account.");
        const target = proposed[kind] as Entity[];
        const index = target.findIndex((candidate) => candidate.id === record.id);
        if (index < 0) target.push(record); else target[index] = record;
      });
    });
    validateGraph(proposed);
    if (!this.remote) {
      throw new Error("Acervo is not connected to the server, so this change was not saved.");
    }
    const result = await this.remote.push(changes, options);
    // One transaction for the records the server blessed and the stamp that says we wrote.
    await this.merge(result.records, result.cursor, result.datasetId, this.instant());
  }

  writeGraph(changes: Partial<VocabularyGraph>): Promise<void> {
    return this.commit(changes);
  }

  private async save(kind: EntityKind, input: EntityInput, requestedId?: string): Promise<Entity> {
    if (!this.ready) throw new Error("Load the Acervo repository before writing.");
    const records = this.graph[kind] as Entity[];
    const existing = requestedId ? records.find((record) => record.id === requestedId) : undefined;
    const record = { ...input, id: existing?.id ?? requestedId ?? newId(), ...this.stamp(existing) } as Entity;
    await this.commit({ [kind]: [record] });
    return (this.graph[kind] as Entity[]).find((candidate) => candidate.id === record.id) ?? record;
  }

  saveVocabulary(input: VocabularyInput, id?: string) { return this.save("vocabularies", input, id) as Promise<Vocabulary>; }
  saveTopic(input: TopicInput, id?: string) { return this.save("topics", input, id) as Promise<Topic>; }
  saveLexeme(input: LexemeInput, id?: string) { return this.save("lexemes", input, id) as Promise<Lexeme>; }
  saveSense(input: SenseInput, id?: string) { return this.save("senses", input, id) as Promise<Sense>; }
  saveAttestation(input: AttestationInput, id?: string) { return this.save("attestations", input, id) as Promise<Attestation>; }
  saveExample(input: ExampleInput, id?: string) { return this.save("examples", input, id) as Promise<Example>; }
  saveImagePrompt(input: ImagePromptInput, id?: string) { return this.save("imagePrompts", input, id) as Promise<ImagePrompt>; }
  saveStudyState(input: StudyStateInput, id?: string) { return this.save("studyStates", input, id) as Promise<StudyState>; }

  /**
   * Saves a whole article, edited as YAML, in one write — on the server.
   *
   * The document goes as the draft `parseArticle` produced, and `POST /articles` works out what it
   * means for the stored entry: a record carrying an id is the one it names, a record without one is
   * new, and a stored record the document no longer mentions is tombstoned. Nothing is recreated, so
   * the Anki note join, the image seed and `createdAt` survive a fixed typo. One round trip, all or
   * nothing, and nothing local moves until the server has accepted it.
   *
   * `base` is what this replica holds of the entry, at the revisions it holds them: the server states
   * those revisions, so an edit made from a stale copy is refused, and it tombstones only records
   * this device could have seen.
   *
   * `minted` names ids this save is *creating* rather than naming, and is empty for every caller but
   * one: a chat proposal that adds an example drawn from a sentence you just supplied needs both
   * records in one save. The exception is an **argument**, not a field in the document, so a
   * hand-typed document cannot claim it.
   */
  async saveArticle(
    draft: ArticleDraft, minted: ReadonlySet<string> = new Set(), options?: WriteOptions
  ): Promise<string> {
    return this.serialize(async () => {
      if (!this.ready) throw new Error("Load the Acervo repository before writing.");
      if (!this.remote) {
        throw new Error("Acervo is not connected to the server, so this change was not saved.");
      }
      const result = await this.remote.saveArticle(draft, minted, this.baseOf(draft.id), options);
      await this.merge(result.records, result.cursor, result.datasetId, this.instant());
      return result.lexemeId;
    });
  }

  /** Every record of one entry this replica holds, at the revision it holds it. */
  private baseOf(lexemeId: string | null): Record<string, number> {
    if (!lexemeId) return {};
    const graph = this.graph;
    const senses = new Set(graph.senses.filter((one) => one.lexemeId === lexemeId).map((one) => one.id));
    const records: Entity[] = [
      ...graph.lexemes.filter((one) => one.id === lexemeId),
      ...graph.senses.filter((one) => one.lexemeId === lexemeId),
      ...graph.examples.filter((one) => senses.has(one.senseId)),
      ...graph.attestations.filter((one) => one.lexemeId === lexemeId),
      ...graph.imagePrompts.filter((one) => one.lexemeId === lexemeId),
      ...graph.pronunciations.filter((one) => one.lexemeId === lexemeId)
    ];
    return Object.fromEntries(records.map((record) => [record.id, record.revision]));
  }

  async delete(kind: EntityKind, id: string): Promise<void> {
    if (!this.ready) throw new Error("Load the Acervo repository before writing.");
    const changed: Partial<VocabularyGraph> = {};
    const change = <T extends Entity>(store: EntityKind, value: T) => {
      const list = (changed[store] ?? []) as T[];
      list.push(value);
      changed[store] = list as never;
    };
    const tombstone = <T extends Entity>(store: EntityKind, record: T) => {
      change(store, { ...record, ...this.stamp(record), deleted: true } as T);
    };
    const target = (this.graph[kind] as Entity[]).find((record) => record.id === id);
    if (!target || target.deleted) return;
    tombstone(kind, target);
    if (kind === "topics") {
      this.graph.lexemes
        .filter((record) => record.topicIds.includes(id) && !record.deleted)
        .forEach((record) => change("lexemes", {
          ...record, ...this.stamp(record), topicIds: record.topicIds.filter((topicId) => topicId !== id)
        }));
    } else if (kind === "lexemes") {
      const senseIds = new Set(this.graph.senses.filter((record) => record.lexemeId === id).map((record) => record.id));
      this.graph.senses.filter((record) => record.lexemeId === id && !record.deleted).forEach((record) => tombstone("senses", record));
      this.graph.attestations.filter((record) => record.lexemeId === id && !record.deleted).forEach((record) => tombstone("attestations", record));
      this.graph.examples.filter((record) => senseIds.has(record.senseId) && !record.deleted).forEach((record) => tombstone("examples", record));
      this.graph.imagePrompts.filter((record) => record.lexemeId === id && !record.deleted).forEach((record) => tombstone("imagePrompts", record));
      this.graph.pronunciations.filter((record) => record.lexemeId === id && !record.deleted).forEach((record) => tombstone("pronunciations", record));
      this.graph.studyStates.filter((record) => record.lexemeId === id && !record.deleted).forEach((record) => tombstone("studyStates", record));
    } else if (kind === "senses") {
      this.graph.examples.filter((record) => record.senseId === id && !record.deleted).forEach((record) => tombstone("examples", record));
      this.graph.imagePrompts.filter((record) => record.senseId === id && !record.deleted).forEach((record) => tombstone("imagePrompts", record));
      const examples = new Set(this.graph.examples.filter((record) => record.senseId === id).map((record) => record.id));
      this.graph.pronunciations
        .filter((record) => !record.deleted && ((record.targetKind === "sense" && record.targetId === id)
          || (record.targetKind === "example" && examples.has(record.targetId))))
        .forEach((record) => tombstone("pronunciations", record));
    }
    await this.commit(changed);
  }
}

export const repository: AcervoRepository = new LocalAcervoRepository();
