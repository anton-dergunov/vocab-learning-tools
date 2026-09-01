/**
 * Export and import of a whole vocabulary as a bundle of files.
 *
 * Three needs, one mechanism: surviving a schema change without losing curation, mirroring the
 * vocabulary into Obsidian (§12), and handing a vocabulary to someone else. All three want the same
 * thing — the words as files, in a representation that outlives the database that produced them.
 *
 * A word file is exactly the document `yaml.ts` already writes, with its ids stripped. There is no
 * second format and no second parser: a bundle is read back through `parseArticle` and written
 * through `repository.saveArticle`, which is the one write path with the diffing, validation and
 * atomicity every other caller gets.
 *
 * Export is built from the replica alone, so it works with the server unreachable, like every other
 * read. Import is a sequence of ordinary writes, so it is online-only and fails loudly, like every
 * other write.
 */

import { Document, isScalar, isSeq, parse, Scalar, visit } from "yaml";
import { SCHEMA_VERSION } from "./api";
import type { Lexeme, TopicInput, VocabularyGraph, VocabularyInput } from "./domain";
import { newId } from "./ids";
import { markdownFor } from "./markdown";
import type { AcervoRepository } from "./repository";
import { articleFor, lexemesIn, languageOptions, vocabularies } from "./selectors";
import { draftFor, parseArticle, yamlForDraft, YamlProblems, type ArticleDraft } from "./yaml";

/**
 * The layout: which files exist and what they are called. Versioned separately from
 * `schemaVersion`, which versions the records inside them, so a directory rename and a field rename
 * never have to be disentangled from one number.
 */
export const BUNDLE_FORMAT = "acervo-export/1";

export const MANIFEST_FILE = "acervo.yaml";
export const VOCABULARIES_FILE = "vocabularies.yaml";
export const TOPICS_FILE = "topics.yaml";
export const MARKDOWN_DIRECTORY = "markdown";

const RESERVED = [MANIFEST_FILE, VOCABULARIES_FILE, TOPICS_FILE];

export interface BundleFile {
  path: string;
  text: string;
}

export interface ExportOptions {
  /** A language tag, or every language the replica holds. */
  language: string | "all";
  markdown: boolean;
}

/* ── filenames ──────────────────────────────────────────────────────────
   The headword is the name, because a directory of ids is a directory nobody can read. */

const CYRILLIC: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "e", ж: "zh", з: "z", и: "i", й: "y",
  к: "k", л: "l", м: "m", н: "n", о: "o", п: "p", р: "r", с: "s", т: "t", у: "u", ф: "f",
  х: "kh", ц: "ts", ч: "ch", ш: "sh", щ: "shch", ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya"
};

function latinise(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .split("")
    .map((character) => CYRILLIC[character] ?? character)
    .join("")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60)
    .replace(/-+$/, "");
}

/**
 * `la balsa` → `balsa`, `ponerse malo` → `ponerse-malo`, `суматоха` → `sumatokha`, `麻烦` → `mafan`.
 *
 * Named after the lemma rather than the headword, because the lemma is the dictionary form and the
 * headword carries the article — a directory named from headwords files half a Spanish vocabulary
 * under `el-` and `la-`. The parser already defaults the lemma to the headword, so it is always
 * there.
 *
 * A script with no Latin form falls back to the reading, which Chinese lexemes are already required
 * to carry and which is the pinyin — so the hardest case needs no dictionary and no guessing.
 */
export function slugFor(lexeme: Pick<Lexeme, "headword" | "lemma" | "reading">): string {
  return latinise(lexeme.lemma) || latinise(lexeme.headword) || latinise(lexeme.reading ?? "") || "word";
}

/** Two words that latinise the same still need two files. Deterministic, so re-exports are stable. */
function uniqueNames(lexemes: Lexeme[]): Map<string, string> {
  const taken = new Map<string, number>();
  const names = new Map<string, string>();
  lexemes.forEach((lexeme) => {
    const base = slugFor(lexeme);
    const seen = taken.get(base) ?? 0;
    taken.set(base, seen + 1);
    names.set(lexeme.id, seen === 0 ? base : `${base}-${seen + 1}`);
  });
  return names;
}

/* ── writing ────────────────────────────────────────────────────────────*/

/** An instant must survive as the string it is, never as a parsed date. */
function quoted(value: string): Scalar {
  const node = new Scalar(value);
  node.type = Scalar.QUOTE_DOUBLE;
  return node;
}

function document(value: unknown): string {
  const node = new Document(value);
  // Short lists of plain values read better on one line, the way the article documents already
  // write `topics: [Food]`. Anything holding records keeps its block form.
  visit(node, (_key, item) => {
    if (isSeq(item) && item.items.length <= 8 && item.items.every(isScalar)) item.flow = true;
  });
  return node.toString({ lineWidth: 0, singleQuote: false, flowCollectionPadding: false });
}

/**
 * Ids leave, except the ones that mean something.
 *
 * An example drawn from a sentence the owner supplied names the attestation it came from — a
 * reference between two records in the same file, which is how provenance is modelled rather than
 * flagged. That id has to survive or the lineage does not. Every other id is the database's private
 * business: dropping them is what lets a file be read as a new word, in any account, including a
 * rebuilt one, where a stated lexeme id would be refused.
 */
export function stripIds(draft: ArticleDraft): ArticleDraft {
  return {
    ...draft,
    id: null,
    senses: draft.senses.map((sense) => ({
      ...sense,
      id: null,
      examples: sense.examples.map((example) => ({ ...example, id: null })),
      images: sense.images.map((image) => ({ ...image, id: null }))
    })),
    images: draft.images.map((image) => ({ ...image, id: null }))
  };
}

function vocabularyContent(graph: VocabularyGraph, languages: string[]): VocabularyInput[] {
  return vocabularies(graph)
    .filter((entry) => languages.includes(entry.language))
    .map((entry) => ({
      language: entry.language,
      definitionLang: entry.definitionLang,
      glossLangs: entry.glossLangs,
      displayName: entry.displayName,
      flag: entry.flag,
      order: entry.order
    }));
}

/**
 * Every topic, not only the ones this language uses. Topics are global in the model, and inventing
 * a per-language topic list here would invent a relationship the records do not have — a full
 * backup would also quietly lose the empty topics the owner deliberately created.
 */
function topicContent(graph: VocabularyGraph): TopicInput[] {
  return graph.topics
    .filter((topic) => !topic.deleted)
    .slice()
    .sort((left, right) => left.order - right.order || left.name.localeCompare(right.name))
    .map((topic) => ({ name: topic.name, icon: topic.icon, order: topic.order }));
}

export function exportBundle(graph: VocabularyGraph, options: ExportOptions, exportedAt: string): BundleFile[] {
  const present = languageOptions(graph).map((option) => option.code);
  const languages = options.language === "all"
    ? present
    : present.filter((code) => code === options.language);

  const files: BundleFile[] = [];
  let lexemes = 0;

  languages.forEach((language) => {
    // Sorted before naming, so which of two colliding slugs gets the suffix never depends on the
    // order the replica happened to store them in.
    const words = lexemesIn(graph, language)
      .slice()
      .sort((left, right) => left.lemma.localeCompare(right.lemma) || left.id.localeCompare(right.id));
    const names = uniqueNames(words);
    words.forEach((lexeme) => {
      const article = articleFor(graph, lexeme.id);
      if (!article) return;
      lexemes += 1;
      files.push({
        path: `${language}/${names.get(lexeme.id)}.yaml`,
        // No study state: review history is irreplaceable but it is not vocabulary, and it is
        // backed up with the Anki collection it belongs to (§17).
        text: yamlForDraft(stripIds(draftFor(article)))
      });
    });
    if (options.markdown) {
      markdownFor(graph, language, exportedAt).forEach((file) => {
        files.push({ path: `${MARKDOWN_DIRECTORY}/${file.path}`, text: file.text });
      });
    }
  });

  const vocabularyRecords = vocabularyContent(graph, languages);
  const topicRecords = topicContent(graph);

  return [
    {
      path: MANIFEST_FILE,
      // No ownerId, no datasetId, no cursor: a bundle is not a replica, and a shared vocabulary
      // must not carry the account it came from.
      text: document({
        format: BUNDLE_FORMAT,
        schemaVersion: SCHEMA_VERSION,
        exportedAt: quoted(exportedAt),
        languages,
        counts: { vocabularies: vocabularyRecords.length, topics: topicRecords.length, lexemes }
      })
    },
    { path: VOCABULARIES_FILE, text: document(vocabularyRecords) },
    { path: TOPICS_FILE, text: document(topicRecords) },
    ...files
  ];
}

export function bundleName(language: string | "all", exportedAt: string): string {
  return `acervo-${language === "all" ? "all" : language}-${exportedAt.slice(0, 10)}.zip`;
}

/* ── reading ────────────────────────────────────────────────────────────*/

export interface BundleProblem {
  path: string;
  message: string;
}

export interface BundlePlan {
  schemaVersion: number;
  vocabularies: VocabularyInput[];
  topics: TopicInput[];
  articles: { path: string; draft: ArticleDraft }[];
  problems: BundleProblem[];
}

/**
 * The only compatibility step in Acervo, and a deliberate exception to the rule against them.
 *
 * Everywhere else the current model simply replaces the old one, because there is nothing to
 * protect. A bundle is different: it is a file that has left the application and outlived the
 * schema it was written under, which is the entire reason it exists. So an easy adaptation — a
 * renamed field, a new one with a sensible default, an enum value that maps cleanly — belongs here,
 * in one function, rewriting the text before `parseArticle` ever sees it. Anything that is not easy
 * is refused and converted outside the application, and this function must never grow into a second
 * pipeline.
 *
 * Today one schema version has ever existed, so there is nothing to adapt and nothing to invent.
 */
function upgradeBundle(files: BundleFile[], from: number): BundleFile[] {
  if (from === SCHEMA_VERSION) return files;
  throw new Error(
    `This bundle was exported from schema version ${from} and Acervo now uses version ${SCHEMA_VERSION}. `
    + "Convert its YAML files to the current shape and import it again."
  );
}

/** macOS zips a folder as a folder. Strip the wrapper so a re-zipped export still reads. */
function unwrap(files: BundleFile[]): BundleFile[] {
  const roots = new Set(files.map((file) => file.path.split("/")[0]));
  if (roots.size !== 1) return files;
  const [root] = [...roots];
  if (files.some((file) => file.path === root)) return files;
  return files.map((file) => ({ ...file, path: file.path.slice(root.length + 1) }));
}

function isWordFile(path: string): boolean {
  if (RESERVED.includes(path)) return false;
  if (path.startsWith(`${MARKDOWN_DIRECTORY}/`)) return false;
  if (!/\.ya?ml$/i.test(path)) return false;
  return path.split("/").length <= 2;
}

function readRecords<T>(
  files: BundleFile[], path: string, problems: BundleProblem[], read: (raw: Record<string, unknown>) => T
): T[] {
  const file = files.find((candidate) => candidate.path === path);
  if (!file) return [];
  let parsed: unknown;
  try { parsed = parse(file.text); }
  catch (error) {
    problems.push({ path, message: error instanceof Error ? error.message : "could not be read." });
    return [];
  }
  if (parsed === null || parsed === undefined) return [];
  if (!Array.isArray(parsed)) {
    problems.push({ path, message: "expected a list of records." });
    return [];
  }
  return parsed.flatMap((raw, index) => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      problems.push({ path, message: `entry ${index + 1} is not a block of fields.` });
      return [];
    }
    try { return [read(raw as Record<string, unknown>)]; }
    catch (error) {
      problems.push({ path, message: `entry ${index + 1} ${error instanceof Error ? error.message : "is invalid."}` });
      return [];
    }
  });
}

const text = (value: unknown): string | null =>
  typeof value === "string" && value.trim() ? value.trim() : null;

export function readBundle(input: BundleFile[]): BundlePlan {
  const problems: BundleProblem[] = [];
  const unwrapped = unwrap(input);

  const manifestFile = unwrapped.find((file) => file.path === MANIFEST_FILE);
  let schemaVersion = SCHEMA_VERSION;
  if (manifestFile) {
    const manifest = parse(manifestFile.text) as Record<string, unknown> | null;
    const format = text(manifest?.format);
    if (format && format !== BUNDLE_FORMAT) {
      throw new Error(
        `This bundle uses the ${format} layout and Acervo reads ${BUNDLE_FORMAT}. It cannot be imported as it is.`
      );
    }
    if (typeof manifest?.schemaVersion === "number") schemaVersion = manifest.schemaVersion;
  } else if (!unwrapped.some((file) => isWordFile(file.path))) {
    throw new Error(`This file does not look like an Acervo export — it has no ${MANIFEST_FILE} and no entries.`);
  }

  const files = upgradeBundle(unwrapped, schemaVersion);

  const vocabularyRecords = readRecords<VocabularyInput>(files, VOCABULARIES_FILE, problems, (raw) => {
    const language = text(raw.language);
    if (!language) throw new Error("has no language.");
    const glossLangs = Array.isArray(raw.glossLangs)
      ? raw.glossLangs.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
      : [];
    if (!glossLangs.length) throw new Error("has no gloss languages.");
    return {
      language,
      definitionLang: text(raw.definitionLang) ?? language,
      glossLangs,
      displayName: text(raw.displayName),
      flag: text(raw.flag),
      order: typeof raw.order === "number" ? raw.order : 0
    };
  });

  const topicRecords = readRecords<TopicInput>(files, TOPICS_FILE, problems, (raw) => {
    const name = text(raw.name);
    if (!name) throw new Error("has no name.");
    return { name, icon: text(raw.icon), order: typeof raw.order === "number" ? raw.order : 0 };
  });

  const articles = files
    .filter((file) => isWordFile(file.path))
    .sort((left, right) => left.path.localeCompare(right.path))
    .flatMap(({ path, text: source }) => {
      try { return [{ path, draft: parseArticle(source) }]; }
      catch (error) {
        const message = error instanceof YamlProblems
          ? error.problems.map((problem) => problem.message).join("; ")
          : error instanceof Error ? error.message : "could not be read.";
        problems.push({ path, message });
        return [];
      }
    });

  return { schemaVersion, vocabularies: vocabularyRecords, topics: topicRecords, articles, problems };
}

/* ── importing ──────────────────────────────────────────────────────────*/

export interface ImportReport {
  vocabulariesAdded: number;
  topicsAdded: number;
  added: number;
  skipped: { language: string; headword: string }[];
  failed: BundleProblem[];
  /** True when the run stopped early: the server went away, or the owner cancelled. */
  aborted: boolean;
}

export interface ImportSignal { cancelled: boolean }

const DISCONNECTED = "not connected to the server";

/**
 * Every id in a document is re-minted on the way in.
 *
 * An imported bundle must not depend on where it came from, and re-importing the same file twice
 * must not collide with what the first import created. Nulling the article id is also what makes
 * the document mean "a new word" to `saveArticle`, which is the only thing it can honestly mean in
 * a database that has never seen it.
 */
export function remintIds(draft: ArticleDraft): ArticleDraft {
  const minted = new Map<string, string>();
  draft.attestations.forEach((attestation) => {
    if (attestation.id) minted.set(attestation.id, newId());
  });
  return {
    ...stripIds(draft),
    attestations: draft.attestations.map((attestation) => ({
      ...attestation,
      id: attestation.id ? minted.get(attestation.id)! : null
    })),
    senses: draft.senses.map((sense) => ({
      ...sense,
      id: null,
      examples: sense.examples.map((example) => ({
        ...example,
        id: null,
        sourceAttestationId: example.sourceAttestationId
          ? minted.get(example.sourceAttestationId) ?? null
          : null
      })),
      images: sense.images.map((image) => ({ ...image, id: null }))
    }))
  };
}

const key = (language: string, headword: string) => `${language}\n${headword.trim().toLowerCase()}`;

/**
 * Applies a bundle, one word at a time, through the one write path.
 *
 * A word already in the vocabulary is skipped rather than merged or duplicated: an import must
 * never cost you curation you did after the export, and the report says exactly what it left alone.
 * A word that fails is reported by file and the run continues — during the phase where the schema
 * moves, knowing which three of four hundred entries were refused is the whole value.
 */
export async function importBundle(
  repository: AcervoRepository,
  plan: BundlePlan,
  onProgress: (done: number, total: number) => void = () => {},
  signal: ImportSignal = { cancelled: false }
): Promise<ImportReport> {
  const report: ImportReport = {
    vocabulariesAdded: 0, topicsAdded: 0, added: 0, skipped: [], failed: [], aborted: false
  };

  const snapshot = repository.snapshot();
  const live = <T extends { deleted: boolean }>(records: T[]) => records.filter((record) => !record.deleted);
  const languages = new Set(live(snapshot.vocabularies).map((entry) => entry.language));
  const topics = new Set(live(snapshot.topics).map((topic) => topic.name.trim().toLowerCase()));
  const words = new Set(live(snapshot.lexemes).map((lexeme) => key(lexeme.language, lexeme.headword)));

  const total = plan.vocabularies.length + plan.topics.length + plan.articles.length;
  let done = 0;
  const step = () => onProgress((done += 1), total);

  /** Only a lost server stops the run; a refused record is this record's problem, not the batch's. */
  const disconnected = (error: unknown) => error instanceof Error && error.message.includes(DISCONNECTED);
  const messageOf = (error: unknown) => error instanceof Error ? error.message : String(error);

  // Vocabularies and topics first: `saveArticle` resolves topics by name and refuses one it does
  // not hold, so a bundle would otherwise fail on every word that carries a new topic.
  for (const vocabulary of plan.vocabularies) {
    if (signal.cancelled) return { ...report, aborted: true };
    if (!languages.has(vocabulary.language)) {
      try {
        await repository.saveVocabulary(vocabulary);
        languages.add(vocabulary.language);
        report.vocabulariesAdded += 1;
      } catch (error) {
        report.failed.push({ path: VOCABULARIES_FILE, message: `${vocabulary.language}: ${messageOf(error)}` });
        if (disconnected(error)) return { ...report, aborted: true };
      }
    }
    step();
  }

  for (const topic of plan.topics) {
    if (signal.cancelled) return { ...report, aborted: true };
    if (!topics.has(topic.name.trim().toLowerCase())) {
      try {
        await repository.saveTopic(topic);
        topics.add(topic.name.trim().toLowerCase());
        report.topicsAdded += 1;
      } catch (error) {
        report.failed.push({ path: TOPICS_FILE, message: `${topic.name}: ${messageOf(error)}` });
        if (disconnected(error)) return { ...report, aborted: true };
      }
    }
    step();
  }

  for (const { path, draft } of plan.articles) {
    if (signal.cancelled) return { ...report, aborted: true };
    const identity = key(draft.language, draft.headword);
    if (words.has(identity)) {
      report.skipped.push({ language: draft.language, headword: draft.headword });
      step();
      continue;
    }
    try {
      await repository.saveArticle(remintIds(draft));
      words.add(identity);
      report.added += 1;
    } catch (error) {
      report.failed.push({ path, message: messageOf(error) });
      if (disconnected(error)) return { ...report, aborted: true };
    }
    step();
  }

  return report;
}
