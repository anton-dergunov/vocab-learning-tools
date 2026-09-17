import { BookIcon, GlobeIcon } from "./icons";
import type { ExternalRow } from "./externalEntries";
import type { ListRow, SortKey, TopicSelection } from "./selectors";

const SORTS: [SortKey, string][] = [["recent", "Recent"], ["alpha", "A–Z"], ["hard", "Hardest"]];

function Strength({ row }: { row: ListRow }) {
  return <span className="strength" title={row.strengthLabel}>
    {[1, 2, 3, 4].map((bar) => <i key={bar} className={bar <= row.strength ? "f" : ""} />)}
  </span>;
}

/**
 * What the external section is doing right now.
 *
 * `online` is separate from the rest because it is the one tier that never runs on its own: §9 asks
 * for no prefetching, and a rate limit is not something to spend on a word someone was only passing
 * through on the way to another one.
 */
export interface ExternalSearch {
  rows: ExternalRow[];
  /** How many matched before the list was cut to what could be described. */
  total: number;
  /** Why a tier came back empty, when the reason is something other than "no such word". */
  trouble: string | null;
  /** True while the device and server tiers are still answering. */
  searching: boolean;
  /** Whether anything at all is switched on to search. */
  enabled: boolean;
  /** The server is unreachable, so only what this device holds can answer. */
  offline: boolean;
  online: "off" | "ready" | "searching" | "done";
  onOpen(row: ExternalRow): void;
  onSearchOnline(): void;
}

function sourceLabel(row: ExternalRow): string {
  if (row.sources.length > 2) return `${row.sources.length} sources`;
  return row.sources.map((source) => source.name).join(" · ");
}

/**
 * The external section: everything Acervo can find that is not yours.
 *
 * Below a rule and after every one of your own words, always — the ordering is the product. What is
 * here carries no emoji, no sense count and no strength bars, because it has none of those things:
 * an external row must be unmistakable at a glance, and the surest way to do that is to show only
 * what is true about it.
 */
function ExternalSection({ query, search }: { query: string; search: ExternalSearch }) {
  const { rows, online } = search;
  return <div className="ext-section">
    <div className="list-sep"><span className="label">Other dictionaries</span></div>

    {search.offline && <p className="ext-status">
      Your server is unreachable, so only the dictionaries stored on this device are being searched.
    </p>}

    <div className="rows">
      {rows.map((row) => <button
        key={`${row.word}:${row.sources[0].dictionaryId}`} className="row ext"
        onClick={() => search.onOpen(row)}
      >
        <span className="plate ext" aria-hidden="true">
          {row.origin === "online" ? <GlobeIcon /> : <BookIcon />}
        </span>
        {/* The source names are repeated as an attribute so a phone can put them under the gloss
            instead of squeezing a second column onto a screen that has no room for one. */}
        <span data-sources={sourceLabel(row)}>
          <span className="word">{row.word}</span>
          <span className="gloss">{row.gloss || "—"}</span>
        </span>
        <span className="meta"><span className="src">{sourceLabel(row)}</span></span>
      </button>)}
    </div>

    {search.total > rows.length && <p className="ext-status">
      The closest {rows.length} of {search.total}. Type more of the word to narrow them.
    </p>}
    {search.searching && <p className="ext-status">Looking through your dictionaries…</p>}
    {/* A reason beats an absence. Switched off, unreachable and genuinely-not-there are three
        different answers, and only the last one is about the word. */}
    {search.trouble && <p className="ext-status trouble" role="status">{search.trouble}</p>}
    {!search.searching && !search.trouble && !rows.length && online !== "searching"
      && <p className="ext-status">No dictionary here holds “{query}”.</p>}

    {online === "ready" && <button className="ext-online" onClick={search.onSearchOnline}>
      <GlobeIcon /><span>Press ⏎ to look “{query}” up online</span>
    </button>}
    {online === "searching" && <p className="ext-status" role="status">Asking the online dictionaries…</p>}
  </div>;
}

export default function LexemeList({
  rows, languageName, topic, topicLabel, topicIcon, query, sort, onSort, onOpen, external, working
}: {
  rows: ListRow[];
  languageName: string;
  topic: TopicSelection;
  topicLabel: string;
  topicIcon: string;
  query: string;
  sort: SortKey;
  onSort(sort: SortKey): void;
  onOpen(id: string): void;
  /** Absent when nothing is being searched — an empty topic list has no external half. */
  external?: ExternalSearch;
  /** Whether the server is still filling a word in, so it can be found without opening it. */
  working?: (id: string) => boolean;
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

  const showExternal = Boolean(trimmed && external?.enabled);

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
            {working?.(row.id) && <span className="working-mark" role="img" aria-label="Still filling in" title="Still filling in" />}
            {row.senseCount > 1 && <span className="senses">{row.senseCount} senses</span>}
            {row.status === "inbox" ? <span className="prov">unreviewed</span> : <Strength row={row} />}
          </span>
        </button>)
      // With a search running, the dictionaries below are the answer, so this shrinks to a line
      // saying which question it is answering rather than taking the whole page to say "nothing".
      : showExternal ? <p className="ext-status none-yours">No words of yours match “{trimmed}”.</p>
      : <p className="empty">Nothing here yet.</p>}
    </div>
    {showExternal && external && <ExternalSection query={trimmed} search={external} />}
  </>;
}
