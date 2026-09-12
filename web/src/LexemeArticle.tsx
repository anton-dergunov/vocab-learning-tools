import { Fragment, useState } from "react";
import { ClipDialog } from "./ClipDialog";
import { storedClipOf, type StoredClip } from "./clips";
import type { Example, Gloss, ImagePrompt } from "./domain";
import { formatClock, formatDay } from "./format";
import { DictionaryFold } from "./ExternalArticle";
import type { ExternalEntry } from "./externalEntries";
import type { Change, Mark } from "./articleEdit";
import { AskIcon, PlayIcon } from "./icons";
import type { DiffPart } from "./wordDiff";
import type { Article, ArticleSense } from "./selectors";
import { EmptySenseImage, SenseImage } from "./SenseImage";

const POS_LABEL: Record<string, string> = {
  noun: "n.", verb: "v.", adj: "adj.", adv: "adv.", phrase: "phr.", idiom: "idiom", expression: "expr."
};
const GENDER_LABEL: Record<string, string> = { feminine: "f.", masculine: "m.", common: "c.", neuter: "n." };
/** Origins that came out of your own reading rather than a corpus or a model. */
const OWN_ORIGINS = new Set(["attestation", "manual"]);

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
  added: "+", changed: "~", removed: "\u2212", moved: "\u2195"
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

function GrammarLine({ article }: { article: Article }) {
  const { lexeme } = article;
  const bits = [POS_LABEL[lexeme.pos] ?? lexeme.pos];
  if (lexeme.gender) bits.push(GENDER_LABEL[lexeme.gender] ?? lexeme.gender);
  bits.push(lexeme.language);
  if (lexeme.register && lexeme.register !== "neutral") bits.push(lexeme.register);
  if (lexeme.dialect) bits.push(lexeme.dialect);
  return <p className="gram">{bits.map((bit, index) =>
    <Fragment key={bit}>{index > 0 && <span className="sep">·</span>}<span>{bit}</span></Fragment>)}</p>;
}

function GlossLine({ gloss }: { gloss: Gloss }) {
  return <div className="gloss-line">
    <span className="lg">{gloss.lang}</span>
    <span className="tm">{gloss.terms.map((term, index) =>
      <Fragment key={term}>{index > 0 && " · "}<b>{term}</b></Fragment>)}</span>
  </div>;
}

function ExampleBlock({ example, onUnsupported, onPlayClip, clips, marks = null, ask = null,
                       label = "" }: {
  example: Example; onUnsupported(message: string): void; onPlayClip(clip: StoredClip): void;
  clips: ClipSlot | null;
  marks?: MarkSlot | null;
  ask?: AskSlot | null;
  label?: string;
}) {
  const mark = marks?.of(example.id) ?? null;
  const own = OWN_ORIGINS.has(example.origin);
  const clip = storedClipOf(example);
  /* A removed block is drawn where it was so nothing vanishes without being seen going — but its id
     is a real record id, so every control has to go with it. "Remove this clip" on a ghost would
     act on a record the proposal is already deleting. */
  const gone = mark === "removed";
  const moved = (field: string) => marks?.field(example.id, field) ?? null;
  return <div className={`ex ${own ? "own" : ""}${marked(mark)}`} data-record={example.id}>
    <MarkGlyph mark={mark} />
    <p className="t">
      <DiffText text={example.text} form={example.matchedForm} words={moved("text")?.words ?? null} />
    </p>
    {example.translation &&
      <p className="tr">
        <DiffText
          text={example.translation} form={example.matchedTranslationForm}
          words={moved("translation")?.words ?? null}
        />
      </p>}
    <div className="foot">
      <span className={`prov ${own ? "own" : ""}`}>{example.origin}</span>
      {example.modelId && <span className="label">{example.modelId}</span>}
      {!example.approved && <span className="prov warnk">unapproved</span>}
      {!gone && example.audioRef && <button className="play mini" onClick={() => onUnsupported("Audio is not wired up yet")}>
        <PlayIcon />Play
      </button>}
      <span className="spacer" />
      {!gone && <AskAnchor ask={ask} target={{ kind: "example", id: example.id, label }} />}
    </div>
    {example.note && <p className="tr ex-note">
      ✎ <DiffText text={example.note} form={null} words={moved("note")?.words ?? null} />
    </p>}
    {clip && !gone && <button className="clip" style={{ marginTop: 10 }} onClick={() => onPlayClip(clip)}>
      <span className="pl"><PlayIcon /></span>
      <span className="ti">{clip.videoTitle ?? "Clip"}
        <span>
          {clip.videoChannel ? `${clip.videoChannel} · ` : "clip · "}
          starts at {formatClock(clip.videoStart)}
        </span></span>
    </button>}
    {/* Removal is an ordinary tombstone, deliberately not a picture's `suppressed` field — and it
        is safe only because the clip search is one-shot at save. The id is derived from the sense
        and the segment, so a later re-search that chose the same segment would write at the
        tombstone's id and bring it back; nothing re-searches, so nothing can. A rescan has to add
        a suppression field before it ships, exactly as the image pipeline had to. */}
    {clip && !gone && example.origin === "subtitle" && clips && <button
      className="link-btn clip-remove"
      onClick={() => clips.remove(example.id)}
    >Remove this clip</button>}
  </div>;
}

/**
 * Where a picture goes: under the sentence it was drawn from, or under the sense when it names none.
 *
 * The record says which — `exampleId` is the anchor the brief writer chose — so the picture sits
 * beside the thing it illustrates rather than in a fold at the bottom of the sense. A sense with no
 * prompt row at all still shows a frame, so the article has one shape whether or not a word has been
 * through the pipeline.
 */
function SenseSection({ entry, index, headword, pictures, clips, onUnsupported, onPlayClip,
                       marks = null, ask = null }: {
  entry: ArticleSense; index: number; headword: string;
  pictures: PictureSlot | null;
  clips: ClipSlot | null;
  onUnsupported(message: string): void;
  onPlayClip(clip: StoredClip): void;
  marks?: MarkSlot | null;
  ask?: AskSlot | null;
}) {
  const { sense, examples, images } = entry;
  const anchored = new Map(images.filter((image) => image.exampleId).map((image) => [image.exampleId!, image]));
  const loose = images.filter((image) => !image.exampleId);

  const frame = (image: ImagePrompt) => pictures && <SenseImage
    prompt={image}
    headword={headword}
    busy={pictures.busy(sense.id)}
    onOpen={() => pictures.open(sense.id, image)}
  />;

  const mark = marks?.of(sense.id) ?? null;
  const label = `sense ${index + 1}`;
  const moved = (field: string) => marks?.field(sense.id, field) ?? null;
  const wasAt = marks?.movedFrom(sense.id) ?? null;
  /* A sense is a large block — definition, glosses, examples, a picture. Tinting all of it because
     its definition was reworded would claim its untouched examples changed too, so the tint goes on
     the line that moved and the sense keeps only its rail bar to say something in here did. */
  return <section className={`sec${marked(mark)}`} data-record={sense.id}>
    <div className="rail-l">
      <div className="inner">
        {/* The rail is not body text and has room, so the glyph sits in the flow here rather than
            being positioned out of it — which is what `.sec .num .mark-glyph` overrides it to do. */}
        <span className="num"><MarkGlyph mark={mark} />{String(index + 1).padStart(2, "0")}</span>
        <span className={`label${tint(moved("domain"))}`}>
          Sense{sense.domain && <><br />{sense.domain}</>}
        </span>
        {/* Where it came from, which is the only thing you need to check a reorder was the one you
            asked for. */}
        {mark === "moved" && wasAt && <span className="label mark-was">was {String(wasAt).padStart(2, "0")}</span>}
      </div>
    </div>
    <div className="body">
      <div className="sense-head">
        <p className={`sense-def${tint(moved("definition"))}`}>
          <DiffText text={sense.definition} form={null} words={moved("definition")?.words ?? null} />
        </p>
        {mark !== "removed" && <AskAnchor ask={ask} target={{ kind: "sense", id: sense.id, label }} />}
      </div>
      <div className={`glosses${tint(moved("glosses"))}`}>
        {sense.glosses.map((gloss) => <GlossLine key={gloss.lang} gloss={gloss} />)}
      </div>
      {examples.map((example, position) => <Fragment key={example.id}>
        <ExampleBlock example={example} onUnsupported={onUnsupported} onPlayClip={onPlayClip}
          clips={clips} marks={marks} ask={ask}
          label={`example ${position + 1} of sense ${index + 1}`} />
        {anchored.has(example.id) && frame(anchored.get(example.id)!)}
      </Fragment>)}
      {loose.map((image) => <Fragment key={image.id}>{frame(image)}</Fragment>)}
      {images.length === 0 && pictures && <EmptySenseImage
        busy={pictures.busy(sense.id)}
        onOpen={() => pictures.open(sense.id, null)}
      />}
      {/* A search in flight says so; a search that finished empty shows **nothing at all**. The
          asymmetry with pictures is deliberate: a missing picture is a gap to fill, so it gets a
          frame, while a missing clip is the expected outcome for most words and a permanent empty
          frame on every sense of every word would be noise. */}
      {clips?.searching && <p className="clip-waiting">Looking for a recorded example…</p>}
    </div>
  </section>;
}

/**
 * `meta` off drops the storage footer, which is what an unsaved proposal wants: id, added, edited
 * and rev are facts about a stored record, and a generated entry under review has none of them yet.
 * Everything above it is identical, because a proposal and the entry it becomes are the same thing.
 */
/**
 * How a picture is reached and whether one is being drawn — both of which only the caller knows.
 *
 * Absent for an unsaved proposal: `articleFromDraft`'s placeholder ids are deliberately not valid
 * record ids, so there is nothing a control could act on. The frames disappear rather than
 * offering buttons that cannot work.
 */
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

export default function LexemeArticle({ article, onUnsupported, meta = true, pictures = null,
                                       clips = null, marks = null, ask = null,
                                       onReference }: {
  article: Article; onUnsupported(message: string): void; meta?: boolean;
  pictures?: PictureSlot | null;
  clips?: ClipSlot | null;
  marks?: MarkSlot | null;
  ask?: AskSlot | null;
  /** What the dictionary fold has loaded, so a question can be asked against what is on screen. */
  onReference?(entry: ExternalEntry | null): void;
}) {
  const { lexeme, topics, senses, attestations, study } = article;
  /* The dialog lives here rather than being handed down from `App`, unlike the picture slot: a
     picture is drawn through a queue somebody else owns, while a clip is only fetched and played.
     That also gives the Add view's preview a working clip button for nothing. */
  const [playing, setPlaying] = useState<StoredClip | null>(null);
  const head = (field: string) => marks?.field(lexeme.id, field) ?? null;
  return <>
    <div className="masthead" data-record={lexeme.id}>
      <div className="head-row">
        <div className={`emoji-plate${tint(head("emoji"))}`}>{lexeme.emoji || "📄"}</div>
        <div className="head-text">
          <h1 className={`headword${tint(head("headword"))}`}>
            <DiffText text={lexeme.headword} form={null} words={head("headword")?.words ?? null} />
          </h1>
          {lexeme.reading && <div className={`reading${tint(head("reading"))}`}>{lexeme.reading}</div>}
          <div className="pron-row">
            {lexeme.ipa && <span className={`ipa${tint(head("ipa"))}`}>{lexeme.ipa}</span>}
            <button className="play" onClick={() => onUnsupported("Audio is not wired up yet")}><PlayIcon />Listen</button>
          </div>
          <div className={tint(head("pos") ?? head("gender") ?? head("register") ?? head("dialect"))}>
            <GrammarLine article={article} />
          </div>
        </div>
      </div>
      <div className={`chips${tint(head("topics") ?? head("status"))}`}>
        <span className={`chip status ${lexeme.status === "inbox" ? "inbox" : ""}`}>{lexeme.status}</span>
        {topics.map((topic) => <span key={topic.id} className="chip">{topic.icon ?? "📌"} {topic.name}</span>)}
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
        onUnsupported={onUnsupported}
        onPlayClip={setPlaying}
      />)}

    {attestations.length > 0 && <section className="sec">
      <div className="rail-l"><div className="inner"><span className="num">✳</span><span className="label">Where you<br />met it</span></div></div>
      <div className="body">
        {attestations.map((attestation) => <div
          key={attestation.id}
          className={`att${marked(marks?.of(attestation.id) ?? null)}`}
          data-record={attestation.id}
        >
          <MarkGlyph mark={marks?.of(attestation.id) ?? null} />
          <p className="t">
            <DiffText
              text={attestation.text} form={null}
              words={marks?.field(attestation.id, "text")?.words ?? null}
            />
          </p>
          {attestation.translation && <p className="tr">
            <DiffText
              text={attestation.translation} form={null}
              words={marks?.field(attestation.id, "translation")?.words ?? null}
            />
          </p>}
          <div className="src">
            <span className="prov">{attestation.sourceKind}</span>
            {attestation.sourceTitle && (attestation.sourceUrl
              ? <a href={attestation.sourceUrl} target="_blank" rel="noreferrer">{attestation.sourceTitle}</a>
              : <span>{attestation.sourceTitle}</span>)}
            <span className="when">{formatDay(attestation.capturedAt)}</span>
          </div>
        </div>)}
      </div>
    </section>}

    {lexeme.notes.length > 0 && <section className="sec">
      <div className="rail-l"><div className="inner"><span className="num">✎</span><span className="label">Notes</span></div></div>
      <div className="body"><ul className="notes">{lexeme.notes.map((note, index) => {
        /* Keyed by position, not by text. Text is not an identity — two identical notes shared a
           React key, and a reworded one had no partner to diff against. */
        const change = marks?.note(index) ?? null;
        return <li key={index} className={marked(change?.mark ?? null).trim()} data-note={index}>
          <MarkGlyph mark={change?.mark ?? null} />
          <DiffText text={note} form={null} words={change?.words ?? null} />
        </li>;
      })}</ul></div>
    </section>}

    {study && <section className="sec">
      <div className="rail-l"><div className="inner"><span className="num">◷</span><span className="label">Study<br />{study.system}</span></div></div>
      <div className="body">
        <div className="stats">
          <div className="stat"><div className="label">Stability</div><div className="v">{study.stability}<small> d</small></div></div>
          <div className="stat"><div className="label">Difficulty</div><div className="v">{study.difficulty}<small>/10</small></div></div>
          <div className="stat"><div className="label">Retrievability</div><div className="v">{Math.round(study.retrievability * 100)}<small>%</small></div></div>
          <div className="stat"><div className="label">Reps · lapses</div><div className="v">{study.reps}<small> · {study.lapses}</small></div></div>
          <div className="stat"><div className="label">Last review</div><div className="v" style={{ fontSize: 14 }}>{formatDay(study.lastReview)}</div></div>
        </div>
      </div>
    </section>}

    {/* Tied to `meta` for the same reason the footer is: a proposal under review is not a stored
        word, and checking it against a dictionary is a thing you do to an entry you have. */}
    {meta && <DictionaryFold
      headword={lexeme.headword} lemma={lexeme.lemma} language={lexeme.language}
      onLoaded={onReference} />}

    {meta && <div className="meta-foot">
      <span>id <b>{lexeme.id}</b></span>
      <span>added <b>{formatDay(lexeme.createdAt)}</b></span>
      <span>edited <b>{formatDay(lexeme.editedAt)}</b></span>
      <span>rev <b>{lexeme.revision}</b></span>
    </div>}

    {playing && <ClipDialog
      stored={playing}
      headword={lexeme.headword}
      glossLang={article.glossLangs[0] ?? null}
      onClose={() => setPlaying(null)}
    />}
  </>;
}
