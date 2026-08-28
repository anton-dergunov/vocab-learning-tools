export const PARTS_OF_SPEECH = ["noun", "verb", "adj", "adv", "phrase", "idiom", "expression"] as const;
export const GENDERS = ["masculine", "feminine", "common", "neuter"] as const;
export const REGISTERS = ["neutral", "formal", "colloquial", "slang", "vulgar"] as const;
export const LEXEME_STATUSES = ["inbox", "active", "learned", "retired", "suppressed"] as const;
export const SOURCE_KINDS = ["web", "book", "conversation", "video", "lesson", "unknown"] as const;
export const EXAMPLE_ORIGINS = ["attestation", "llm", "tatoeba", "subtitle", "wiktionary", "manual"] as const;

export type PartOfSpeech = typeof PARTS_OF_SPEECH[number];
export type Gender = typeof GENDERS[number];
export type Register = typeof REGISTERS[number];
export type LexemeStatus = typeof LEXEME_STATUSES[number];
export type SourceKind = typeof SOURCE_KINDS[number];
export type ExampleOrigin = typeof EXAMPLE_ORIGINS[number];
export type EntityKind = "topics" | "lexemes" | "senses" | "attestations" | "examples" | "imagePrompts" | "studyStates";

export interface SyncFields {
  deleted: boolean;
  createdAt: string;
  editedAt: string;
  editedBy: string;
  revision: number;
}

export interface OwnedFields {
  ownerId: string;
}

export interface Gloss {
  lang: string;
  terms: string[];
}

export interface Topic extends SyncFields, OwnedFields {
  id: string;
  name: string;
  icon: string | null;
}

export interface Lexeme extends SyncFields, OwnedFields {
  id: string;
  language: string;
  headword: string;
  lemma: string;
  reading: string | null;
  pos: PartOfSpeech;
  gender: Gender | null;
  register: Register | null;
  dialect: string | null;
  emoji: string | null;
  topicIds: string[];
  status: LexemeStatus;
  shortGloss: string | null;
  notes: string[];
}

export interface Sense extends SyncFields, OwnedFields {
  id: string;
  lexemeId: string;
  definition: string;
  definitionLang: string;
  glosses: Gloss[];
  domain: string | null;
  order: number;
}

export interface Attestation extends SyncFields, OwnedFields {
  id: string;
  lexemeId: string;
  text: string;
  translation: string | null;
  sourceUrl: string | null;
  sourceTitle: string | null;
  sourceKind: SourceKind;
  capturedAt: string;
}

export interface Example extends SyncFields, OwnedFields {
  id: string;
  senseId: string;
  text: string;
  textLang: string;
  translation: string | null;
  translationLang: string | null;
  origin: ExampleOrigin;
  sourceAttestationId: string | null;
  modelId: string | null;
  videoRef: string | null;
  imageRef: string | null;
  audioRef: string | null;
  note: string | null;
  approved: boolean;
}

export interface ImagePrompt extends SyncFields, OwnedFields {
  id: string;
  lexemeId: string;
  senseId: string | null;
  prompt: string;
  styleId: string;
  seed: number;
  modelId: string;
  promptVersion: string;
}

export interface StudyState extends SyncFields, OwnedFields {
  id: string;
  lexemeId: string;
  system: string;
  noteId: number | null;
  cardIds: number[];
  reps: number;
  lapses: number;
  stability: number;
  difficulty: number;
  retrievability: number;
  lastReview: string | null;
  syncedAt: string | null;
}

export interface VocabularyGraph {
  topics: Topic[];
  lexemes: Lexeme[];
  senses: Sense[];
  attestations: Attestation[];
  examples: Example[];
  imagePrompts: ImagePrompt[];
  studyStates: StudyState[];
}

export type TopicInput = Omit<Topic, "id" | keyof SyncFields | keyof OwnedFields>;
export type LexemeInput = Omit<Lexeme, "id" | keyof SyncFields | keyof OwnedFields>;
export type SenseInput = Omit<Sense, "id" | keyof SyncFields | keyof OwnedFields>;
export type AttestationInput = Omit<Attestation, "id" | keyof SyncFields | keyof OwnedFields>;
export type ExampleInput = Omit<Example, "id" | keyof SyncFields | keyof OwnedFields>;
export type ImagePromptInput = Omit<ImagePrompt, "id" | keyof SyncFields | keyof OwnedFields>;
export type StudyStateInput = Omit<StudyState, "id" | keyof SyncFields | keyof OwnedFields>;

const RECORD_ID = /^[a-z0-9]{15}$/;
const INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
const LANGUAGE = /^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/;

function invariant(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

function oneOf<T extends string>(value: unknown, values: readonly T[], label: string): asserts value is T {
  invariant(typeof value === "string" && values.includes(value as T), `${label} is invalid.`);
}

function optionalString(value: unknown, label: string): asserts value is string | null {
  invariant(value === null || (typeof value === "string" && value.trim().length > 0), `${label} must be null or non-empty.`);
}

function stringArray(value: unknown, label: string, allowEmpty = true): asserts value is string[] {
  invariant(Array.isArray(value) && value.every((item) => typeof item === "string" && item.trim()), `${label} must contain strings.`);
  invariant(allowEmpty || value.length > 0, `${label} must not be empty.`);
  invariant(new Set(value).size === value.length, `${label} must not contain duplicates.`);
}

function language(value: unknown, label: string): asserts value is string {
  invariant(typeof value === "string" && LANGUAGE.test(value), `${label} must be a BCP-47 language tag.`);
}

export function validateRecordId(value: unknown): asserts value is string {
  invariant(typeof value === "string" && RECORD_ID.test(value), "Record id must contain 15 lowercase letters or digits.");
}

export function validateInstant(value: unknown, label = "Timestamp"): asserts value is string {
  invariant(typeof value === "string" && INSTANT.test(value) && !Number.isNaN(Date.parse(value)), `${label} must be an ISO-8601 UTC instant with milliseconds.`);
}

function syncFields(record: SyncFields & OwnedFields & { id: string }) {
  validateRecordId(record.id);
  validateRecordId(record.ownerId);
  invariant(typeof record.deleted === "boolean", "Deleted must be boolean.");
  validateInstant(record.createdAt, "Created time");
  validateInstant(record.editedAt, "Edited time");
  invariant(/^[a-z0-9]{1,32}$/.test(record.editedBy), "Editor id is invalid.");
  invariant(Number.isSafeInteger(record.revision) && record.revision >= 0, "Revision is invalid.");
}

export function validateGraph(graph: VocabularyGraph): void {
  const ids = new Set<string>();
  let ownerId: string | null = null;
  const remember = (record: SyncFields & OwnedFields & { id: string }) => {
    syncFields(record);
    ownerId ??= record.ownerId;
    invariant(record.ownerId === ownerId, "A vocabulary graph must contain records for one owner only.");
    invariant(!ids.has(record.id), `Duplicate record id ${record.id}.`);
    ids.add(record.id);
  };
  const topics = new Map<string, Topic>();
  graph.topics.forEach((record) => {
    remember(record);
    invariant(record.name.trim().length > 0, "Topic name is required.");
    optionalString(record.icon, "Topic icon");
    topics.set(record.id, record);
  });
  const lexemes = new Map<string, Lexeme>();
  graph.lexemes.forEach((record) => {
    remember(record);
    language(record.language, "Lexeme language");
    invariant(record.headword.trim().length > 0 && record.lemma.trim().length > 0, "Lexeme headword and lemma are required.");
    optionalString(record.reading, "Reading");
    if (record.language.toLowerCase().startsWith("zh")) invariant(Boolean(record.reading?.trim()), "Chinese lexemes require a reading.");
    oneOf(record.pos, PARTS_OF_SPEECH, "Part of speech");
    if (record.gender !== null) oneOf(record.gender, GENDERS, "Gender");
    if (record.register !== null) oneOf(record.register, REGISTERS, "Register");
    optionalString(record.dialect, "Dialect");
    optionalString(record.emoji, "Emoji");
    stringArray(record.topicIds, "Topic ids");
    record.topicIds.forEach((topicId) => {
      validateRecordId(topicId);
      const topic = topics.get(topicId);
      invariant(topic, "Lexeme references a missing topic.");
      invariant(topic.ownerId === record.ownerId, "Lexeme and topic must have the same owner.");
    });
    oneOf(record.status, LEXEME_STATUSES, "Lexeme status");
    optionalString(record.shortGloss, "Short gloss");
    stringArray(record.notes, "Notes");
    lexemes.set(record.id, record);
  });

  const senses = new Map<string, Sense>();
  graph.senses.forEach((record) => {
    remember(record);
    const lexeme = lexemes.get(record.lexemeId);
    invariant(lexeme, "Sense references a missing lexeme.");
    invariant(record.ownerId === lexeme.ownerId, "Sense and lexeme must have the same owner.");
    invariant(record.definition.trim().length > 0, "Sense definition is required.");
    language(record.definitionLang, "Definition language");
    invariant(Number.isSafeInteger(record.order) && record.order >= 0, "Sense order is invalid.");
    optionalString(record.domain, "Sense domain");
    invariant(Array.isArray(record.glosses) && record.glosses.length > 0, "A sense requires at least one gloss group.");
    const glossLanguages = new Set<string>();
    record.glosses.forEach((gloss) => {
      language(gloss.lang, "Gloss language");
      invariant(!glossLanguages.has(gloss.lang), "Gloss languages must be unique per sense.");
      glossLanguages.add(gloss.lang);
      stringArray(gloss.terms, "Gloss terms", false);
    });
    senses.set(record.id, record);
  });

  const attestations = new Map<string, Attestation>();
  graph.attestations.forEach((record) => {
    remember(record);
    const lexeme = lexemes.get(record.lexemeId);
    invariant(lexeme, "Attestation references a missing lexeme.");
    invariant(record.ownerId === lexeme.ownerId, "Attestation and lexeme must have the same owner.");
    invariant(record.text.trim().length > 0, "Attestation text is required.");
    optionalString(record.translation, "Attestation translation");
    optionalString(record.sourceUrl, "Source URL");
    optionalString(record.sourceTitle, "Source title");
    oneOf(record.sourceKind, SOURCE_KINDS, "Source kind");
    validateInstant(record.capturedAt, "Capture time");
    attestations.set(record.id, record);
  });

  graph.examples.forEach((record) => {
    remember(record);
    const sense = senses.get(record.senseId);
    invariant(sense, "Example references a missing sense.");
    invariant(record.ownerId === sense.ownerId, "Example and sense must have the same owner.");
    invariant(record.text.trim().length > 0, "Example text is required.");
    language(record.textLang, "Example language");
    optionalString(record.translation, "Example translation");
    optionalString(record.translationLang, "Translation language");
    invariant(Boolean(record.translation) === Boolean(record.translationLang), "Translation and translation language must be supplied together.");
    if (record.translationLang) language(record.translationLang, "Translation language");
    oneOf(record.origin, EXAMPLE_ORIGINS, "Example origin");
    optionalString(record.sourceAttestationId, "Source attestation id");
    if (record.origin === "attestation") invariant(record.sourceAttestationId, "Attestation examples require a source attestation.");
    if (record.sourceAttestationId) {
      const attestation = attestations.get(record.sourceAttestationId);
      invariant(attestation, "Example references a missing attestation.");
      invariant(record.ownerId === attestation.ownerId, "Example and attestation must have the same owner.");
      invariant(attestation.lexemeId === sense.lexemeId, "Example sense and attestation must belong to one lexeme.");
    }
    [record.modelId, record.videoRef, record.imageRef, record.audioRef, record.note].forEach((value) => optionalString(value, "Example optional field"));
    invariant(typeof record.approved === "boolean", "Example approval is invalid.");
  });

  graph.imagePrompts.forEach((record) => {
    remember(record);
    const lexeme = lexemes.get(record.lexemeId);
    invariant(lexeme, "Image prompt references a missing lexeme.");
    invariant(record.ownerId === lexeme.ownerId, "Image prompt and lexeme must have the same owner.");
    optionalString(record.senseId, "Image prompt sense id");
    if (record.senseId) {
      const sense = senses.get(record.senseId);
      invariant(sense?.lexemeId === record.lexemeId, "Image prompt sense belongs to another lexeme.");
      invariant(sense.ownerId === record.ownerId, "Image prompt and sense must have the same owner.");
    }
    invariant(record.prompt.trim() && record.styleId.trim() && record.modelId.trim() && record.promptVersion.trim(), "Image prompt fields are required.");
    invariant(Number.isSafeInteger(record.seed) && record.seed >= 0 && record.seed <= 2147483647, "Image prompt seed is invalid.");
  });

  graph.studyStates.forEach((record) => {
    remember(record);
    const lexeme = lexemes.get(record.lexemeId);
    invariant(lexeme, "Study state references a missing lexeme.");
    invariant(record.ownerId === lexeme.ownerId, "Study state and lexeme must have the same owner.");
    invariant(record.system.trim().length > 0, "Study system is required.");
    invariant(record.noteId === null || (Number.isSafeInteger(record.noteId) && record.noteId >= 0), "Study note id is invalid.");
    invariant(Array.isArray(record.cardIds) && record.cardIds.every((id) => Number.isSafeInteger(id) && id >= 0), "Study card ids are invalid.");
    [record.reps, record.lapses].forEach((value) => invariant(Number.isSafeInteger(value) && value >= 0, "Study count is invalid."));
    [record.stability, record.difficulty].forEach((value) => invariant(Number.isFinite(value) && value >= 0, "Study metric is invalid."));
    invariant(Number.isFinite(record.retrievability) && record.retrievability >= 0 && record.retrievability <= 1, "Retrievability is invalid.");
    if (record.lastReview) validateInstant(record.lastReview, "Last review");
    if (record.syncedAt) validateInstant(record.syncedAt, "Study sync time");
  });
}

export function effectiveShortGloss(graph: VocabularyGraph, lexemeId: string): string | null {
  const lexeme = graph.lexemes.find((candidate) => candidate.id === lexemeId && !candidate.deleted);
  if (!lexeme) return null;
  if (lexeme.shortGloss?.trim()) return lexeme.shortGloss.trim();
  const sense = graph.senses
    .filter((candidate) => candidate.lexemeId === lexemeId && !candidate.deleted)
    .sort((left, right) => left.order - right.order || left.id.localeCompare(right.id))[0];
  return sense?.glosses[0]?.terms[0] ?? null;
}
