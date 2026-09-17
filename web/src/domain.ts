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
export type EntityKind = "vocabularies" | "topics" | "lexemes" | "senses" | "attestations" | "examples" | "imagePrompts" | "pronunciations" | "studyStates";
/** What a pronunciation reads: a lexeme's headword, a sense's definition, an example's or an attestation's text. */
export const PRONUNCIATION_TARGETS = ["lexeme", "sense", "example", "attestation"] as const;
export type PronunciationTarget = typeof PRONUNCIATION_TARGETS[number];

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

/**
 * One language this owner studies, and how they want it presented (design §03).
 *
 * A vocabulary exists independently of whether it holds any words yet — that is the whole point,
 * since a language has to be configured before its first word can be captured. `languages.ts`
 * supplies the flag and name when the record leaves them empty.
 */
export interface Vocabulary extends SyncFields, OwnedFields {
  id: string;
  language: string;
  /** The language a sense is defined in — usually the target language itself. */
  definitionLang: string;
  /** The languages to translate into, most preferred first. Never empty. */
  glossLangs: string[];
  /**
   * The language usage notes are written in. Neither of the two above: a definition is short and
   * formulaic, so reading it in the target language is cheap practice, while a note is unbounded
   * contrastive prose and the part of an article you skim. Defaults to the first gloss language,
   * and is configurable because immersion becomes the better answer at some point.
   */
  notesLang: string;
  displayName: string | null;
  flag: string | null;
  order: number;
}

export interface Topic extends SyncFields, OwnedFields {
  id: string;
  name: string;
  icon: string | null;
  order: number;
}

export interface Lexeme extends SyncFields, OwnedFields {
  id: string;
  language: string;
  headword: string;
  lemma: string;
  reading: string | null;
  ipa: string | null;
  pos: PartOfSpeech;
  gender: Gender | null;
  register: Register | null;
  dialect: string | null;
  emoji: string | null;
  topicIds: string[];
  status: LexemeStatus;
  shortGloss: string | null;
  notes: string[];
  /**
   * When the spoken-usage corpus was last successfully consulted for this lexeme, or null.
   *
   * One field answers two questions. Null means never consulted, which is what the server's
   * enrichment looks for and what an imported word looks like. Set with no `subtitle` examples means consulted and
   * nothing was good enough — a normal answer for most words, not a gap to fill again. Set and
   * older than the corpus's own `built_at` means the corpus has moved on since.
   *
   * Written only on a *successful* consultation, so a retrieval service that was down leaves the
   * word looking untouched and Try again finds it.
   */
  clipsSearchedAt: string | null;
}

export interface Sense extends SyncFields, OwnedFields {
  id: string;
  lexemeId: string;
  definition: string;
  definitionLang: string;
  glosses: Gloss[];
  domain: string | null;
  /** The sense's own emoji, beside the word's: what the article's sense selector shows. */
  emoji: string | null;
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
  videoTitle: string | null;
  videoChannel: string | null;
  videoStart: number | null;
  videoEnd: number | null;
  /** The corpus's own stable `segment_id`, so the stored text can be audited against the segment. */
  clipRef: string | null;
  imageRef: string | null;
  /**
   * How a native speaker would sound saying this sentence, as a short English direction a voice that
   * takes one can follow. Null reads it neutrally.
   */
  emotion: string | null;
  note: string | null;
  matchedForm: string | null;
  matchedTranslationForm: string | null;
}

/**
 * One sense's picture, and everything about how it came to exist or failed to.
 *
 * The state a picture is in is derived from these fields rather than named by a status:
 * `imageRef` set is *ready*; empty with no attempts is *briefed, not yet drawn*; empty with a
 * `failureReason` is *failed*; and `suppressed` is the owner having ruled on it. A status column
 * would be a fifth thing to keep in step with the four facts that already say all of this.
 *
 * `suppressed` is deliberately not a tombstone. An image prompt's id is derived from its `senseId`,
 * so a tombstoned row is invisible to enrichment, which re-briefs the sense and mints the same id —
 * tombstoning does not prevent regeneration, it guarantees a collision.
 */
export interface ImagePrompt extends SyncFields, OwnedFields {
  id: string;
  lexemeId: string;
  senseId: string | null;
  /** The example the scene was built from, so the article can put the picture under it. */
  exampleId: string | null;
  /** The scene brief. Empty on a picture the owner attached, and on one the writer refused. */
  prompt: string;
  styleId: string;
  seed: number;
  modelId: string;
  promptVersion: string;
  imageRef: string | null;
  /** Absent on a picture the owner supplied — provenance modelled, never a flag. */
  imageModelId: string | null;
  attempts: number;
  failureReason: string | null;
  suppressed: boolean;
}

/**
 * A recording of one spoken field, made by the server when somebody pressed play.
 *
 * Its id is derived from what it reads (`pronunciationId(targetKind, targetId)`), so a field has at
 * most one clip and recording it again rewrites this row. `text` is the words actually spoken: a
 * record edited since no longer matches it, and that is what makes the clip stale.
 */
export interface Pronunciation extends SyncFields, OwnedFields {
  id: string;
  lexemeId: string;
  targetKind: PronunciationTarget;
  targetId: string;
  text: string;
  lang: string;
  /** The emotion the voice was actually given, which is null when it could not take one. */
  emotion: string | null;
  audioRef: string;
  audioMime: string;
  providerId: string;
  modelId: string;
  voice: string | null;
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
  vocabularies: Vocabulary[];
  topics: Topic[];
  lexemes: Lexeme[];
  senses: Sense[];
  attestations: Attestation[];
  examples: Example[];
  imagePrompts: ImagePrompt[];
  pronunciations: Pronunciation[];
  studyStates: StudyState[];
}

export type VocabularyInput = Omit<Vocabulary, "id" | keyof SyncFields | keyof OwnedFields>;
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
  const vocabularyLanguages = new Set<string>();
  graph.vocabularies.forEach((record) => {
    remember(record);
    language(record.language, "Vocabulary language");
    language(record.definitionLang, "Vocabulary definition language");
    stringArray(record.glossLangs, "Vocabulary gloss languages", false);
    record.glossLangs.forEach((code) => language(code, "Vocabulary gloss language"));
    language(record.notesLang, "Vocabulary notes language");
    optionalString(record.displayName, "Vocabulary name");
    optionalString(record.flag, "Vocabulary flag");
    invariant(Number.isSafeInteger(record.order) && record.order >= 0, "Vocabulary order is invalid.");
    // Not a storage constraint (§04 forbids those on replicated collections) — a graph-level one,
    // so two devices that each added the same language offline cannot both be believed at once.
    if (!record.deleted) {
      invariant(!vocabularyLanguages.has(record.language), `Two vocabularies claim ${record.language}.`);
      vocabularyLanguages.add(record.language);
    }
  });

  const topics = new Map<string, Topic>();
  graph.topics.forEach((record) => {
    remember(record);
    invariant(record.name.trim().length > 0, "Topic name is required.");
    optionalString(record.icon, "Topic icon");
    invariant(Number.isSafeInteger(record.order) && record.order >= 0, "Topic order is invalid.");
    topics.set(record.id, record);
  });
  const lexemes = new Map<string, Lexeme>();
  graph.lexemes.forEach((record) => {
    remember(record);
    language(record.language, "Lexeme language");
    invariant(record.headword.trim().length > 0 && record.lemma.trim().length > 0, "Lexeme headword and lemma are required.");
    optionalString(record.reading, "Reading");
    optionalString(record.ipa, "IPA");
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
    if (record.clipsSearchedAt !== null) validateInstant(record.clipsSearchedAt, "Clip search time");
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
    optionalString(record.emoji, "Sense emoji");
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

  const examples = new Map<string, Example>();
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
    [record.modelId, record.videoRef, record.videoTitle, record.videoChannel, record.clipRef, record.imageRef, record.emotion, record.note].forEach((value) => optionalString(value, "Example optional field"));
    [record.videoStart, record.videoEnd].forEach((value) => invariant(value === null || (Number.isSafeInteger(value) && value >= 0), "Example video timing is invalid."));
    // `videoRef` is what every clip field hangs on: a title, a channel, a timing or the corpus's
    // own segment id without one describes a clip that names no video.
    if (record.videoTitle || record.videoChannel || record.clipRef || record.videoStart !== null || record.videoEnd !== null) {
      invariant(record.videoRef, "An example clip title, channel, segment or timing requires a video reference.");
    }
    // Zero reads as "no end", matching the server: the projection emits the stored integer and a
    // clip example without an end carries 0, exactly as one without a start does.
    if (record.videoEnd) invariant(record.videoEnd > (record.videoStart ?? 0), "An example clip must end after it starts.");
    optionalString(record.matchedForm, "Matched form");
    optionalString(record.matchedTranslationForm, "Matched translation form");
    if (record.matchedForm) invariant(record.text.includes(record.matchedForm), "The matched form must occur in the example text.");
    if (record.matchedTranslationForm) {
      invariant(record.translation, "A matched translation form requires a translation.");
      invariant(record.translation.includes(record.matchedTranslationForm), "The matched translation form must occur in the translation.");
    }
    examples.set(record.id, record);
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
    optionalString(record.exampleId, "Image prompt example id");
    if (record.exampleId) {
      const example = examples.get(record.exampleId);
      invariant(example?.senseId === record.senseId, "Image prompt example belongs to another sense.");
      invariant(example.ownerId === record.ownerId, "Image prompt and example must have the same owner.");
    }
    // A brief is three fields or none of them: without the style and the version there is no way to
    // rebuild the prompt that was actually sent, so half a brief reproduces nothing.
    if (record.prompt.trim()) {
      invariant(record.styleId.trim() && record.promptVersion.trim(), "An image brief must name its style and prompt version.");
    }
    invariant(Number.isSafeInteger(record.seed) && record.seed >= 0 && record.seed <= 2147483647, "Image prompt seed is invalid.");
    invariant(Number.isSafeInteger(record.attempts) && record.attempts >= 0, "Image prompt attempt count is invalid.");
    invariant(typeof record.suppressed === "boolean", "Image prompt suppression is invalid.");
    optionalString(record.failureReason, "Image failure reason");
    optionalString(record.imageRef, "Rendered image reference");
    optionalString(record.imageModelId, "Rendering model id");
    // One direction only. A rendering model with nothing rendered is nonsense; a rendered image
    // with no model is a picture the owner attached themselves.
    invariant(!record.imageModelId || Boolean(record.imageRef), "A rendering model without a rendered image is not a record of anything.");
  });

  graph.pronunciations.forEach((record) => {
    remember(record);
    const lexeme = lexemes.get(record.lexemeId);
    invariant(lexeme, "Pronunciation references a missing lexeme.");
    invariant(record.ownerId === lexeme.ownerId, "Pronunciation and lexeme must have the same owner.");
    oneOf(record.targetKind, PRONUNCIATION_TARGETS, "Pronunciation target kind");
    const word = record.targetKind === "lexeme" ? lexemes.get(record.targetId)?.id
      : record.targetKind === "sense" ? senses.get(record.targetId)?.lexemeId
      : record.targetKind === "attestation" ? attestations.get(record.targetId)?.lexemeId
      : senses.get(examples.get(record.targetId)?.senseId ?? "")?.lexemeId;
    invariant(word === record.lexemeId, "A pronounced record must belong to the pronunciation's lexeme.");
    invariant(record.text.length > 0, "Pronunciation text is required.");
    language(record.lang, "Pronunciation language");
    optionalString(record.emotion, "Pronunciation emotion");
    [record.audioRef, record.audioMime, record.providerId, record.modelId].forEach((value) =>
      invariant(typeof value === "string" && value.trim().length > 0, "A pronunciation names its file and who recorded it."));
    optionalString(record.voice, "Pronunciation voice");
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
