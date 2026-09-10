/**
 * Pure derivation from a vocabulary graph to the view models the interface renders.
 *
 * Nothing here touches storage or the network, so the whole list/article/search surface is
 * testable without a replica. Tombstone filtering lives here and only here.
 */

import {
  effectiveShortGloss,
  type Attestation, type Example, type ImagePrompt, type Lexeme, type LexemeStatus,
  type OwnedFields, type Sense, type StudyState, type SyncFields, type Topic, type Vocabulary,
  type VocabularyGraph
} from "./domain";
import { glossLanguagesFor, languageOf, presentationOf, type LanguagePresentation } from "./languages";
// Type-only, so it is erased at build time and the cycle with `yaml.ts` — which imports `Article`
// from here — never exists at runtime.
import type { ArticleDraft } from "./yaml";

export type SortKey = "recent" | "alpha" | "hard";
/** A topic record id, or one of the two synthetic collections the rail offers. */
export type TopicSelection = "all" | "inbox" | string;

export interface ListRow {
  id: string;
  headword: string;
  reading: string | null;
  emoji: string | null;
  shortGloss: string;
  senseCount: number;
  status: LexemeStatus;
  /** Zero when the word has never been scheduled, otherwise one to four bars. */
  strength: number;
  strengthLabel: string;
}

export interface ArticleSense {
  sense: Sense;
  examples: Example[];
  images: ImagePrompt[];
}

export interface Article {
  lexeme: Lexeme;
  topics: Topic[];
  senses: ArticleSense[];
  attestations: Attestation[];
  /** Lexeme-level prompts — the card image, as opposed to a per-sense one. */
  images: ImagePrompt[];
  study: StudyState | null;
}

/**
 * What is still missing a picture, and why.
 *
 * A **query, not a queue** — the rule the whole image design rests on, applied on the client. The
 * replica already holds every sense and every image prompt, so "what is left" is derived on each
 * read rather than stored; a word deleted mid-run simply leaves it, and nothing has to be told.
 *
 * This is also how the interface reports work the *server's* sweep is doing. There is no job store
 * to poll and deliberately none to build: an owner-scoped job record would replicate to every
 * device, which is the question `docs/plans/nas-to-mac-job-queue.md` declined to answer.
 */
/** A picture with enough of its surroundings to be named in a list. */
export interface ImageWorkEntry {
  prompt: ImagePrompt;
  headword: string;
  /** 1-based, the way the article numbers senses, so the two can be read together. */
  senseNumber: number;
}

export interface ImageWork {
  /** Senses with no live prompt at all, so nothing has even been briefed for them. */
  unbriefed: { lexemeId: string; senseId: string }[];
  /** Briefed but not yet drawn, and not out of attempts. */
  undrawn: ImageWorkEntry[];
  /** Attempted and still without a picture. `isRetryable` says which of these will be tried again. */
  failed: ImageWorkEntry[];
  /** Ruled out by the owner, or refused by the writer. Counted, never retried. */
  suppressed: ImageWorkEntry[];
  /**
   * Pictures that exist, most recently written first.
   *
   * A list rather than a count, and derived rather than remembered. The panel used to show a
   * session-scoped log of what this device had drawn, which was wrong twice over: it emptied on
   * every reload, so five pictures showed as two, and it could never mention the pictures the
   * server's sweep drew while nobody was looking. `editedAt` is on the record, so this answers
   * "what has been made lately" for both engines and survives a restart.
   */
  drawn: ImageWorkEntry[];
}

export function imageWork(graph: VocabularyGraph): ImageWork {
  const prompts = live(graph.imagePrompts);
  const bySense = new Map(prompts.filter((p) => p.senseId).map((p) => [p.senseId!, p]));
  const words = new Map(live(graph.lexemes).map((lexeme) => [lexeme.id, lexeme]));
  // Sense id -> the number the article prints beside it. Derived from the sort rather than from
  // `sense.order`, which is the writer's ordinal and need not start at zero or run consecutively.
  const numbered = new Map<string, number>();
  const counted = new Map<string, number>();
  live(graph.senses)
    .slice()
    .sort((left, right) => left.order - right.order || left.id.localeCompare(right.id))
    .forEach((sense) => {
      const next = (counted.get(sense.lexemeId) ?? 0) + 1;
      counted.set(sense.lexemeId, next);
      numbered.set(sense.id, next);
    });

  const work: ImageWork = { unbriefed: [], undrawn: [], failed: [], suppressed: [], drawn: [] };
  const entry = (prompt: ImagePrompt, lexemeId: string, senseId: string): ImageWorkEntry => ({
    prompt,
    headword: words.get(lexemeId)?.headword ?? "",
    senseNumber: numbered.get(senseId) ?? 1
  });

  live(graph.senses).forEach((sense) => {
    if (!words.has(sense.lexemeId)) return;
    const prompt = bySense.get(sense.id);
    if (!prompt) {
      work.unbriefed.push({ lexemeId: sense.lexemeId, senseId: sense.id });
      return;
    }
    const found = entry(prompt, sense.lexemeId, sense.id);
    if (prompt.imageRef) work.drawn.push(found);
    else if (prompt.suppressed) work.suppressed.push(found);
    // Attempted and still blank. Whether anything will try again is `isRetryable`'s question, not
    // a second list: the record says what happened and the threshold says what to do about it.
    else if (prompt.attempts > 0) work.failed.push(found);
    else work.undrawn.push(found);
  });

  work.drawn.sort((left, right) => right.prompt.editedAt.localeCompare(left.prompt.editedAt));
  work.failed.sort((left, right) => right.prompt.editedAt.localeCompare(left.prompt.editedAt));
  return work;
}

/** Whether anything more can be tried for this picture without the owner asking for it. */
export function isRetryable(prompt: ImagePrompt, maxAttempts: number): boolean {
  return !prompt.suppressed && !prompt.imageRef && prompt.attempts < maxAttempts;
}

export interface LanguageOption extends LanguagePresentation {
  count: number;
  /** False for a language that has words but no vocabulary record behind it any more. */
  configured: boolean;
}

export interface TopicOption {
  id: TopicSelection;
  name: string;
  icon: string;
  count: number | null;
}

const live = <T extends SyncFields>(records: T[]): T[] => records.filter((record) => !record.deleted);

const LEADING_ARTICLE = /^(el|la|los|las|le|les|der|die|das|the) /i;

function sortKeyOf(lexeme: Lexeme): string {
  return lexeme.headword.replace(LEADING_ARTICLE, "");
}

export function strengthOf(study: StudyState | null): number {
  if (!study) return 0;
  return Math.min(4, Math.max(1, Math.round(Math.log10(Math.max(study.stability, 1.1)) * 1.7 + 1)));
}

export function lexemesIn(graph: VocabularyGraph, language: string): Lexeme[] {
  return live(graph.lexemes).filter((lexeme) => lexeme.language === language);
}

export function vocabularies(graph: VocabularyGraph): Vocabulary[] {
  return live(graph.vocabularies)
    .slice()
    .sort((left, right) => left.order - right.order || left.language.localeCompare(right.language));
}

export function vocabularyFor(graph: VocabularyGraph, language: string): Vocabulary | null {
  return live(graph.vocabularies).find((entry) => entry.language === language) ?? null;
}

/**
 * Every language the switcher offers: the ones configured, in the owner's order, plus any that
 * still hold words without a record behind them.
 *
 * A configured language with no words has to appear, or a vocabulary could never be filled — there
 * would be nowhere to switch to before the first capture. That is why this is no longer derived
 * from the lexemes alone.
 */
export function languageOptions(graph: VocabularyGraph): LanguageOption[] {
  const counts = new Map<string, number>();
  live(graph.lexemes).forEach((lexeme) => counts.set(lexeme.language, (counts.get(lexeme.language) ?? 0) + 1));
  const configured = vocabularies(graph).map((entry) => ({
    ...presentationOf(entry), count: counts.get(entry.language) ?? 0, configured: true
  }));
  const known = new Set(configured.map((option) => option.code));
  const orphaned = [...counts.entries()]
    .filter(([code]) => !known.has(code))
    .map(([code, count]) => ({ ...languageOf(code), count, configured: false }))
    .sort((left, right) => right.count - left.count || left.name.localeCompare(right.name));
  return [...configured, ...orphaned];
}

export function inboxCount(graph: VocabularyGraph, language: string): number {
  return lexemesIn(graph, language).filter((lexeme) => lexeme.status === "inbox").length;
}

export function topicOptions(graph: VocabularyGraph, language: string): TopicOption[] {
  const filed = lexemesIn(graph, language).filter((lexeme) => lexeme.status !== "inbox");
  return live(graph.topics)
    .slice()
    .sort((left, right) => left.order - right.order || left.name.localeCompare(right.name))
    .map((topic) => ({
      id: topic.id,
      name: topic.name,
      icon: topic.icon ?? "📌",
      count: filed.filter((lexeme) => lexeme.topicIds.includes(topic.id)).length || null
    }));
}

export function sensesOf(graph: VocabularyGraph, lexemeId: string): Sense[] {
  return live(graph.senses)
    .filter((sense) => sense.lexemeId === lexemeId)
    .sort((left, right) => left.order - right.order || left.id.localeCompare(right.id));
}

/**
 * The one-line form: the curated override when there is one, otherwise the first sense's gloss in
 * the language configured for this vocabulary language. A projection, never a stored second record.
 */
export function shortGlossOf(graph: VocabularyGraph, lexeme: Lexeme): string {
  if (lexeme.shortGloss?.trim()) return lexeme.shortGloss.trim();
  const sense = sensesOf(graph, lexeme.id)[0];
  if (sense) {
    const preferred = glossLanguagesFor(lexeme.language, graph.vocabularies)
      .map((lang) => sense.glosses.find((gloss) => gloss.lang === lang))
      .find(Boolean);
    const gloss = preferred ?? sense.glosses[0];
    if (gloss) return gloss.terms.join("; ");
  }
  return effectiveShortGloss(graph, lexeme.id) ?? "";
}

function searchHaystack(graph: VocabularyGraph, lexeme: Lexeme): string {
  const senses = sensesOf(graph, lexeme.id);
  return [
    lexeme.headword, lexeme.lemma, lexeme.reading ?? "", lexeme.shortGloss ?? "",
    ...senses.map((sense) => sense.definition),
    ...senses.flatMap((sense) => sense.glosses.flatMap((gloss) => gloss.terms))
  ].join(" ").toLowerCase();
}

export interface ListQuery {
  language: string;
  topic: TopicSelection;
  query: string;
  sort: SortKey;
}

export function visibleRows(graph: VocabularyGraph, { language, topic, query, sort }: ListQuery): ListRow[] {
  const search = query.trim().toLowerCase();
  let rows = lexemesIn(graph, language);
  if (search) {
    rows = rows.filter((lexeme) => searchHaystack(graph, lexeme).includes(search));
  } else if (topic === "inbox") {
    rows = rows.filter((lexeme) => lexeme.status === "inbox");
  } else {
    rows = rows.filter((lexeme) => lexeme.status !== "inbox");
    if (topic !== "all") rows = rows.filter((lexeme) => lexeme.topicIds.includes(topic));
  }
  const studyOf = (lexeme: Lexeme) => studyStateOf(graph, lexeme.id);
  const sorters: Record<SortKey, (left: Lexeme, right: Lexeme) => number> = {
    recent: (left, right) => right.createdAt.localeCompare(left.createdAt),
    alpha: (left, right) => sortKeyOf(left).localeCompare(sortKeyOf(right), language),
    hard: (left, right) => (studyOf(right)?.difficulty ?? -1) - (studyOf(left)?.difficulty ?? -1)
  };
  return rows.slice().sort(sorters[sort]).map((lexeme) => {
    const study = studyOf(lexeme);
    return {
      id: lexeme.id,
      headword: lexeme.headword,
      reading: lexeme.reading,
      emoji: lexeme.emoji,
      shortGloss: shortGlossOf(graph, lexeme),
      senseCount: sensesOf(graph, lexeme.id).length,
      status: lexeme.status,
      strength: strengthOf(study),
      strengthLabel: study
        ? `stability ${study.stability} d · difficulty ${study.difficulty}`
        : "not scheduled yet"
    };
  });
}

export function studyStateOf(graph: VocabularyGraph, lexemeId: string): StudyState | null {
  return live(graph.studyStates).find((state) => state.lexemeId === lexemeId) ?? null;
}

/**
 * Neither examples nor attestations carry an order field, so graph order would be whatever the last
 * sync happened to deliver. The YAML projection is edited by hand and diffed against what was
 * shown, so the sequence has to be the same every time it is rendered.
 */
const byAge = <T extends SyncFields & { id: string }>(records: T[]): T[] =>
  [...records].sort((left, right) =>
    left.createdAt.localeCompare(right.createdAt) || left.id.localeCompare(right.id));

/**
 * At most one picture per sense, which is what §02 decided and what the article should show.
 *
 * Belt and braces rather than the mechanism: an image prompt's id is *derived* from its sense, so a
 * second row for one sense cannot be created any more. It could be before — `saveArticle` minted a
 * random id while the server derived one, so importing a bundle left a sense with an empty frame
 * carrying the brief and a picture carrying none. This keeps such a pair from being *shown* while
 * it exists in a replica written by the older code.
 *
 * The one kept is the drawn one, then the most recently edited: a picture beats a bare brief, and
 * "the newest thing that happened to this sense" is the only other honest tie-break.
 */
function onePicture(images: ImagePrompt[]): ImagePrompt[] {
  if (images.length < 2) return images;
  const ranked = images.slice().sort((left, right) =>
    Number(Boolean(right.imageRef)) - Number(Boolean(left.imageRef))
    || right.editedAt.localeCompare(left.editedAt)
  );
  return [ranked[0]];
}

export function articleFor(graph: VocabularyGraph, lexemeId: string): Article | null {
  const lexeme = live(graph.lexemes).find((candidate) => candidate.id === lexemeId);
  if (!lexeme) return null;
  const examples = live(graph.examples);
  const images = live(graph.imagePrompts).filter((image) => image.lexemeId === lexemeId);
  return {
    lexeme,
    topics: lexeme.topicIds
      .map((id) => live(graph.topics).find((topic) => topic.id === id))
      .filter((topic): topic is Topic => Boolean(topic)),
    senses: sensesOf(graph, lexemeId).map((sense) => ({
      sense,
      examples: byAge(examples.filter((example) => example.senseId === sense.id)),
      images: onePicture(byAge(images.filter((image) => image.senseId === sense.id)))
    })),
    attestations: byAge(live(graph.attestations).filter((attestation) => attestation.lexemeId === lexemeId)),
    // Without these the card image is invisible in the projection, so saving would orphan it.
    images: byAge(images.filter((image) => image.senseId === null)),
    study: studyStateOf(graph, lexemeId)
  };
}

/* ── the second feeder ──────────────────────────────────────────────────
   An article the store has never seen — what capture proposes, or what you have typed into the
   editor and not saved — assembled into the same view model a stored one produces, so there is one
   renderer rather than a second surface for reviewing a proposal (design §16).

   The output is RENDER-ONLY. It is not a graph, it is not validated, and it must never be written:
   the one writer is `repository.saveArticle(parseArticle(text))`, which reads the document again
   rather than trusting anything assembled here. The placeholder ids below carry a `draft:` prefix
   precisely so a leak fails loudly — no record id is allowed to look like that. */

/** What a record that has never been stored knows about itself: nothing. */
const UNSAVED: SyncFields & OwnedFields = {
  ownerId: "", deleted: false, createdAt: "", editedAt: "", editedBy: "", revision: 0
};

/** A React key for a record the document did not name, stable across re-parses of the same text. */
const placeholder = (path: string) => `draft:${path}`;

function topicsFromNames(graph: VocabularyGraph, names: string[]): Topic[] {
  const stored = live(graph.topics);
  return names.map((name) => {
    const match = stored.find((topic) => topic.name.toLowerCase() === name.toLowerCase());
    // A name that matches nothing is still shown. The preview's job is to say what the document
    // says; refusing an unknown topic is `saveArticle`'s job, and it does it on the way out.
    return match ?? { ...UNSAVED, id: placeholder(`topic:${name}`), name, icon: null, order: 0 };
  });
}

export function articleFromDraft(graph: VocabularyGraph, draft: ArticleDraft): Article {
  const lexemeId = draft.id ?? placeholder("lexeme");
  const topics = topicsFromNames(graph, draft.topics);
  const lexeme: Lexeme = {
    ...UNSAVED,
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
    topicIds: topics.map((topic) => topic.id),
    status: draft.status,
    shortGloss: draft.shortGloss,
    notes: draft.notes
  };

  const promptsOf = (drafts: ArticleDraft["images"], senseId: string | null, path: string): ImagePrompt[] =>
    drafts.map((image, index) => ({
      ...UNSAVED,
      id: image.id ?? placeholder(`${path}:${index}`),
      lexemeId,
      senseId,
      exampleId: image.exampleId,
      // A draft is a proposal, so nothing has been attempted, refused or ruled on yet.
      attempts: 0,
      failureReason: null,
      suppressed: false,
      prompt: image.prompt,
      styleId: image.styleId,
      seed: image.seed,
      modelId: image.modelId,
      promptVersion: image.promptVersion,
      imageRef: image.imageRef,
      imageModelId: image.imageModelId
    }));

  return {
    lexeme,
    topics,
    // Document order throughout, not `byAge`: the placeholder timestamps are all equal, and the
    // order you wrote is the order you are reviewing.
    senses: draft.senses.map((senseDraft, senseIndex) => {
      const senseId = senseDraft.id ?? placeholder(`sense:${senseIndex}`);
      const sense: Sense = {
        ...UNSAVED,
        id: senseId,
        lexemeId,
        definition: senseDraft.definition,
        definitionLang: senseDraft.definitionLang,
        glosses: senseDraft.glosses,
        domain: senseDraft.domain,
        order: senseDraft.order
      };
      return {
        sense,
        examples: senseDraft.examples.map((example, index): Example => ({
          ...UNSAVED,
          id: example.id ?? placeholder(`example:${senseIndex}:${index}`),
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
          approved: example.approved
        })),
        images: promptsOf(senseDraft.images, senseId, `senseImage:${senseIndex}`)
      };
    }),
    attestations: draft.attestations.map((attestation, index): Attestation => ({
      ...UNSAVED,
      id: attestation.id ?? placeholder(`attestation:${index}`),
      lexemeId,
      text: attestation.text,
      translation: attestation.translation,
      sourceUrl: attestation.sourceUrl,
      sourceTitle: attestation.sourceTitle,
      sourceKind: attestation.sourceKind,
      capturedAt: attestation.capturedAt
    })),
    images: promptsOf(draft.images, null, "image"),
    // A document cannot carry study state, so a proposal never has any to show.
    study: null
  };
}
