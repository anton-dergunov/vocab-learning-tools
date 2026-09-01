/**
 * The Obsidian projection: a generated, read-only mirror of the vocabulary as markdown.
 *
 * A second projection alongside `yaml.ts`, and the same rule applies — this is the only place
 * markdown is written. It is export-only by design (§12): reconciling free-form markdown against a
 * structured store is the coupling this application exists to escape, so nothing reads it back.
 *
 * The shape is the convention the vault already uses, because a generated file that does not look
 * like the hand-written ones beside it is a file nobody reads:
 *
 *     ##### **el parlante** 🔊
 *     *speaker; loudspeaker*
 *     > Nos estamos conectando al **parlante** por Bluetooth. - We're connecting to the **speaker** via Bluetooth.
 *
 * Pure: no storage, no network, no DOM.
 */

import type { Lexeme, Sense, VocabularyGraph } from "./domain";
import { glossLanguagesFor, languageOf } from "./languages";
import { articleFor, lexemesIn, type Article, type ArticleSense } from "./selectors";

/** Words waiting to be filed, which the rail also keeps out of every topic. */
const INBOX_FILE = "Inbox";
/** Filed words that belong to no topic. The vault already calls this heap Misc. */
const UNFILED_FILE = "Misc";

/** Characters no filesystem agrees on. A topic is free text, so it can hold any of them. */
const ILLEGAL = /[/\\:*?"<>|#^[\]]/g;

function safeName(value: string): string {
  return value.replace(ILLEGAL, " ").replace(/\s+/g, " ").trim();
}

/**
 * `Spanish vocab - Technology.md`.
 *
 * The language is in the name rather than only in the directory, because Obsidian is searched by
 * note name: two languages with a Technology topic would otherwise be two notes called Technology,
 * and neither would be distinguishable from ordinary notes about technology.
 */
export function fileNameFor(language: string, section: string): string {
  return `${safeName(languageOf(language).name)} vocab - ${safeName(section)}.md`;
}

/** Bolds the form the example was matched on, which is what `matchedForm` is for. */
function emphasise(text: string, form: string | null): string {
  if (!form) return text;
  const at = text.indexOf(form);
  if (at < 0) return text;
  return `${text.slice(0, at)}**${form}**${text.slice(at + form.length)}`;
}

/** The sense's terms in the vocabulary's preferred gloss language, joined the way the vault does. */
function glossLine(graph: VocabularyGraph, lexeme: Lexeme, sense: Sense): string {
  const preferred = glossLanguagesFor(lexeme.language, graph.vocabularies)
    .map((lang) => sense.glosses.find((gloss) => gloss.lang === lang))
    .find(Boolean);
  const gloss = preferred ?? sense.glosses[0];
  return gloss ? gloss.terms.join("; ") : sense.definition;
}

function senseBlock(graph: VocabularyGraph, lexeme: Lexeme, entry: ArticleSense, label: string): string[] {
  const lines = [`${label}*${glossLine(graph, lexeme, entry.sense)}*`];
  entry.examples.forEach((example) => {
    const text = emphasise(example.text, example.matchedForm);
    const translation = example.translation
      ? ` - ${emphasise(example.translation, example.matchedTranslationForm)}`
      : "";
    lines.push(`> ${text}${translation}`);
  });
  return lines;
}

export function entryFor(graph: VocabularyGraph, article: Article): string {
  const { lexeme, senses } = article;
  const heading = [
    `##### **${lexeme.headword}**`,
    lexeme.reading ? `*${lexeme.reading}*` : "",
    lexeme.emoji ?? ""
  ].filter(Boolean).join(" ");

  const lines = [heading];
  // Numbered only when there is more than one sense, so the common single-sense word comes out
  // identical to what the vault holds today.
  senses.forEach((entry, index) => {
    lines.push(...senseBlock(graph, lexeme, entry, senses.length > 1 ? `${index + 1}. ` : ""));
  });
  // Notes are curated text; losing them in the readable copy would make it the lesser record.
  lexeme.notes.forEach((note) => lines.push("", note));
  return lines.join("\n");
}

/** Which file a word belongs in. Inbox first, mirroring the rail, which files nothing until it is out. */
function sectionsFor(graph: VocabularyGraph, lexeme: Lexeme): string[] {
  if (lexeme.status === "inbox") return [INBOX_FILE];
  const names = lexeme.topicIds
    .map((id) => graph.topics.find((topic) => topic.id === id && !topic.deleted))
    .filter((topic): topic is NonNullable<typeof topic> => Boolean(topic))
    .map((topic) => topic.name);
  return names.length ? names : [UNFILED_FILE];
}

export interface MarkdownFile { path: string; text: string }

/**
 * One file per language and section. A word filed under two topics appears in both — the file is a
 * view, not a home, and Obsidian is happier with a word present twice than absent once.
 */
export function markdownFor(graph: VocabularyGraph, language: string, exportedAt: string): MarkdownFile[] {
  const collator = new Intl.Collator(language);
  const sections = new Map<string, Article[]>();

  lexemesIn(graph, language).forEach((lexeme) => {
    const article = articleFor(graph, lexeme.id);
    if (!article) return;
    sectionsFor(graph, lexeme).forEach((section) => {
      const bucket = sections.get(section) ?? [];
      bucket.push(article);
      sections.set(section, bucket);
    });
  });

  return [...sections.entries()]
    .sort(([left], [right]) => collator.compare(left, right))
    .map(([section, articles]) => {
      // Alphabetical, so re-exporting after adding a word is a one-hunk diff rather than a rewrite.
      const sorted = articles
        .slice()
        .sort((left, right) => collator.compare(left.lexeme.headword, right.lexeme.headword));
      const frontMatter = [
        "---",
        `acervo-export: "${exportedAt}"`,
        `language: ${language}`,
        `section: ${JSON.stringify(section)}`,
        "---",
        ""
      ].join("\n");
      const body = sorted.map((article) => entryFor(graph, article)).join("\n\n");
      return { path: fileNameFor(language, section), text: `${frontMatter}\n${body}\n` };
    });
}
