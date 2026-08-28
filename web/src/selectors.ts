/**
 * Pure derivation from a vocabulary graph to the view models the interface renders.
 *
 * Nothing here touches storage or the network, so the whole list/article/search surface is
 * testable without a replica. Tombstone filtering lives here and only here.
 */

import {
  effectiveShortGloss,
  type Attestation, type Example, type ImagePrompt, type Lexeme, type LexemeStatus,
  type Sense, type StudyState, type SyncFields, type Topic, type VocabularyGraph
} from "./domain";
import { glossLanguagesFor, languageOf, type LanguagePresentation } from "./languages";
import { pendingKey } from "./localDatabase";

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
  study: StudyState | null;
  synced: boolean;
}

export interface LanguageOption extends LanguagePresentation {
  count: number;
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

export function languageOptions(graph: VocabularyGraph): LanguageOption[] {
  const counts = new Map<string, number>();
  live(graph.lexemes).forEach((lexeme) => counts.set(lexeme.language, (counts.get(lexeme.language) ?? 0) + 1));
  return [...counts.entries()]
    .map(([code, count]) => ({ ...languageOf(code), count }))
    .sort((left, right) => right.count - left.count || left.name.localeCompare(right.name));
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
    const preferred = glossLanguagesFor(lexeme.language)
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

export function articleFor(graph: VocabularyGraph, lexemeId: string, pending: string[]): Article | null {
  const lexeme = live(graph.lexemes).find((candidate) => candidate.id === lexemeId);
  if (!lexeme) return null;
  const examples = live(graph.examples);
  const images = live(graph.imagePrompts);
  return {
    lexeme,
    topics: lexeme.topicIds
      .map((id) => live(graph.topics).find((topic) => topic.id === id))
      .filter((topic): topic is Topic => Boolean(topic)),
    senses: sensesOf(graph, lexemeId).map((sense) => ({
      sense,
      examples: examples.filter((example) => example.senseId === sense.id),
      images: images.filter((image) => image.senseId === sense.id)
    })),
    attestations: live(graph.attestations).filter((attestation) => attestation.lexemeId === lexemeId),
    study: studyStateOf(graph, lexemeId),
    synced: !pending.includes(pendingKey("lexemes", lexemeId))
  };
}
