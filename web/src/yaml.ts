/**
 * The YAML pane is a projection of the record, in the same spirit as the short form: one source,
 * two presentations. Serialisation only — nothing here parses YAML back into the graph.
 */

import { languageOf } from "./languages";
import type { Article } from "./selectors";

const PLAIN = /^[\w .,;:’'ºª/()-]+$/u;

function scalar(value: string | number | boolean | null): string {
  if (value === null || value === undefined) return "null";
  if (typeof value !== "string") return String(value);
  const reserved = /^(true|false|null|yes|no)$/i.test(value) || /^[\d.]+$/.test(value);
  return PLAIN.test(value) && !reserved && !value.includes(": ") ? value : JSON.stringify(value);
}

export function yamlFor(article: Article): string {
  const { lexeme, topics, senses, attestations, study } = article;
  const lines: string[] = [];
  lines.push(`# ${lexeme.headword} — ${languageOf(lexeme.language).name}`);
  lines.push(`id: ${lexeme.id}`);
  lines.push(`language: ${lexeme.language}`);
  lines.push(`headword: ${scalar(lexeme.headword)}`);
  lines.push(`lemma: ${scalar(lexeme.lemma)}`);
  if (lexeme.reading) lines.push(`reading: ${scalar(lexeme.reading)}`);
  if (lexeme.ipa) lines.push(`ipa: ${scalar(lexeme.ipa)}`);
  lines.push(`pos: ${lexeme.pos}`);
  if (lexeme.gender) lines.push(`gender: ${lexeme.gender}`);
  lines.push(`register: ${lexeme.register ?? "null"}`);
  if (lexeme.dialect) lines.push(`dialect: ${lexeme.dialect}`);
  lines.push(`emoji: ${scalar(lexeme.emoji)}`);
  lines.push(`status: ${lexeme.status}`);
  lines.push(`topics: [${topics.map((topic) => scalar(topic.name)).join(", ")}]`);
  lines.push(`shortGloss: ${lexeme.shortGloss ? scalar(lexeme.shortGloss) : "null            # null = derived from sense 1"}`);
  if (lexeme.notes.length) {
    lines.push("notes:");
    lexeme.notes.forEach((note) => lines.push(`  - ${scalar(note)}`));
  } else {
    lines.push("notes: []");
  }

  lines.push("senses:");
  senses.forEach(({ sense, examples, images }) => {
    lines.push(`  - order: ${sense.order}`);
    lines.push(`    definition: ${scalar(sense.definition)}`);
    lines.push(`    definitionLang: ${sense.definitionLang}`);
    if (sense.domain) lines.push(`    domain: ${sense.domain}`);
    lines.push("    glosses:");
    sense.glosses.forEach((gloss) => {
      lines.push(`      - { lang: ${gloss.lang}, terms: [${gloss.terms.map(scalar).join(", ")}] }`);
    });
    if (examples.length) {
      lines.push("    examples:");
      examples.forEach((example) => {
        lines.push(`      - text: ${scalar(example.text)}`);
        if (example.translation) lines.push(`        translation: ${scalar(example.translation)}`);
        lines.push(`        origin: ${example.origin}`);
        if (example.modelId) lines.push(`        modelId: ${example.modelId}`);
        if (example.matchedForm) lines.push(`        matchedForm: ${scalar(example.matchedForm)}`);
        if (example.videoRef) {
          lines.push(`        videoRef: ${scalar(example.videoRef)}`);
          if (example.videoTitle) lines.push(`        videoTitle: ${scalar(example.videoTitle)}`);
          if (example.videoStart !== null) lines.push(`        videoStart: ${example.videoStart}`);
        }
        lines.push(`        approved: ${example.approved}`);
      });
    } else {
      lines.push("    examples: []");
    }
    if (images.length) {
      lines.push("    imagePrompts:");
      images.forEach((image) => {
        lines.push(`      - prompt: ${scalar(image.prompt)}`);
        lines.push(`        styleId: ${image.styleId}`);
        lines.push(`        seed: ${image.seed}`);
        if (image.imageRef) lines.push(`        imageRef: ${scalar(image.imageRef)}`);
      });
    }
  });

  if (attestations.length) {
    lines.push("attestations:");
    attestations.forEach((attestation) => {
      lines.push(`  - text: ${scalar(attestation.text)}          # verbatim, never rewritten`);
      if (attestation.translation) lines.push(`    translation: ${scalar(attestation.translation)}`);
      lines.push(`    sourceKind: ${attestation.sourceKind}`);
      if (attestation.sourceTitle) lines.push(`    sourceTitle: ${scalar(attestation.sourceTitle)}`);
      if (attestation.sourceUrl) lines.push(`    sourceUrl: ${attestation.sourceUrl}`);
      lines.push(`    capturedAt: ${attestation.capturedAt}`);
    });
  }

  if (study) {
    lines.push("study:");
    lines.push(`  system: ${study.system}`);
    lines.push(`  reps: ${study.reps}`);
    lines.push(`  lapses: ${study.lapses}`);
    lines.push(`  stability: ${study.stability}`);
    lines.push(`  difficulty: ${study.difficulty}`);
    lines.push(`  retrievability: ${study.retrievability}`);
    lines.push(`  lastReview: ${study.lastReview ?? "null"}`);
  }

  return lines.join("\n");
}

export const YAML_TEMPLATE = `# New entry — fill in what you know, leave the rest.
language: es
headword: ""
lemma: ""
pos: noun            # noun verb adj adv phrase idiom expression
gender: null         # masculine feminine — Spanish nouns only
register: neutral    # neutral formal colloquial slang vulgar
emoji: ""
status: inbox
topics: []           # e.g. [Food, Travel]
shortGloss: null     # null = derived from the first gloss below
notes: []
senses:
  - order: 0
    definition: ""             # in the target language
    definitionLang: es
    glosses:
      - { lang: en, terms: [""] }
    examples:
      - text: ""
        translation: ""
        origin: manual
        approved: true
attestations: []     # the sentence you actually met it in, verbatim
`;
