import type { ListRow, SortKey, TopicSelection } from "./selectors";

const SORTS: [SortKey, string][] = [["recent", "Recent"], ["alpha", "A–Z"], ["hard", "Hardest"]];

function Strength({ row }: { row: ListRow }) {
  return <span className="strength" title={row.strengthLabel}>
    {[1, 2, 3, 4].map((bar) => <i key={bar} className={bar <= row.strength ? "f" : ""} />)}
  </span>;
}

export default function LexemeList({ rows, languageName, topic, topicLabel, topicIcon, query, sort, onSort, onOpen }: {
  rows: ListRow[];
  languageName: string;
  topic: TopicSelection;
  topicLabel: string;
  topicIcon: string;
  query: string;
  sort: SortKey;
  onSort(sort: SortKey): void;
  onOpen(id: string): void;
}) {
  const trimmed = query.trim();
  let title = topicLabel;
  let icon = topicIcon;
  let sub: string;
  if (trimmed) {
    title = "Search";
    icon = "🔍";
    sub = `${rows.length} match${rows.length === 1 ? "" : "es"} for “${trimmed}” in ${languageName}`;
  } else if (topic === "inbox") {
    sub = "Captured, processed, waiting for your review";
  } else if (topic === "all") {
    sub = `${rows.length} in ${languageName}`;
  } else {
    sub = `${rows.length} word${rows.length === 1 ? "" : "s"} in ${languageName}`;
  }

  return <>
    <div className="list-head">
      <div>
        <h1><span className="ic">{icon}</span>{title}</h1>
        <p className="label sub">{sub}</p>
      </div>
      <div className="sortbar">
        {SORTS.map(([key, text]) =>
          <button key={key} className={`sort-btn ${sort === key ? "on" : ""}`} onClick={() => onSort(key)}>{text}</button>)}
      </div>
    </div>
    <div className="rows">
      {rows.length ? rows.map((row) =>
        <button key={row.id} className={`row ${row.status === "inbox" ? "inbox" : ""}`} onClick={() => onOpen(row.id)}>
          <span className="plate">{row.emoji || "📄"}</span>
          <span>
            <span className="word">{row.headword}{row.reading && <span className="rdg">{row.reading}</span>}</span>
            <span className="gloss">{row.shortGloss}</span>
          </span>
          <span className="meta">
            {row.senseCount > 1 && <span className="senses">{row.senseCount} senses</span>}
            {row.status === "inbox" ? <span className="prov">unreviewed</span> : <Strength row={row} />}
          </span>
        </button>)
      : <p className="empty">Nothing here yet.</p>}
    </div>
  </>;
}
