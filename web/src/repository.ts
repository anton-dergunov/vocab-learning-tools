import {
  validateGraph,
  type Attestation, type AttestationInput, type EntityKind, type Example, type ExampleInput,
  type ImagePrompt, type ImagePromptInput, type Lexeme, type LexemeInput, type Sense, type SenseInput,
  type OwnedFields, type StudyState, type StudyStateInput, type SyncFields, type Topic, type TopicInput,
  type VocabularyGraph
} from "./domain";
import { createLocalDatabase, MemoryDatabase, RECORD_STORES, type LocalDatabase, type ReplicaMeta } from "./localDatabase";
import { newDeviceId, newId, nowInstant } from "./ids";
import type { ArticleDraft, ImagePromptDraft } from "./yaml";

export const LOCAL_SCHEMA_VERSION = 4;

const EMPTY_GRAPH = (): VocabularyGraph => ({
  topics: [], lexemes: [], senses: [], attestations: [], examples: [], imagePrompts: [], studyStates: []
});

type Entity = Topic | Lexeme | Sense | Attestation | Example | ImagePrompt | StudyState;
type EntityInput = TopicInput | LexemeInput | SenseInput | AttestationInput | ExampleInput | ImagePromptInput | StudyStateInput;

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
export interface RemoteGraph {
  push(changes: Partial<VocabularyGraph>): Promise<RemoteWrite>;
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
  saveArticle(draft: ArticleDraft): Promise<string>;
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
        topics: contents.topics,
        lexemes: contents.lexemes,
        senses: contents.senses,
        attestations: contents.attestations,
        examples: contents.examples,
        imagePrompts: contents.imagePrompts,
        studyStates: contents.studyStates
      };
      validateGraph(graph);
      const allRecords: Entity[][] = [
        graph.topics, graph.lexemes, graph.senses, graph.attestations, graph.examples, graph.imagePrompts, graph.studyStates
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
  private commit(changes: Partial<VocabularyGraph>): Promise<void> {
    return this.serialize(() => this.send(changes));
  }

  private async send(changes: Partial<VocabularyGraph>): Promise<void> {
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
    const result = await this.remote.push(changes);
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

  saveTopic(input: TopicInput, id?: string) { return this.save("topics", input, id) as Promise<Topic>; }
  saveLexeme(input: LexemeInput, id?: string) { return this.save("lexemes", input, id) as Promise<Lexeme>; }
  saveSense(input: SenseInput, id?: string) { return this.save("senses", input, id) as Promise<Sense>; }
  saveAttestation(input: AttestationInput, id?: string) { return this.save("attestations", input, id) as Promise<Attestation>; }
  saveExample(input: ExampleInput, id?: string) { return this.save("examples", input, id) as Promise<Example>; }
  saveImagePrompt(input: ImagePromptInput, id?: string) { return this.save("imagePrompts", input, id) as Promise<ImagePrompt>; }
  saveStudyState(input: StudyStateInput, id?: string) { return this.save("studyStates", input, id) as Promise<StudyState>; }

  /**
   * Applies a whole article, edited as YAML, in one write.
   *
   * The document is the complete article, so the diff needs no content matching: a record carrying
   * an id is the one it names, a record without one is new, and a stored record the document no
   * longer mentions is removed. Nothing is recreated — ids stay put across an edit, which is what
   * keeps the Anki note join (§10), the image seed derived from the lexeme id (§09) and `createdAt`
   * from being reset every time a typo is fixed.
   *
   * One batch, one round trip, all or nothing: half an applied article is worse than none.
   */
  async saveArticle(draft: ArticleDraft): Promise<string> {
    if (!this.ready) throw new Error("Load the Acervo repository before writing.");
    const changed: Partial<VocabularyGraph> = {};
    const change = <T extends Entity>(store: EntityKind, value: T) => {
      const list = (changed[store] ?? []) as T[];
      list.push(value);
      changed[store] = list as never;
    };
    const live = <T extends Entity>(records: T[]): T[] => records.filter((record) => !record.deleted);
    const find = <T extends Entity>(records: T[], id: string | null): T | undefined =>
      id ? records.find((record) => record.id === id) : undefined;

    const lexemeId = draft.id ?? newId();
    const existingLexeme = find(this.graph.lexemes, draft.id);
    if (draft.id && (!existingLexeme || existingLexeme.deleted)) {
      throw new Error("This document names an entry that is not in your vocabulary, so it was not saved.");
    }

    const topicIds = draft.topics.map((name) => {
      const topic = live(this.graph.topics)
        .find((candidate) => candidate.name.toLowerCase() === name.trim().toLowerCase());
      if (!topic) {
        const known = live(this.graph.topics).map((candidate) => candidate.name).sort().join(", ");
        throw new Error(
          `There is no topic called "${name}". Topics are created deliberately; the ones you have are: ${known || "none yet"}.`
        );
      }
      return topic.id;
    });

    change("lexemes", {
      ...existingLexeme,
      id: lexemeId,
      language: draft.language,
      headword: draft.headword,
      lemma: draft.lemma,
      reading: draft.reading,
      ipa: draft.ipa,
      pos: draft.pos,
      gender: draft.gender,
      register: draft.register,
      dialect: draft.dialect,
      emoji: draft.emoji,
      topicIds,
      status: draft.status,
      shortGloss: draft.shortGloss,
      notes: draft.notes,
      ...this.stamp(existingLexeme)
    } as Lexeme);

    // An id in the document that belongs to a different entry would silently steal that record.
    const claim = <T extends Entity>(records: T[], id: string | null, owner: (record: T) => boolean): T | undefined => {
      const existing = find(records, id);
      if (!existing) {
        if (id) throw new Error(`This document names a record that is not in your vocabulary (${id}), so it was not saved.`);
        return undefined;
      }
      if (!owner(existing)) {
        throw new Error(`The id ${id} belongs to a different entry, so this document was not saved.`);
      }
      return existing;
    };

    const prompt = (image: ImagePromptDraft, senseId: string | null): string => {
      const existing = claim(this.graph.imagePrompts, image.id, (record) => record.lexemeId === lexemeId);
      const id = image.id ?? newId();
      change("imagePrompts", {
        ...existing,
        id,
        lexemeId,
        senseId,
        prompt: image.prompt,
        styleId: image.styleId,
        seed: image.seed,
        modelId: image.modelId,
        promptVersion: image.promptVersion,
        imageRef: image.imageRef,
        imageModelId: image.imageModelId,
        ...this.stamp(existing)
      } as ImagePrompt);
      return id;
    };

    const keptSenses = new Set<string>();
    const keptExamples = new Set<string>();
    const keptAttestations = new Set<string>();
    const keptPrompts = new Set<string>();

    draft.attestations.forEach((attestation) => {
      const existing = claim(this.graph.attestations, attestation.id, (record) => record.lexemeId === lexemeId);
      const id = attestation.id ?? newId();
      keptAttestations.add(id);
      change("attestations", {
        ...existing,
        id,
        lexemeId,
        text: attestation.text,
        translation: attestation.translation,
        sourceUrl: attestation.sourceUrl,
        sourceTitle: attestation.sourceTitle,
        sourceKind: attestation.sourceKind,
        // Editable like any other field; a new attestation that does not name one is captured now.
        capturedAt: attestation.capturedAt.trim() || existing?.capturedAt || this.instant(),
        ...this.stamp(existing)
      } as Attestation);
    });

    draft.senses.forEach((sense) => {
      const existing = claim(this.graph.senses, sense.id, (record) => record.lexemeId === lexemeId);
      const senseId = sense.id ?? newId();
      keptSenses.add(senseId);
      change("senses", {
        ...existing,
        id: senseId,
        lexemeId,
        definition: sense.definition,
        definitionLang: sense.definitionLang,
        glosses: sense.glosses,
        domain: sense.domain,
        order: sense.order,
        ...this.stamp(existing)
      } as Sense);

      sense.examples.forEach((example) => {
        // An example belongs to this article when the sense it is stored under does. That also
        // allows moving one between senses of the same entry: the id is kept, the parent changes.
        const current = claim(this.graph.examples, example.id, (record) =>
          this.graph.senses.some((candidate) => candidate.id === record.senseId && candidate.lexemeId === lexemeId));
        const id = example.id ?? newId();
        keptExamples.add(id);
        change("examples", {
          ...current,
          id,
          senseId,
          text: example.text,
          textLang: example.textLang,
          translation: example.translation,
          translationLang: example.translationLang,
          origin: example.origin,
          sourceAttestationId: example.sourceAttestationId,
          modelId: example.modelId,
          videoRef: example.videoRef,
          videoTitle: example.videoTitle,
          videoStart: example.videoStart,
          imageRef: example.imageRef,
          audioRef: example.audioRef,
          note: example.note,
          matchedForm: example.matchedForm,
          matchedTranslationForm: example.matchedTranslationForm,
          approved: example.approved,
          ...this.stamp(current)
        } as Example);
      });

      sense.images.forEach((image) => keptPrompts.add(prompt(image, senseId)));
    });

    draft.images.forEach((image) => keptPrompts.add(prompt(image, null)));

    // Whatever the document stopped mentioning. A tombstone rather than a deletion, because a pull
    // asks for `revision > cursor` and a row that is simply gone has no revision left to send.
    const tombstone = <T extends Entity>(store: EntityKind, record: T) => {
      change(store, { ...record, ...this.stamp(record), deleted: true } as T);
    };
    const senseIds = new Set(live(this.graph.senses).filter((record) => record.lexemeId === lexemeId).map((record) => record.id));
    live(this.graph.senses)
      .filter((record) => record.lexemeId === lexemeId && !keptSenses.has(record.id))
      .forEach((record) => tombstone("senses", record));
    live(this.graph.attestations)
      .filter((record) => record.lexemeId === lexemeId && !keptAttestations.has(record.id))
      .forEach((record) => tombstone("attestations", record));
    // Covers both an example removed on its own and one carried away by its sense.
    live(this.graph.examples)
      .filter((record) => senseIds.has(record.senseId) && !keptExamples.has(record.id))
      .forEach((record) => tombstone("examples", record));
    live(this.graph.imagePrompts)
      .filter((record) => record.lexemeId === lexemeId && !keptPrompts.has(record.id))
      .forEach((record) => tombstone("imagePrompts", record));

    await this.commit(changed);
    return lexemeId;
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
      this.graph.studyStates.filter((record) => record.lexemeId === id && !record.deleted).forEach((record) => tombstone("studyStates", record));
    } else if (kind === "senses") {
      this.graph.examples.filter((record) => record.senseId === id && !record.deleted).forEach((record) => tombstone("examples", record));
      this.graph.imagePrompts.filter((record) => record.senseId === id && !record.deleted).forEach((record) => tombstone("imagePrompts", record));
    }
    await this.commit(changed);
  }
}

export const repository: AcervoRepository = new LocalAcervoRepository();
