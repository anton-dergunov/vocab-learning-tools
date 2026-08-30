import { Fragment } from "react";
import type { Example, Gloss, ImagePrompt } from "./domain";
import { formatClock, formatDay } from "./format";
import { CaretIcon, PlayIcon } from "./icons";
import type { Article, ArticleSense } from "./selectors";

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

function ImageFold({ images }: { images: ImagePrompt[] }) {
  const rendered = images.filter((image) => image.imageRef);
  return <details className="fold">
    <summary><span className="caret"><CaretIcon /></span><span className="label">Images · {images.length}</span></summary>
    <div className="fold-body">
      {rendered.length > 0 && <div className="thumbs">
        {rendered.map((image) => <figure key={image.id} className="thumb" style={{ margin: 0 }}>
          <img src={image.imageRef!} alt="" />
          <figcaption className="cap"><span className="label">{image.styleId}</span></figcaption>
        </figure>)}
      </div>}
      {images.map((image) => <p key={image.id} className="hint" style={{ marginTop: 11 }}>{image.prompt}</p>)}
    </div>
  </details>;
}

function SenseSection({ entry, index, onUnsupported }: {
  entry: ArticleSense; index: number; onUnsupported(message: string): void;
}) {
  const { sense, examples, images } = entry;
  return <section className="sec">
    <div className="rail-l"><div className="inner">
      <span className="num">{String(index + 1).padStart(2, "0")}</span>
      <span className="label">Sense{sense.domain && <><br />{sense.domain}</>}</span>
    </div></div>
    <div className="body">
      <p className="sense-def">{sense.definition}</p>
      <div className="glosses">{sense.glosses.map((gloss) => <GlossLine key={gloss.lang} gloss={gloss} />)}</div>
      {examples.map((example) => <ExampleBlock key={example.id} example={example} onUnsupported={onUnsupported} />)}
      {images.length > 0 && <ImageFold images={images} />}
    </div>
  </section>;
}

/**
 * `meta` off drops the storage footer, which is what an unsaved proposal wants: id, added, edited
 * and rev are facts about a stored record, and a generated entry under review has none of them yet.
 * Everything above it is identical, because a proposal and the entry it becomes are the same thing.
 */
export default function LexemeArticle({ article, onUnsupported, meta = true }: {
  article: Article; onUnsupported(message: string): void; meta?: boolean;
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
      <SenseSection key={entry.sense.id} entry={entry} index={index} onUnsupported={onUnsupported} />)}

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

    {meta && <div className="meta-foot">
      <span>id <b>{lexeme.id}</b></span>
      <span>added <b>{formatDay(lexeme.createdAt)}</b></span>
      <span>edited <b>{formatDay(lexeme.editedAt)}</b></span>
      <span>rev <b>{lexeme.revision}</b></span>
    </div>}
  </>;
}
