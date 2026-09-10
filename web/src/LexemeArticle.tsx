import { Fragment } from "react";
import type { Example, Gloss, ImagePrompt } from "./domain";
import { formatClock, formatDay } from "./format";
import { DictionaryFold } from "./ExternalArticle";
import { PlayIcon } from "./icons";
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

function ExampleBlock({ example, onUnsupported }: { example: Example; onUnsupported(message: string): void }) {
  const own = OWN_ORIGINS.has(example.origin);
  return <div className={`ex ${own ? "own" : ""}`}>
    <p className="t"><Marked text={example.text} form={example.matchedForm} /></p>
    {example.translation &&
      <p className="tr"><Marked text={example.translation} form={example.matchedTranslationForm} /></p>}
    <div className="foot">
      <span className={`prov ${own ? "own" : ""}`}>{example.origin}</span>
      {example.modelId && <span className="label">{example.modelId}</span>}
      {!example.approved && <span className="prov warnk">unapproved</span>}
      {example.audioRef && <button className="play mini" onClick={() => onUnsupported("Audio is not wired up yet")}>
        <PlayIcon />Play
      </button>}
    </div>
    {example.note && <p className="tr">✎ {example.note}</p>}
    {example.videoRef && <button className="clip" style={{ marginTop: 10 }} onClick={() => onUnsupported("Clip playback is not wired up yet")}>
      <span className="pl"><PlayIcon /></span>
      <span className="ti">{example.videoTitle ?? "Clip"}
        <span>clip · starts at {formatClock(example.videoStart)}</span></span>
    </button>}
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
function SenseSection({ entry, index, headword, pictures, onUnsupported }: {
  entry: ArticleSense; index: number; headword: string;
  pictures: PictureSlot | null;
  onUnsupported(message: string): void;
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

  return <section className="sec">
    <div className="rail-l"><div className="inner">
      <span className="num">{String(index + 1).padStart(2, "0")}</span>
      <span className="label">Sense{sense.domain && <><br />{sense.domain}</>}</span>
    </div></div>
    <div className="body">
      <p className="sense-def">{sense.definition}</p>
      <div className="glosses">{sense.glosses.map((gloss) => <GlossLine key={gloss.lang} gloss={gloss} />)}</div>
      {examples.map((example) => <Fragment key={example.id}>
        <ExampleBlock example={example} onUnsupported={onUnsupported} />
        {anchored.has(example.id) && frame(anchored.get(example.id)!)}
      </Fragment>)}
      {loose.map((image) => <Fragment key={image.id}>{frame(image)}</Fragment>)}
      {images.length === 0 && pictures && <EmptySenseImage
        busy={pictures.busy(sense.id)}
        onOpen={() => pictures.open(sense.id, null)}
      />}
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
export interface PictureSlot {
  /**
   * `senseId` is always the sense that was clicked, and `prompt` is null for one that has no row
   * yet. Both are needed: a sense with no row still belongs to a word whose brief can be written,
   * and the dialog has to know *which* sense's brief to show when it comes back.
   */
  open(senseId: string, prompt: ImagePrompt | null): void;
  busy(senseId: string): boolean;
}

export default function LexemeArticle({ article, onUnsupported, meta = true, pictures = null }: {
  article: Article; onUnsupported(message: string): void; meta?: boolean;
  pictures?: PictureSlot | null;
}) {
  const { lexeme, topics, senses, attestations, study } = article;
  return <>
    <div className="masthead">
      <div className="head-row">
        <div className="emoji-plate">{lexeme.emoji || "📄"}</div>
        <div className="head-text">
          <h1 className="headword">{lexeme.headword}</h1>
          {lexeme.reading && <div className="reading">{lexeme.reading}</div>}
          <div className="pron-row">
            {lexeme.ipa && <span className="ipa">{lexeme.ipa}</span>}
            <button className="play" onClick={() => onUnsupported("Audio is not wired up yet")}><PlayIcon />Listen</button>
          </div>
          <GrammarLine article={article} />
        </div>
      </div>
      <div className="chips">
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
        onUnsupported={onUnsupported}
      />)}

    {attestations.length > 0 && <section className="sec">
      <div className="rail-l"><div className="inner"><span className="num">✳</span><span className="label">Where you<br />met it</span></div></div>
      <div className="body">
        {attestations.map((attestation) => <div key={attestation.id} className="att">
          <p className="t">{attestation.text}</p>
          {attestation.translation && <p className="tr">{attestation.translation}</p>}
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
      <div className="body"><ul className="notes">{lexeme.notes.map((note) => <li key={note}>{note}</li>)}</ul></div>
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
      headword={lexeme.headword} lemma={lexeme.lemma} language={lexeme.language} />}

    {meta && <div className="meta-foot">
      <span>id <b>{lexeme.id}</b></span>
      <span>added <b>{formatDay(lexeme.createdAt)}</b></span>
      <span>edited <b>{formatDay(lexeme.editedAt)}</b></span>
      <span>rev <b>{lexeme.revision}</b></span>
    </div>}
  </>;
}
