/**
 * One article, two ways to read it.
 *
 * **Page** is the whole entry scrolled top to bottom, and is where the conversation lives: an edit
 * that reorders senses needs every sense in view, and a proposal's marks are drawn here. **Cards**
 * is one thing at a time, swiped left and right, for glancing at a word on a phone. Both draw from
 * the same `Article` and neither has anything the other lacks except the ask dock and the marks.
 *
 * What used to sit under a sentence as a badge — origin, model, the picture's style, where a clip
 * starts — is not on the reading surface. Nobody reads them while learning a word; your own sentence
 * keeps one quiet tag, and what else is worth keeping is in Details.
 */

import { Fragment, useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { ClipDialog } from "./ClipDialog";
import { storedClipOf, type StoredClip } from "./clips";
import type { Attestation, Example, Gloss, ImagePrompt, Lexeme, Sense } from "./domain";
import type { ArticleView } from "./editorPreferences";
import { formatDay } from "./format";
import { DictionaryEntries } from "./ExternalArticle";
import type { ExternalEntry } from "./externalEntries";
import type { Change, Mark } from "./articleEdit";
import { AskIcon, BackIcon, BookIcon, CaretIcon, FilmIcon, HederaIcon, InfoIcon, PictureIcon, PlayIcon } from "./icons";
import type { DiffPart } from "./wordDiff";
import type { Article, ArticleSense } from "./selectors";
import { CardPicture, EmptySenseImage, SenseImage, imageStateOf } from "./SenseImage";

/* Plain words rather than a grammarian's abbreviations: "noun, feminine", not "n. · f.". */
const POS_WORD: Record<string, string> = {
  noun: "noun", verb: "verb", adj: "adjective", adv: "adverb", phrase: "phrase", idiom: "idiom", expression: "expression"
};
const REGISTER_WORD: Record<string, string> = { colloquial: "informal", formal: "formal", slang: "slang", vulgar: "vulgar" };
/** Origins that came out of your own reading rather than a corpus or a model. */
const OWN_ORIGINS = new Set(["attestation", "manual"]);
const AUDIO_PENDING = "Audio is not wired up yet";

export function grammarWords(lexeme: Lexeme): string {
  const bits = [(POS_WORD[lexeme.pos] ?? lexeme.pos) + (lexeme.gender ? `, ${lexeme.gender}` : "")];
  if (lexeme.register && lexeme.register !== "neutral") bits.push(REGISTER_WORD[lexeme.register] ?? lexeme.register);
  if (lexeme.dialect) bits.push(lexeme.dialect);
  return bits.join(" · ");
}

/** Where the word is filed, as a quiet line rather than a row of chips. */
function placeLine(article: Article): string {
  const status = article.lexeme.status === "inbox" ? "Inbox" : article.lexeme.status === "learned" ? "Learned" : null;
  return [status, article.topics.map((topic) => topic.name).join(", ")].filter(Boolean).join(" — ");
}

/**
 * A video title is the loudest text a creator can write and the least useful thing on the page, so
 * it is made quiet by rule rather than by taste: hashtags and emoji out, everything lower case.
 */
export function quietTitle(title: string): string {
  return title
    .replace(/#[\p{L}\p{N}_]+/gu, " ")
    // Flags are pairs of regional indicators and keycaps are a digit plus a combining mark — neither
    // is a pictograph, which is how "🇪🇸" got through.
    .replace(/[0-9#*]\u{FE0F}?\u{20E3}/gu, "")
    .replace(/\p{Extended_Pictographic}|\p{Regional_Indicator}|\p{Emoji_Presentation}|[\u{FE0F}\u{200D}\u{20E3}\u{E0020}-\u{E007F}\u{1F3FB}-\u{1F3FF}]/gu, "")
    .replace(/\s*[|•]\s*/g, " · ")
    .replace(/\s+/g, " ")
    .replace(/^[\s·:\-–—]+|[\s·:\-–—]+$/g, "")
    .toLowerCase();
}

const isClip = (example: Example) => Boolean(example.videoRef);

/** Written examples first, clips last: a clip is the least legible way to meet a sentence. */
function orderedExamples(examples: Example[]): Example[] {
  return [...examples.filter((example) => !isClip(example)), ...examples.filter(isClip)];
}

/**
 * A sentence you supplied is shown once, in its sense. "Where you met it" keeps only the ones no
 * example was drawn from — which is also where a photo of the page will go when photo capture keeps
 * one.
 */
export function looseAttestations(article: Article): Attestation[] {
  const used = new Set(article.senses.flatMap(({ examples }) =>
    examples.map((example) => example.sourceAttestationId).filter(Boolean)));
  return article.attestations.filter((attestation) => !used.has(attestation.id));
}

export const senseName = (sense: Sense) => sense.domain ? `${sense.emoji ? `${sense.emoji} ` : ""}${sense.domain}` : "";

/** Renders the sentence with the matched surface form emphasised, without storing markup. */
function Marked({ text, form }: { text: string; form: string | null }) {
  if (!form || !text.includes(form)) return <>{text}</>;
  return <>{text.split(form).map((part, index) =>
    index === 0 ? <Fragment key={index}>{part}</Fragment>
      : <Fragment key={index}><b>{form}</b>{part}</Fragment>)}</>;
}

/** Added and changed take `--core`, removed `--warn`, and a move takes neither: nothing in it moved. */
const MARK_CLASS: Record<Mark, string> = {
  added: "mark-add", changed: "mark-change", removed: "mark-cut", moved: "mark-moved"
};
/* `−` rather than the design's `✂`: at 11px in the mono face the scissors is a smudge that reads as
   a stray bracket, and a minus pairs with the plus at a glance. The colour and the strikethrough
   are what actually carry it; the glyph is for when neither is available. */
const MARK_GLYPH: Record<Mark, string> = {
  added: "+", changed: "~", removed: "−", moved: "↕"
};
const marked = (mark: Mark | null) => (mark ? ` mark ${MARK_CLASS[mark]}` : "");

/**
 * The glyph is absolutely positioned and must be a *direct child of the marked block*, never inside
 * a paragraph — putting it in the text flow is what used to push a marked note fifteen pixels right
 * of its unmarked neighbours. No mark may change where body text sits.
 */
function MarkGlyph({ mark }: { mark: Mark | null }) {
  if (!mark) return null;
  return <span className="mark-glyph" aria-hidden="true">{MARK_GLYPH[mark]}</span>;
}

/** Tint the element that draws a field, when that field is the one that moved. */
const tint = (change: Change | null | undefined) => (change ? " field-change" : "");

/**
 * A string, with the words a proposal changed marked in place.
 *
 * `Marked` and the word diff both want to slice the same string and cannot both own the slicing, so
 * the diff wins and `Marked` runs inside each part. A `matchedForm` that straddles a part boundary
 * simply loses its bold for the length of the review — the right side to lose, since emphasis is
 * decoration and the diff is the information, and `Marked`'s own `includes` guard makes it degrade
 * to plain text rather than to wrong text.
 */
function DiffText({ text, form, words }: { text: string; form: string | null; words: DiffPart[] | null }) {
  if (!words) return <Marked text={text} form={form} />;
  return <>{words.map((part, index) => part.at === "same"
    ? <Marked key={index} text={part.text} form={form} />
    : <span key={index} className={part.at === "ins" ? "wd-ins" : "wd-del"}>
        <Marked text={part.text} form={form} />
      </span>)}</>;
}

/** A small listen button after a sentence. */
function Say({ label = "Listen", head = false, onListen }: { label?: string; head?: boolean; onListen(): void }) {
  return <button
    type="button" className={`say${head ? " always head" : ""}`} aria-label={label} onClick={onListen}
  ><PlayIcon /></button>;
}

/**
 * A sentence with its listen button glued to the last word.
 *
 * A button is a break opportunity on both sides, and one that wraps onto a line of its own reads as a
 * stray control. So the last word and the button share a no-wrap span. Not an invisible joiner
 * character: that becomes part of the sentence for everything that reads its text, a copy included.
 * Left unglued while a proposal marks the words, and when the emphasised form straddles the last
 * space, because either would have to be cut in two.
 */
function Spoken({ text, form, words = null, children }: {
  text: string; form: string | null; words?: DiffPart[] | null; children: ReactNode;
}) {
  const space = text.trimEnd().lastIndexOf(" ");
  const at = form ? text.indexOf(form) : -1;
  const straddles = form !== null && at >= 0 && at <= space && at + form.length > space;
  if (words || space < 0 || straddles) {
    return <><DiffText text={text} form={form} words={words} />{children}</>;
  }
  const lead = text.slice(0, space + 1);
  const tail = text.slice(space + 1);
  const inLead = at >= 0 && at + (form?.length ?? 0) <= space;
  return <>
    <Marked text={lead} form={inLead ? form : null} />
    <span className="say-tail"><Marked text={tail} form={inLead ? null : form} />{children}</span>
  </>;
}

function AskAnchor({ ask, target }: { ask: AskSlot | null; target: AskTarget }) {
  if (!ask) return null;
  const on = ask.focused === target.id;
  return <button
    className={`ask-anchor ${on ? "on" : ""}`}
    aria-label={on ? `Stop asking about ${target.label}` : `Ask about ${target.label}`}
    aria-pressed={on}
    onClick={() => ask.focus(on ? null : target)}
  ><AskIcon /></button>;
}

function GlossLine({ gloss }: { gloss: Gloss }) {
  return <div className="gloss-line">
    <span className="lg">{gloss.lang}</span>
    <span className="tm">{gloss.terms.map((term, index) =>
      <Fragment key={term}>{index > 0 && " · "}<b>{term}</b></Fragment>)}</span>
  </div>;
}

/** Calm, but plainly a thing to press: an outlined pill with a film icon, in ink rather than teal. */
function ClipLine({ clip, onPlay }: { clip: StoredClip; onPlay(): void }) {
  const source = [clip.videoTitle ? quietTitle(clip.videoTitle) : null, clip.videoChannel?.toLowerCase() ?? null]
    .filter(Boolean).join(" · ") || "clip";
  return <button type="button" className="clip-line" onClick={onPlay} aria-label={`Play the clip: ${source}`}>
    <span className="film"><FilmIcon /></span><span className="src">{source}</span>
  </button>;
}

function OwnTag() {
  return <span className="own-tag">your sentence</span>;
}

/* ── Page ───────────────────────────────────────────────────────────────── */

/**
 * A section of the page that folds on its own.
 *
 * Folded, it is one line — icon and name across the whole width — rather than the rail's stacked
 * three, which is what a folded Details used to cost.
 */
function FoldingSection({ folded, onToggle, rail, className = "", record, children }: {
  folded: boolean; onToggle(): void; rail: ReactNode; className?: string; record?: string; children: ReactNode;
}) {
  return <section className={`sec${folded ? " folded" : ""}${className}`} data-record={record}>
    <div className="rail-l">
      <button type="button" className="inner sec-toggle" aria-expanded={!folded} onClick={onToggle}>
        <span className="caret" aria-hidden="true"><CaretIcon /></span>{rail}
      </button>
    </div>
    {!folded && <div className="body">{children}</div>}
  </section>;
}

function ExampleBlock({ example, onListen, onPlayClip, marks = null, ask = null, label = "" }: {
  example: Example; onListen(): void; onPlayClip(example: Example): void;
  marks?: MarkSlot | null;
  ask?: AskSlot | null;
  label?: string;
}) {
  const mark = marks?.of(example.id) ?? null;
  const own = OWN_ORIGINS.has(example.origin);
  const clip = storedClipOf(example);
  /* A removed block is drawn where it was so nothing vanishes without being seen going — but its id
     is a real record id, so every control has to go with it. */
  const gone = mark === "removed";
  const moved = (field: string) => marks?.field(example.id, field) ?? null;
  return <div className={`ex${own ? " own" : ""}${clip ? " clip-ex" : ""}${marked(mark)}`} data-record={example.id}>
    <MarkGlyph mark={mark} />
    <div className="ex-text">
      <p className="t">
        <Spoken text={example.text} form={example.matchedForm} words={moved("text")?.words ?? null}>
          {!gone && <Say onListen={onListen} />}
        </Spoken>
      </p>
      {example.translation && <p className="tr">
        <DiffText
          text={example.translation} form={example.matchedTranslationForm}
          words={moved("translation")?.words ?? null}
        />
      </p>}
      {own && <OwnTag />}
      {example.note && <p className="tr ex-note">
        ✎ <DiffText text={example.note} form={null} words={moved("note")?.words ?? null} />
      </p>}
      {clip && !gone && <ClipLine clip={clip} onPlay={() => onPlayClip(example)} />}
    </div>
    {!gone && <AskAnchor ask={ask} target={{ kind: "example", id: example.id, label }} />}
  </div>;
}

function SenseSection({ entry, index, headword, pictures, clips, folded, onToggle, onListen, onPlayClip,
                       marks = null, ask = null }: {
  entry: ArticleSense; index: number; headword: string;
  pictures: PictureSlot | null;
  clips: ClipSlot | null;
  folded: boolean; onToggle(): void;
  onListen(): void;
  onPlayClip(example: Example): void;
  marks?: MarkSlot | null;
  ask?: AskSlot | null;
}) {
  const { sense, examples, images } = entry;
  const record = images[0] ?? null;
  const busy = pictures?.busy(sense.id) ?? false;
  const drawn = Boolean(record && imageStateOf(record) === "ready");
  const mark = marks?.of(sense.id) ?? null;
  const label = `sense ${index + 1}`;
  const moved = (field: string) => marks?.field(sense.id, field) ?? null;
  const wasAt = marks?.movedFrom(sense.id) ?? null;
  const name = senseName(sense);
  /* A sense is a large block — definition, glosses, examples, a picture. Tinting all of it because
     its definition was reworded would claim its untouched examples changed too, so the tint goes on
     the line that moved and the sense keeps only its rail bar to say something in here did. */
  return <FoldingSection
    folded={folded} onToggle={onToggle} className={marked(mark)} record={sense.id}
    rail={<>
      {/* The rail is not body text and has room, so the glyph sits in the flow here rather than
          being positioned out of it — which is what `.sec .num .mark-glyph` overrides it to do. */}
      <span className="num"><MarkGlyph mark={mark} />{String(index + 1).padStart(2, "0")}</span>
      <span className={`label${tint(moved("domain") ?? moved("emoji"))}`}>{name || "Sense"}</span>
      {/* Where it came from, which is the only thing you need to check a reorder was the one you
          asked for. */}
      {mark === "moved" && wasAt && <span className="label mark-was">was {String(wasAt).padStart(2, "0")}</span>}
    </>}
  >
    <div className="sense-head">
      <p className={`sense-def${tint(moved("definition"))}`}>
        <Spoken text={sense.definition} form={null} words={moved("definition")?.words ?? null}>
          {mark !== "removed" && <Say onListen={onListen} />}
        </Spoken>
      </p>
      {/* Where a picture is asked for: the page is for editing, so the control lives here and not on
          a card, and it replaces the empty frames a sense without a picture used to carry. */}
      {pictures && !drawn && !busy && mark !== "removed" && <button
        type="button" className="ask-anchor picture-anchor"
        aria-label={record && imageStateOf(record) === "failed" ? "The picture could not be drawn" : "Add a picture"}
        title={record && imageStateOf(record) === "failed" ? "The picture could not be drawn" : "Add a picture"}
        onClick={() => pictures.open(sense.id, record)}
      ><PictureIcon /></button>}
      {mark !== "removed" && <AskAnchor ask={ask} target={{ kind: "sense", id: sense.id, label }} />}
    </div>
    <div className={`glosses${tint(moved("glosses"))}`}>
      {sense.glosses.map((gloss) => <GlossLine key={gloss.lang} gloss={gloss} />)}
    </div>
    {/* The picture leads its sense: it is the thing seen first, whichever sentence it was drawn
        from. It is shown when it exists or is being drawn, and otherwise not at all — no empty
        frame; the icon in the heading is how one is asked for. */}
    {pictures && record && (drawn || busy) && <SenseImage
      prompt={record} headword={headword} busy={busy} onOpen={() => pictures.open(sense.id, record)}
    />}
    {pictures && !record && busy && <EmptySenseImage busy onOpen={() => pictures.open(sense.id, null)} />}
    {orderedExamples(examples).map((example, position) => <ExampleBlock
      key={example.id} example={example} onListen={onListen} onPlayClip={onPlayClip}
      marks={marks} ask={ask} label={`example ${position + 1} of sense ${index + 1}`}
    />)}
    {/* A search in flight says so; a search that finished empty shows **nothing at all**. The
        asymmetry with pictures is deliberate: a missing picture is a gap to fill, so it gets a
        frame, while a missing clip is the expected outcome for most words. */}
    {clips?.searching && <p className="clip-waiting">Looking for a recorded example…</p>}
  </FoldingSection>;
}

function AttestationBlock({ attestation, marks, onListen }: {
  attestation: Attestation; marks: MarkSlot | null; onListen(): void;
}) {
  const mark = marks?.of(attestation.id) ?? null;
  return <div className={`att${marked(mark)}`} data-record={attestation.id}>
    <MarkGlyph mark={mark} />
    <div className="att-text">
      <p className="t">
        <Spoken text={attestation.text} form={null} words={marks?.field(attestation.id, "text")?.words ?? null}>
          <Say onListen={onListen} />
        </Spoken>
      </p>
      {attestation.translation && <p className="tr">
        <DiffText
          text={attestation.translation} form={null}
          words={marks?.field(attestation.id, "translation")?.words ?? null}
        />
      </p>}
      <p className="src">
        {attestation.sourceTitle && (attestation.sourceUrl
          ? <a href={attestation.sourceUrl} target="_blank" rel="noreferrer">{attestation.sourceTitle}</a>
          : <span>{attestation.sourceTitle}</span>)}
        <span className="when">{formatDay(attestation.capturedAt)}</span>
      </p>
    </div>
  </div>;
}

function NotesList({ notes, marks }: { notes: string[]; marks: MarkSlot | null }) {
  return <ul className="notes">{notes.map((note, index) => {
    /* Keyed by position, not by text. Text is not an identity — two identical notes shared a
       React key, and a reworded one had no partner to diff against. */
    const change = marks?.note(index) ?? null;
    return <li key={index} className={marked(change?.mark ?? null).trim()} data-note={index}>
      <MarkGlyph mark={change?.mark ?? null} />
      <DiffText text={note} form={null} words={change?.words ?? null} />
    </li>;
  })}</ul>;
}

/** What is known about the record rather than about the word, which is why it starts folded. */
function Details({ article }: { article: Article }) {
  const { lexeme, study } = article;
  const models = [...new Set([
    ...article.senses.flatMap(({ examples, images }) => [
      ...examples.map((example) => example.modelId),
      ...images.map((image) => image.imageModelId)
    ])
  ].filter((model): model is string => Boolean(model)))];
  return <>
    <dl className="facts">
      <div><dt>id</dt><dd>{lexeme.id}</dd></div>
      <div><dt>added</dt><dd>{formatDay(lexeme.createdAt)}</dd></div>
      <div><dt>edited</dt><dd>{formatDay(lexeme.editedAt)}</dd></div>
      <div><dt>rev</dt><dd>{lexeme.revision}</dd></div>
      {models.length > 0 && <div className="wide"><dt>made with</dt><dd>{models.join(", ")}</dd></div>}
    </dl>
    {study && <div className="stats">
      <div className="stat"><div className="label">Stability</div><div className="v">{study.stability}<small> d</small></div></div>
      <div className="stat"><div className="label">Difficulty</div><div className="v">{study.difficulty}<small>/10</small></div></div>
      <div className="stat"><div className="label">Retrievability</div><div className="v">{Math.round(study.retrievability * 100)}<small>%</small></div></div>
      <div className="stat"><div className="label">Reps · lapses</div><div className="v">{study.reps}<small> · {study.lapses}</small></div></div>
      <div className="stat"><div className="label">Last review</div><div className="v" style={{ fontSize: 14 }}>{formatDay(study.lastReview)}</div></div>
    </div>}
  </>;
}

/* ── Cards ──────────────────────────────────────────────────────────────── */

/** An ivy leaf, pointing away from the sentence it marks: ☙ above it, ❧ below it. */
function Hedera({ side }: { side: "above" | "below" }) {
  return <span className={`card-ornament ${side}`} aria-hidden="true"><HederaIcon /></span>;
}

interface Card {
  group: string;
  chip: string;
  aside: boolean;
  body: ReactNode;
}

/**
 * One sense at a time, and inside a sense one sentence at a time.
 *
 * The definition and its gloss stay at the top of every card of their sense, because a sentence is
 * only worth reading against the meaning it illustrates. A picture goes on the card of the sentence
 * it was drawn from — a clip's included — and one drawn from the sense alone opens the sense. The
 * picture is the part that gives way when a card is short of room; a card whose words alone do not
 * fit scrolls on its own, as the exception, and nothing forbids it.
 */
function ArticleCards({ article, pictures, onListen, onPlayClip, onReference }: {
  article: Article; pictures: PictureSlot | null;
  onListen(): void; onPlayClip(example: Example): void;
  onReference?(entry: ExternalEntry | null): void;
}) {
  const { lexeme } = article;
  const track = useRef<HTMLDivElement | null>(null);
  const nav = useRef<HTMLElement | null>(null);
  const [at, setAt] = useState(0);

  const cards: Card[] = [];
  article.senses.forEach(({ sense, examples, images }, index) => {
    const items = orderedExamples(examples);
    const record = images[0] ?? null;
    const busy = pictures?.busy(sense.id) ?? false;
    const drawn = Boolean(record && imageStateOf(record) === "ready");
    /* A picture goes on the card of the sentence it was drawn from — a clip's included — whatever
       state it is in, so a picture being drawn appears where the finished one will. */
    const anchored = record?.exampleId && items.some((example) => example.id === record.exampleId)
      ? record.exampleId : null;
    const count = Math.max(items.length, 1);
    const name = senseName(sense);
    for (let position = 0; position < count; position += 1) {
      const example = items[position] ?? null;
      const spot = anchored ? example?.id === anchored : position === 0;
      /* A card is for reading, so it shows a picture that exists, the page's frame while one is
         being drawn right now, and otherwise nothing: no placeholder and no control. Pictures are
         asked for and changed on the page. */
      const visual = !spot ? null
        : drawn && record
          ? <CardPicture prompt={record} headword={lexeme.headword} busy={busy} />
        : busy
          ? <div className="card-frame">{record
              ? <SenseImage prompt={record} headword={lexeme.headword} busy onOpen={() => undefined} />
              : <EmptySenseImage busy onOpen={() => undefined} />}</div>
        : null;
      /* A card that is only words is set as an epigraph between two ivy leaves, so the space reads
         as a margin; a card with no sentence either keeps the pair of leaves alone. */
      const quoted = !visual && Boolean(example);
      const bare = !visual && !example;
      const clip = example ? storedClipOf(example) : null;
      cards.push({
        group: `sense:${sense.id}`,
        chip: name || String(index + 1),
        aside: false,
        body: <>
          <div className="card-sense">
            <p className="card-def"><Spoken text={sense.definition} form={null}><Say onListen={onListen} /></Spoken></p>
            {sense.glosses.map((gloss) => <p key={gloss.lang} className="card-gloss">
              <span className="lg">{gloss.lang}</span>{gloss.terms.join(" · ")}
            </p>)}
          </div>
          <div className={`card-main${quoted ? " quoted" : ""}${bare ? " bare" : ""}`}>
            {visual}
            {quoted && <Hedera side="above" />}
            {example && <div className={`card-ex${OWN_ORIGINS.has(example.origin) ? " own" : ""}${clip ? " clip-ex" : ""}`}>
              <p className="t">
                {quoted && <span className="quote-mark" aria-hidden="true">“</span>}
                <Spoken text={example.text} form={example.matchedForm}>
                  {quoted && <span className="quote-mark" aria-hidden="true">”</span>}
                  <Say onListen={onListen} />
                </Spoken>
              </p>
              {example.translation && <p className="tr">
                <Marked text={example.translation} form={example.matchedTranslationForm} />
              </p>}
              {OWN_ORIGINS.has(example.origin) && <OwnTag />}
              {clip && <ClipLine clip={clip} onPlay={() => onPlayClip(example)} />}
            </div>}
            {quoted && <Hedera side="below" />}
            {bare && <span className="card-ornament pair" aria-hidden="true"><HederaIcon /><HederaIcon /></span>}
          </div>
          {count > 1 && <span className="card-pos">{position + 1} / {count}</span>}
        </>
      });
    }
  });
  if (lexeme.notes.length) cards.push({
    group: "notes", chip: "✎ Notes", aside: true,
    body: <><h2 className="card-title">Notes</h2><div className="card-main top"><NotesList notes={lexeme.notes} marks={null} /></div></>
  });
  const met = looseAttestations(article);
  if (met.length) cards.push({
    group: "met", chip: "✳ Met it", aside: true,
    body: <><h2 className="card-title">Where you met it</h2><div className="card-main top">
      {met.map((attestation) => <AttestationBlock key={attestation.id} attestation={attestation} marks={null} onListen={onListen} />)}
    </div></>
  });
  const dictionaryAt = cards.length;
  cards.push({
    group: "dict", chip: "Dictionaries", aside: true,
    body: <><h2 className="card-title">Other dictionaries</h2><div className="card-main top">
      {/* Mounted only once the card is reached: reaching it is the gesture that asks. */}
      {at === dictionaryAt && <DictionaryEntries
        headword={lexeme.headword} lemma={lexeme.lemma} language={lexeme.language} onLoaded={onReference} />}
    </div></>
  });
  cards.push({
    group: "details", chip: "Details", aside: true,
    body: <><h2 className="card-title">Details</h2><div className="card-main top"><Details article={article} /></div></>
  });

  const groups = cards
    .map((card, index) => ({ ...card, first: index }))
    .filter((card, index, all) => all.findIndex((other) => other.group === card.group) === index);
  const current = cards[Math.min(at, cards.length - 1)]?.group;

  /* Beside the column only where the margin really has room for them, measured against `.main`,
     which clips: a window-width rule put them where the space it assumed was not always there. */
  const root = useRef<HTMLDivElement | null>(null);
  const [beside, setBeside] = useState(false);
  useEffect(() => {
    const element = root.current;
    const clipper = element?.closest(".main");
    if (!element || !clipper || typeof ResizeObserver === "undefined") return;
    const measure = () => {
      const inner = element.getBoundingClientRect();
      const outer = clipper.getBoundingClientRect();
      setBeside(inner.left - outer.left >= 100 && outer.right - inner.right >= 100);
    };
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    observer.observe(clipper);
    measure();
    return () => observer.disconnect();
  }, []);

  const go = useCallback((index: number) => {
    const element = track.current;
    if (!element) return;
    const to = Math.max(0, Math.min(index, element.children.length - 1));
    element.scrollTo({ left: to * element.clientWidth, behavior: "smooth" });
  }, []);

  // A different word starts at its first card.
  useLayoutEffect(() => {
    setAt(0);
    if (track.current) track.current.scrollLeft = 0;
  }, [lexeme.id]);

  useEffect(() => {
    const chip = nav.current?.querySelector<HTMLElement>(".cards-chip.on");
    if (!chip || !nav.current || typeof nav.current.scrollTo !== "function") return;
    nav.current.scrollTo({ left: chip.offsetLeft - (nav.current.clientWidth - chip.offsetWidth) / 2, behavior: "smooth" });
  }, [current]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      if (isTyping(event.target)) return;
      event.preventDefault();
      go(at + (event.key === "ArrowRight" ? 1 : -1));
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [at, go]);

  return <div className={`cards${beside ? " edges-beside" : ""}`} ref={root}>
    <header className="cards-head">
      <div className="cards-word">
        <span className="cw-emoji" aria-hidden="true">{lexeme.emoji || "📄"}</span>
        {/* The word and its button share one inline line, where `vertical-align: middle` centres the
            button on the word's lowercase letters rather than on the line box. */}
        <div className="cw-line" data-length={lexeme.headword.length > 24 ? "long" : lexeme.headword.length > 14 ? "mid" : "short"}>
          <h1 className="cw-headword">{lexeme.headword}</h1>
          <Say head label={`Listen to ${lexeme.headword}`} onListen={onListen} />
        </div>
        {/* No transcription on a card: the play button is how a word is heard, and the line it took
            is room the card needs more. A reading (pinyin) is part of the word, so it stays. */}
        {lexeme.reading && <span className="reading">{lexeme.reading}</span>}
      </div>
      <nav className="cards-nav" aria-label="Senses and sections" ref={nav}>
        {groups.map((group, index) => <Fragment key={group.group}>
          {/* A rule between the meanings and everything about the word as a whole. */}
          {group.aside && !groups[index - 1]?.aside && index > 0 && <span className="cards-sep" aria-hidden="true" />}
          <button
            type="button"
            className={`cards-chip${group.group === current ? " on" : ""}${group.aside ? " aside" : ""}`}
            aria-current={group.group === current}
            onClick={() => go(group.first)}
          >{group.chip}</button>
        </Fragment>)}
      </nav>
    </header>
    <div className="cards-stage">
      <div
        className="cards-track" ref={track}
        onScroll={(event) => {
          const element = event.currentTarget;
          setAt(Math.round(element.scrollLeft / Math.max(element.clientWidth, 1)));
        }}
      >
        {cards.map((card, index) => <article
          key={`${card.group}:${index}`} className="card" aria-label={`Card ${index + 1} of ${cards.length}`}
          data-card={index}
        >{card.body}</article>)}
      </div>
    </div>
    {/* Beside the column when there is margin for them, else a pair at the foot of the card. */}
    <div className="cards-edges">
      <button type="button" className="cards-edge prev" aria-label="Previous card" disabled={at === 0} onClick={() => go(at - 1)}><BackIcon /></button>
      <button type="button" className="cards-edge next" aria-label="Next card" disabled={at >= cards.length - 1} onClick={() => go(at + 1)}><BackIcon /></button>
    </div>
  </div>;
}

/* ── reading helpers shared by both views ───────────────────────────────── */

function isTyping(target: EventTarget | null): boolean {
  return target instanceof Element && Boolean(target.closest("input, textarea, select, [contenteditable], .cm-editor"));
}

/**
 * Select all selects the word, not the application around it.
 *
 * Copying an article somewhere else is worth keeping; the top bar, the Add button and the dock are
 * not part of it. In Cards it is the card on screen.
 */
function useSelectAll(root: React.RefObject<HTMLElement | null>, view: ArticleView) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "a") return;
      if (isTyping(event.target) || !root.current) return;
      const target = view === "cards"
        ? cardOnScreen(root.current) ?? root.current
        : root.current;
      event.preventDefault();
      const range = document.createRange();
      range.selectNodeContents(target);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [root, view]);
}

function cardOnScreen(root: HTMLElement): HTMLElement | null {
  const track = root.querySelector<HTMLElement>(".cards-track");
  if (!track) return null;
  const index = Math.round(track.scrollLeft / Math.max(track.clientWidth, 1));
  return track.children[index] as HTMLElement | undefined ?? null;
}

/**
 * Listen to whatever is selected, in the language the article is in.
 *
 * A floating button above the selection, because a play button on every phrase would be noise and a
 * selection is already the gesture for "this bit".
 */
function SelectionListen({ root, onListen }: { root: React.RefObject<HTMLElement | null>; onListen(): void }) {
  const [at, setAt] = useState<{ left: number; top: number } | null>(null);
  useEffect(() => {
    const onChange = () => {
      const selection = window.getSelection();
      const text = selection && !selection.isCollapsed ? selection.toString().trim() : "";
      if (!text || !root.current || !selection?.anchorNode || !root.current.contains(selection.anchorNode)
          || selection.rangeCount === 0) {
        setAt(null);
        return;
      }
      const box = selection.getRangeAt(0).getBoundingClientRect?.();
      if (!box) { setAt(null); return; }
      setAt({
        left: Math.min(Math.max(box.left + box.width / 2, 60), window.innerWidth - 60),
        top: Math.max(box.top, 70)
      });
    };
    document.addEventListener("selectionchange", onChange);
    return () => document.removeEventListener("selectionchange", onChange);
  }, [root]);
  if (!at) return null;
  return <button
    type="button" className="sel-say" style={{ left: at.left, top: at.top }}
    // Pressing it must not collapse the selection it is about to read.
    onMouseDown={(event) => event.preventDefault()}
    onClick={onListen}
  ><PlayIcon /><span>Listen</span></button>;
}

/* ── slots the caller supplies ──────────────────────────────────────────── */

/**
 * Whether a clip search is in flight, and how a clip is taken off the page.
 *
 * Absent for an unsaved proposal, like `PictureSlot` and for the same reason: the placeholder ids
 * `articleFromDraft` mints are deliberately not valid record ids, so there is nothing to act on.
 */
export interface ClipSlot {
  /** One search covers every sense of the word, so this is per word rather than per sense. */
  searching: boolean;
  remove(exampleId: string): void;
}

/**
 * A live proposal's change marks. Absent for a stored article with nothing proposed against it.
 *
 * Caller-supplied like `PictureSlot` and `ClipSlot`, and for the same reason: this component knows
 * how to draw an article and nothing about where a proposal came from. It never sees an operation —
 * the marks are a comparison of two drafts by record id, which is what lets the wire format change
 * without touching anything here.
 */
export interface MarkSlot {
  /** The record's own mark, which decides the block treatment. Null when nothing happened to it. */
  of(id: string): Mark | null;
  /**
   * Did one field of one record move, and which words moved inside it.
   *
   * Null when the record is unmarked, so a lookup against an unrelated record cannot hit. Split from
   * `of` because a single method cannot return both a block treatment and a field's word diff, and
   * because the old overload consulted a separate lexeme-only table and ignored the record entirely.
   */
  field(id: string, field: string): Change | null;
  /** Notes are a positional list with no ids of their own. Index into the notes as drawn. */
  note(index: number): Change | null;
  /** Where a `moved` record used to be, counting from one. Null for anything that did not move. */
  movedFrom(id: string): number | null;
}

/** Which block the next turn is about. */
export interface AskTarget {
  kind: "sense" | "example";
  id: string;
  /** What the dock's chip says: "sense 1", "example 2". */
  label: string;
}

/**
 * Bounding a question to one block, which removes the need to type "the second example".
 *
 * Absent whenever there is nothing an id could safely name: the Add view's preview, and a live
 * proposal, whose added records carry `articleFromDraft`'s placeholder ids rather than real ones.
 */
export interface AskSlot {
  focus(target: AskTarget | null): void;
  /** The focused record's id, so its anchor renders active. */
  focused: string | null;
}

export interface PictureSlot {
  /**
   * `senseId` is always the sense that was clicked, and `prompt` is null for one that has no row
   * yet. Both are needed: a sense with no row still belongs to a word whose brief can be written,
   * and the dialog has to know *which* sense's brief to show when it comes back.
   */
  open(senseId: string, prompt: ImagePrompt | null): void;
  busy(senseId: string): boolean;
}

/**
 * `meta` off drops Details and Other dictionaries, which is what an unsaved proposal wants: id,
 * added, edited and rev are facts about a stored record, and checking a dictionary is a thing you do
 * to an entry you have. Everything above them is identical, because a proposal and the entry it
 * becomes are the same thing.
 */
export default function LexemeArticle({ article, onUnsupported, meta = true, view = "page", pictures = null,
                                       clips = null, marks = null, ask = null,
                                       onReference }: {
  article: Article; onUnsupported(message: string): void; meta?: boolean;
  /** Cards never carries marks or the ask anchors: a proposal is reviewed on the page. */
  view?: ArticleView;
  pictures?: PictureSlot | null;
  clips?: ClipSlot | null;
  marks?: MarkSlot | null;
  ask?: AskSlot | null;
  /** What the dictionary section has loaded, so a question can be asked against what is on screen. */
  onReference?(entry: ExternalEntry | null): void;
}) {
  const { lexeme, senses } = article;
  const root = useRef<HTMLDivElement | null>(null);
  /* The dialog lives here rather than being handed down from `App`, unlike the picture slot: a
     picture is drawn through a queue somebody else owns, while a clip is only fetched and played.
     That also gives the Add view's preview a working clip button for nothing. */
  const [playing, setPlaying] = useState<Example | null>(null);
  const playingClip = playing ? storedClipOf(playing) : null;
  /* Every section folds on its own, remembered per word for as long as the article is open. */
  const [folds, setFolds] = useState<Record<string, boolean>>({});
  const listen = useCallback(() => onUnsupported(AUDIO_PENDING), [onUnsupported]);
  useSelectAll(root, view);

  const key = (part: string) => `${lexeme.id}:${part}`;
  const isFolded = (part: string, byDefault: boolean) => folds[key(part)] ?? byDefault;
  const toggle = (part: string, byDefault: boolean) =>
    setFolds((current) => ({ ...current, [key(part)]: !(current[key(part)] ?? byDefault) }));

  const head = (field: string) => marks?.field(lexeme.id, field) ?? null;
  const place = placeLine(article);
  const met = looseAttestations(article);
  const dialog = playing && playingClip && <ClipDialog
    stored={playingClip}
    headword={lexeme.headword}
    glossLang={article.glossLangs[0] ?? null}
    onClose={() => setPlaying(null)}
    /* Removing a clip belongs to the clip, where you have just watched it — not under every one on
       the page. Only a stored subtitle example can be removed; a proposal's has no real id. */
    onRemove={clips && playing.origin === "subtitle"
      ? () => { clips.remove(playing.id); setPlaying(null); }
      : undefined}
  />;

  if (view === "cards") {
    return <div className="article-root cards-root" ref={root}>
      <ArticleCards article={article} pictures={pictures} onListen={listen} onPlayClip={setPlaying} onReference={onReference} />
      <SelectionListen root={root} onListen={listen} />
      {dialog}
    </div>;
  }

  return <div className="article-root" ref={root}>
    <div className="masthead" data-record={lexeme.id}>
      <div className="head-row">
        <div className={`emoji-plate${tint(head("emoji"))}`}>{lexeme.emoji || "📄"}</div>
        <div className="head-text">
          {/* Two lines beside the plate: the word with its play button, then how it sounds and what
              it is. Where it is filed trails that second line in small mono — it says something
              about the word, so it stays in view, but it should not cost a line of its own. */}
          {/* Inline rather than flex: `vertical-align: middle` centres the button on the word's
              lowercase letters, which is where the eye reads the word, at every size it wraps to. */}
          <div className="head-line">
            <h1 className={`headword${tint(head("headword"))}`}>
              <DiffText text={lexeme.headword} form={null} words={head("headword")?.words ?? null} />
            </h1>
            <Say head label={`Listen to ${lexeme.headword}`} onListen={listen} />
          </div>
          {lexeme.reading && <div className={`reading${tint(head("reading"))}`}>{lexeme.reading}</div>}
          <div className="pron-row">
            {lexeme.ipa && <span className={`ipa${tint(head("ipa"))}`}>{lexeme.ipa}</span>}
            <span className={`gram${tint(head("pos") ?? head("gender") ?? head("register") ?? head("dialect"))}`}>
              {grammarWords(lexeme)}
            </span>
            {place && <span className={`place${tint(head("topics") ?? head("status"))}`}>{place}</span>}
          </div>
        </div>
      </div>
    </div>

    {senses.map((entry, index) =>
      <SenseSection
        key={entry.sense.id}
        entry={entry}
        index={index}
        headword={lexeme.headword}
        pictures={pictures}
        clips={clips}
        marks={marks}
        ask={ask}
        folded={isFolded(`sense:${entry.sense.id}`, false)}
        onToggle={() => toggle(`sense:${entry.sense.id}`, false)}
        onListen={listen}
        onPlayClip={setPlaying}
      />)}

    {/* Notes, then where you met it, then the two things you open on purpose. */}
    {lexeme.notes.length > 0 && <FoldingSection
      folded={isFolded("notes", false)} onToggle={() => toggle("notes", false)}
      rail={<><span className="num">✎</span><span className="label">Notes</span></>}
    ><NotesList notes={lexeme.notes} marks={marks} /></FoldingSection>}

    {met.length > 0 && <FoldingSection
      folded={isFolded("met", false)} onToggle={() => toggle("met", false)}
      rail={<><span className="num">✳</span><span className="label">Where you met it</span></>}
    >
      {met.map((attestation) =>
        <AttestationBlock key={attestation.id} attestation={attestation} marks={marks} onListen={listen} />)}
    </FoldingSection>}

    {meta && <FoldingSection
      folded={isFolded("dict", true)} onToggle={() => toggle("dict", true)}
      rail={<><span className="num"><BookIcon /></span><span className="label">Other dictionaries</span></>}
    >
      {/* Mounted only when unfolded, and mounting is what looks the word up. */}
      <DictionaryEntries
        headword={lexeme.headword} lemma={lexeme.lemma} language={lexeme.language} onLoaded={onReference} />
    </FoldingSection>}

    {meta && <FoldingSection
      folded={isFolded("details", true)} onToggle={() => toggle("details", true)}
      rail={<><span className="num"><InfoIcon /></span><span className="label">Details</span></>}
    ><Details article={article} /></FoldingSection>}

    <SelectionListen root={root} onListen={listen} />
    {dialog}
  </div>;
}
