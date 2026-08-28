import {
  validateGraph,
  type Attestation, type AttestationInput, type EntityKind, type Example, type ExampleInput,
  type ImagePrompt, type ImagePromptInput, type Lexeme, type LexemeInput, type Sense, type SenseInput,
  type OwnedFields, type StudyState, type StudyStateInput, type SyncFields, type VocabularyGraph
} from "./domain";
import { createLocalDatabase, MemoryDatabase, pendingKey, type LocalDatabase, type RecordStore, type ReplicaMeta } from "./localDatabase";
import { newDeviceId, newId, nowInstant } from "./ids";

export const LOCAL_SCHEMA_VERSION = 1;

const EMPTY_GRAPH = (): VocabularyGraph => ({
  lexemes: [], senses: [], attestations: [], examples: [], imagePrompts: [], studyStates: []
});

type Entity = Lexeme | Sense | Attestation | Example | ImagePrompt | StudyState;
type EntityInput = LexemeInput | SenseInput | AttestationInput | ExampleInput | ImagePromptInput | StudyStateInput;

export interface ReplicaSnapshot extends VocabularyGraph {
  ready: boolean;
  ownerId: string;
  deviceId: string;
  pendingCount: number;
  persistent: boolean;
}

export interface AcervoRepository {
  load(ownerId: string): Promise<void>;
  clear(): Promise<void>;
  snapshot(): ReplicaSnapshot;
  writeGraph(changes: Partial<VocabularyGraph>): Promise<void>;
  saveLexeme(input: LexemeInput, id?: string): Promise<Lexeme>;
  saveSense(input: SenseInput, id?: string): Promise<Sense>;
  saveAttestation(input: AttestationInput, id?: string): Promise<Attestation>;
  saveExample(input: ExampleInput, id?: string): Promise<Example>;
  saveImagePrompt(input: ImagePromptInput, id?: string): Promise<ImagePrompt>;
  saveStudyState(input: StudyStateInput, id?: string): Promise<StudyState>;
  delete(kind: EntityKind, id: string): Promise<void>;
}

export class LocalAcervoRepository implements AcervoRepository {
  private graph = EMPTY_GRAPH();
  private meta: ReplicaMeta = { ownerId: "", deviceId: "", schemaVersion: LOCAL_SCHEMA_VERSION };
  private pending = new Set<string>();
  private ready = false;
  private persistent = true;
  private lastInstant = "";

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
      this.pending = new Set();
      this.meta = { ownerId, deviceId, schemaVersion: LOCAL_SCHEMA_VERSION };
      await this.database.write({ meta: this.meta });
    } else {
      const graph: VocabularyGraph = {
        lexemes: contents.lexemes,
        senses: contents.senses,
        attestations: contents.attestations,
        examples: contents.examples,
        imagePrompts: contents.imagePrompts,
        studyStates: contents.studyStates
      };
      validateGraph(graph);
      const allRecords: Entity[][] = [
        graph.lexemes, graph.senses, graph.attestations, graph.examples, graph.imagePrompts, graph.studyStates
      ];
      const hasForeignRecord = allRecords.some((records) => records.some((record) => record.ownerId !== ownerId));
      if (hasForeignRecord) throw new Error("Replica records do not belong to the authenticated owner.");
      this.graph = graph;
      this.pending = new Set(contents.pending);
      this.meta = { ownerId, deviceId, schemaVersion: LOCAL_SCHEMA_VERSION };
    }
    this.ready = true;
  }

  async clear(): Promise<void> {
    await this.database.wipe();
    this.graph = EMPTY_GRAPH();
    this.pending = new Set();
    this.ready = false;
  }

  snapshot(): ReplicaSnapshot {
    return {
      ...structuredClone(this.graph), ready: this.ready, ownerId: this.meta.ownerId,
      deviceId: this.meta.deviceId, pendingCount: this.pending.size, persistent: this.persistent
    };
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
      revision: 0
    };
  }

  async writeGraph(changes: Partial<VocabularyGraph>): Promise<void> {
    if (!this.ready) throw new Error("Load the Acervo repository before writing.");
    const next = structuredClone(this.graph);
    const pending: string[] = [];
    const write: Partial<VocabularyGraph> = {};
    (Object.entries(changes) as [EntityKind, Entity[]][]).forEach(([kind, records]) => {
      if (!records) return;
      const target = next[kind] as Entity[];
      records.forEach((record) => {
        if (record.ownerId !== this.meta.ownerId) throw new Error("Cannot write a record owned by another account.");
        const index = target.findIndex((candidate) => candidate.id === record.id);
        if (index < 0) target.push(structuredClone(record));
        else target[index] = structuredClone(record);
        pending.push(pendingKey(kind as RecordStore, record.id));
      });
      write[kind] = structuredClone(records) as never;
    });
    validateGraph(next);
    await this.database.write({ ...write, addPending: pending });
    this.graph = next;
    pending.forEach((key) => this.pending.add(key));
  }

  private async save(kind: EntityKind, input: EntityInput, requestedId?: string): Promise<Entity> {
    if (!this.ready) throw new Error("Load the Acervo repository before writing.");
    const records = this.graph[kind] as Entity[];
    const existing = requestedId ? records.find((record) => record.id === requestedId) : undefined;
    const record = { ...input, id: existing?.id ?? requestedId ?? newId(), ...this.stamp(existing) } as Entity;
    const next = structuredClone(this.graph);
    (next[kind] as Entity[]).splice(existing ? records.indexOf(existing) : records.length, existing ? 1 : 0, record);
    validateGraph(next);
    const key = pendingKey(kind as RecordStore, record.id);
    await this.database.write({ [kind]: [record], addPending: [key] });
    this.graph = next;
    this.pending.add(key);
    return record;
  }

  saveLexeme(input: LexemeInput, id?: string) { return this.save("lexemes", input, id) as Promise<Lexeme>; }
  saveSense(input: SenseInput, id?: string) { return this.save("senses", input, id) as Promise<Sense>; }
  saveAttestation(input: AttestationInput, id?: string) { return this.save("attestations", input, id) as Promise<Attestation>; }
  saveExample(input: ExampleInput, id?: string) { return this.save("examples", input, id) as Promise<Example>; }
  saveImagePrompt(input: ImagePromptInput, id?: string) { return this.save("imagePrompts", input, id) as Promise<ImagePrompt>; }
  saveStudyState(input: StudyStateInput, id?: string) { return this.save("studyStates", input, id) as Promise<StudyState>; }

  async delete(kind: EntityKind, id: string): Promise<void> {
    if (!this.ready) throw new Error("Load the Acervo repository before writing.");
    const changed: Partial<VocabularyGraph> = {};
    const tombstone = <T extends Entity>(store: EntityKind, record: T) => {
      const value = { ...record, ...this.stamp(record), deleted: true } as T;
      const list = (changed[store] ?? []) as T[];
      list.push(value);
      changed[store] = list as never;
    };
    const target = (this.graph[kind] as Entity[]).find((record) => record.id === id);
    if (!target || target.deleted) return;
    tombstone(kind, target);
    if (kind === "lexemes") {
      const senseIds = new Set(this.graph.senses.filter((record) => record.lexemeId === id).map((record) => record.id));
      this.graph.senses.filter((record) => record.lexemeId === id && !record.deleted).forEach((record) => tombstone("senses", record));
      this.graph.attestations.filter((record) => record.lexemeId === id && !record.deleted).forEach((record) => tombstone("attestations", record));
      this.graph.examples.filter((record) => senseIds.has(record.senseId) && !record.deleted).forEach((record) => tombstone("examples", record));
      this.graph.imagePrompts.filter((record) => record.lexemeId === id && !record.deleted).forEach((record) => tombstone("imagePrompts", record));
      this.graph.studyStates.filter((record) => record.lexemeId === id && !record.deleted).forEach((record) => tombstone("studyStates", record));
    } else if (kind === "senses") {
      this.graph.examples.filter((record) => record.senseId === id && !record.deleted).forEach((record) => tombstone("examples", record));
      this.graph.imagePrompts.filter((record) => record.senseId === id && !record.deleted).forEach((record) => tombstone("imagePrompts", record));
    }
    const next = structuredClone(this.graph);
    const pending: string[] = [];
    Object.entries(changed).forEach(([store, updates]) => {
      (updates ?? []).forEach((record) => {
        const list = next[store as EntityKind] as Entity[];
        const index = list.findIndex((candidate) => candidate.id === record.id);
        list[index] = record as Entity;
        pending.push(pendingKey(store as RecordStore, record.id));
      });
    });
    validateGraph(next);
    await this.database.write({ ...changed, addPending: pending });
    this.graph = next;
    pending.forEach((key) => this.pending.add(key));
  }
}

export const repository: AcervoRepository = new LocalAcervoRepository();
