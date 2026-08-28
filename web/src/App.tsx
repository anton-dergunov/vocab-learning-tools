import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AddSheet, { type AddTab } from "./AddSheet";
import { backendSession } from "./api";
import { BackIcon, GearIcon, PencilIcon, PlusIcon, SearchIcon, TrashIcon } from "./icons";
import LexemeArticle from "./LexemeArticle";
import LexemeList from "./LexemeList";
import { languageOf } from "./languages";
import { isNativeHost, UPDATE_EVENT, updateStage, type UpdateStage } from "./pwa";
import { repository, type ReplicaSnapshot } from "./repository";
import {
  articleFor, inboxCount, languageOptions, topicOptions, visibleRows,
  type SortKey, type TopicSelection
} from "./selectors";
import Settings from "./Settings";
import SignIn from "./SignIn";
import type { StoredSession } from "./session";
import { pullGraph } from "./sync";
import { yamlFor } from "./yaml";
import { YamlEditor, YamlView } from "./YamlPane";
import "./styles.css";

type Mode = "read" | "yaml" | "edit";

export default function App() {
  const native = isNativeHost();
  const [session, setSession] = useState<StoredSession | null | undefined>(undefined);
  const [snapshot, setSnapshot] = useState<ReplicaSnapshot | null>(null);
  const [syncedAt, setSyncedAt] = useState<string | null>(null);

  const [language, setLanguage] = useState("");
  const [topic, setTopic] = useState<TopicSelection>("all");
  const [sort, setSort] = useState<SortKey>("recent");
  const [query, setQuery] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("read");

  const [addTab, setAddTab] = useState<AddTab | null>(null);
  const [langMenu, setLangMenu] = useState(false);
  const [settings, setSettings] = useState(false);
  const [toast, setToast] = useState("");
  const [update, setUpdate] = useState<UpdateStage | undefined>(() => updateStage());

  const search = useRef<HTMLInputElement>(null);
  const main = useRef<HTMLElement>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const notify = useCallback((message: string) => {
    setToast(message);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), 2200);
  }, []);

  useEffect(() => {
    const changed = (event: Event) => setUpdate((event as CustomEvent<UpdateStage | undefined>).detail);
    window.addEventListener(UPDATE_EVENT, changed);
    return () => window.removeEventListener(UPDATE_EVENT, changed);
  }, []);

  useEffect(() => { void backendSession.restore().then(setSession); }, []);

  /* The replica renders first; the pull is a background refresh that may simply fail. */
  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    void (async () => {
      await repository.load(session.userId);
      if (!cancelled) setSnapshot(repository.snapshot());
      try {
        const stamp = await pullGraph();
        if (cancelled) return;
        setSnapshot(repository.snapshot());
        setSyncedAt(stamp);
      } catch (error) {
        if (!cancelled) notify(error instanceof Error ? error.message : "The vocabulary could not be refreshed.");
      }
    })();
    return () => { cancelled = true; };
  }, [session, notify]);

  const languages = useMemo(() => (snapshot ? languageOptions(snapshot) : []), [snapshot]);

  useEffect(() => {
    if (!languages.length) return;
    if (!languages.some((option) => option.code === language)) setLanguage(languages[0].code);
  }, [languages, language]);

  const rows = useMemo(
    () => (snapshot && language ? visibleRows(snapshot, { language, topic, query, sort }) : []),
    [snapshot, language, topic, query, sort]
  );
  const topics = useMemo(
    () => (snapshot && language ? topicOptions(snapshot, language) : []),
    [snapshot, language]
  );
  const article = useMemo(
    () => (snapshot && openId ? articleFor(snapshot, openId, snapshot.pending) : null),
    [snapshot, openId]
  );

  useEffect(() => {
    document.title = article ? `${article.lexeme.headword} — Acervo` : "Acervo";
  }, [article]);

  const openLexeme = useCallback((id: string) => {
    setOpenId(id);
    setMode("read");
    if (main.current) main.current.scrollTop = 0;
  }, []);

  const chooseTopic = useCallback((next: TopicSelection) => {
    setTopic(next);
    setOpenId(null);
    setQuery("");
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        search.current?.focus();
        search.current?.select();
      }
      if (event.key === "Escape") {
        if (addTab) setAddTab(null);
        else if (openId) setOpenId(null);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [addTab, openId]);

  async function removeLexeme(id: string) {
    await repository.delete("lexemes", id);
    setSnapshot(repository.snapshot());
    setOpenId(null);
    notify("Deleted — a tombstone was written to this device");
  }

  async function signOut() {
    await backendSession.logout();
    await repository.clear();
    setSnapshot(null);
    setSettings(false);
    setSession(null);
  }

  if (session === undefined) return <div className="signin-page" />;
  if (session === null) return <SignIn onSignedIn={setSession} />;

  const active = languageOf(language || "en");
  const inbox = snapshot && language ? inboxCount(snapshot, language) : 0;
  const currentTopic = topics.find((option) => option.id === topic);
  const topicLabel = topic === "all" ? "All words" : topic === "inbox" ? "Inbox" : currentTopic?.name ?? "Topic";
  const topicIcon = topic === "all" ? "📖" : topic === "inbox" ? "📥" : currentTopic?.icon ?? "📌";

  return <>
    <div className="viewport" onClick={() => setLangMenu(false)}>
      <div className="app">
        <div className="brand"><span className="mark">A.</span></div>

        <header className="topbar">
          <div className={`search ${query.trim() ? "searching" : ""}`}>
            <SearchIcon />
            <input
              ref={search} type="search" placeholder="Search your words…" autoComplete="off" spellCheck={false}
              value={query}
              onChange={(event) => { setQuery(event.target.value); setOpenId(null); }}
            />
            <span className="kbd">⌘K</span>
            <span className="scope">yours</span>
          </div>

          <button className="tb-btn primary" onClick={() => setAddTab("capture")}>
            <PlusIcon /><span className="wide-only">Add</span>
          </button>

          {!native && <button
            className={`icon-btn gear ${update === "ready" ? "has-update" : ""}`}
            onClick={() => setSettings(true)}
            aria-label={update === "ready" ? "Open settings; an update is ready" : "Open settings"}
          ><GearIcon /></button>}

          <button
            className="tb-btn lang-btn" aria-haspopup="menu" aria-label="Vocabulary language"
            onClick={(event) => { event.stopPropagation(); setLangMenu((open) => !open); }}
          >
            <span className="flag">{active.flag}</span>
            <span className="code">{active.code.toUpperCase()}</span>
          </button>
          <div className={`menu ${langMenu ? "open" : ""}`}>
            <div className="label menu-label">Vocabulary language</div>
            {languages.map((option) => <button
              key={option.code} className={option.code === language ? "on" : ""}
              onClick={() => { setLanguage(option.code); chooseTopic("all"); setLangMenu(false); }}
            >
              <span>{option.flag}</span><span>{option.name}</span><span className="cnt">{option.count}</span>
            </button>)}
          </div>
        </header>

        <nav className="rail" aria-label="Topics">
          <button className={`tab ${topic === "all" ? "on" : ""}`} title="All words" onClick={() => chooseTopic("all")}>
            <span className="ic">📖</span><span className="nm">All</span>
            <span className="cnt">{snapshot && language ? visibleRows(snapshot, { language, topic: "all", query: "", sort }).length : 0}</span>
          </button>
          {inbox > 0 && <button className={`tab ${topic === "inbox" ? "on" : ""}`} title="Inbox" onClick={() => chooseTopic("inbox")}>
            <span className="ic">📥</span><span className="nm">Inbox</span><span className="cnt">{inbox}</span>
          </button>}
          <div className="rail-sep" />
          {topics.map((option) => <button
            key={option.id} className={`tab ${topic === option.id ? "on" : ""}`} title={option.name}
            onClick={() => chooseTopic(option.id)}
          >
            <span className="ic">{option.icon}</span><span className="nm">{option.name}</span>
            {option.count !== null && <span className="cnt">{option.count}</span>}
          </button>)}
        </nav>

        <main className="main" ref={main}>
          <div className="pane">
            {article && <div className="art-bar">
              <button className="icon-btn" aria-label="Back to the list" onClick={() => setOpenId(null)}><BackIcon /></button>
              <span className="label">{topicLabel}</span>
              <span className="spacer" />
              <div className="seg">
                <button className={mode === "read" ? "on" : ""} onClick={() => setMode("read")}>Read</button>
                <button className={mode !== "read" ? "on" : ""} onClick={() => setMode("yaml")}>YAML</button>
              </div>
              <button className="icon-btn" aria-label="Edit as YAML" title="Edit as YAML" onClick={() => setMode("edit")}><PencilIcon /></button>
              <button className="icon-btn" aria-label="Delete" title="Delete" onClick={() => void removeLexeme(article.lexeme.id)}><TrashIcon /></button>
            </div>}

            {!snapshot ? <p className="empty">Opening your vocabulary…</p>
              : !article ? <LexemeList
                  rows={rows} languageName={active.name} topic={topic}
                  topicLabel={topicLabel} topicIcon={topicIcon} query={query} sort={sort}
                  onSort={setSort} onOpen={openLexeme}
                />
              : mode === "read" ? <LexemeArticle article={article} onUnsupported={notify} />
              : mode === "yaml" ? <YamlView name={article.lexeme.headword} yaml={yamlFor(article)} />
              : <YamlEditor
                  name={article.lexeme.headword} yaml={yamlFor(article)}
                  onCancel={() => setMode("read")}
                  onSave={() => notify("Editing is not wired up yet")}
                />}
          </div>
        </main>
      </div>
    </div>

    {addTab && <AddSheet tab={addTab} onTab={setAddTab} onClose={() => setAddTab(null)} onUnsupported={notify} />}
    {settings && <Settings
      update={update} email={session.email} syncedAt={syncedAt}
      onSignOut={() => void signOut()} onClose={() => setSettings(false)}
    />}
    <div className={`toast ${toast ? "show" : ""}`}>{toast}</div>
  </>;
}
