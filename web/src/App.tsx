import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import AddView, { type AddTab } from "./AddView";
import { backendSession, type CaptureRequest } from "./api";
import { BackIcon, GearIcon, PencilIcon, PlusIcon, SearchIcon, TrashIcon } from "./icons";
import LexemeArticle from "./LexemeArticle";
import LexemeList from "./LexemeList";
import { languageOf } from "./languages";
import {
  alreadyInstalledOnThisDevice, canPromptInstall, detectedInstallPlatform,
  INSTALL_AVAILABLE_EVENT, INSTALLED_EVENT, promptInstall,
  shouldOfferMobileInstall, UPDATE_EVENT, updateStage, type UpdateStage
} from "./pwa";
import { repository, type ReplicaSnapshot } from "./repository";
import {
  articleFor, inboxCount, languageOptions, topicOptions, visibleRows,
  type SortKey, type TopicSelection
} from "./selectors";
import Settings from "./Settings";
import SignIn from "./SignIn";
import type { StoredSession } from "./session";
import { syncEngine } from "./sync";
import { SyncChip } from "./SyncStatus";
import { parseArticle, yamlFor, YamlProblems, type YamlProblem } from "./yaml";
import { YamlEditor, YamlView } from "./YamlPane";
import "./styles.css";

type Mode = "read" | "yaml" | "edit";

function InstallGate({ onContinue }: { onContinue(): void }) {
  const platform = detectedInstallPlatform();
  const [promptAvailable, setPromptAvailable] = useState(canPromptInstall());
  const [installedHere, setInstalledHere] = useState(false);

  useEffect(() => {
    let active = true;
    void alreadyInstalledOnThisDevice().then((installed) => { if (active) setInstalledHere(installed); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const available = () => setPromptAvailable(true);
    const installed = () => onContinue();
    window.addEventListener(INSTALL_AVAILABLE_EVENT, available);
    window.addEventListener(INSTALLED_EVENT, installed);
    return () => {
      window.removeEventListener(INSTALL_AVAILABLE_EVENT, available);
      window.removeEventListener(INSTALLED_EVENT, installed);
    };
  }, [onContinue]);

  const install = async () => {
    const accepted = await promptInstall();
    setPromptAvailable(false);
    if (accepted) onContinue();
  };

  return <div className="install-page"><section className="install-card" aria-labelledby="install-title">
    <p className="install-kicker">Acervo</p>
    <h1 id="install-title">Install the app</h1>
    {platform === "ios" ? <ol className="install-steps">
      <li>Open this page in <strong>Safari</strong>.</li>
      <li>Tap <strong>Share</strong>.</li>
      <li>Choose <strong>Add to Home Screen</strong>, then tap <strong>Add</strong>.</li>
    </ol> : <>
      <p className="install-copy">{promptAvailable
        ? "Add Acervo to your home screen for a compact, full-screen experience."
        : installedHere
          ? "Acervo is already installed on this device. Open it from your home screen, or carry on here in the browser."
          : "Chrome only offers the install button once. If it does not appear, open the ⋮ menu: it offers Install app when Acervo is not installed yet, and Open app when it already is."}</p>
      {promptAvailable && <button className="tb-btn primary install-button" onClick={() => void install()}>Install Acervo</button>}
    </>}
    <button className="continue-browser" onClick={onContinue}>Continue in browser</button>
  </section></div>;
}

export default function App() {
  const [showInstall, setShowInstall] = useState(() => shouldOfferMobileInstall()
    && sessionStorage.getItem("acervo-install-dismissed") !== "true");
  const [session, setSession] = useState<StoredSession | null | undefined>(undefined);
  const [snapshot, setSnapshot] = useState<ReplicaSnapshot | null>(null);

  const [language, setLanguage] = useState("");
  const [topic, setTopic] = useState<TopicSelection>("all");
  const [sort, setSort] = useState<SortKey>("recent");
  const [query, setQuery] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("read");
  const [problems, setProblems] = useState<YamlProblem[]>([]);
  const [saving, setSaving] = useState(false);

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

  const syncStatus = useSyncExternalStore(syncEngine.subscribe, syncEngine.getStatus);

  useEffect(() => { void backendSession.restore().then(setSession); }, []);

  /* A rejected token drops the sign-in but keeps the replica: the vocabulary is still the owner's,
     and signing back in puts the article they were reading straight back on screen. */
  useEffect(() => {
    backendSession.onUnauthorized(() => {
      syncEngine.stop();
      void backendSession.reject().then(() => setSession(null));
    });
    return () => backendSession.onUnauthorized(null);
  }, []);

  /* The replica renders first and the engine refreshes it behind that, so a server that is down
     costs nothing but freshness. Every later repaint is driven by the sync status changing. */
  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    void (async () => {
      await repository.load(session.userId);
      if (cancelled) return;
      setSnapshot(repository.snapshot());
      syncEngine.start();
      await syncEngine.syncNow();
      // Extending the token happens once the vocabulary is already on screen, and signs the owner
      // out only if the server answers and rejects it.
      await backendSession.refresh();
    })();
    return () => { cancelled = true; syncEngine.stop(); };
  }, [session]);

  useEffect(() => {
    if (session && repository.snapshot().ready) setSnapshot(repository.snapshot());
  }, [session, syncStatus]);

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
    () => (snapshot && openId ? articleFor(snapshot, openId) : null),
    [snapshot, openId]
  );

  useEffect(() => {
    document.title = article ? `${article.lexeme.headword} — Acervo` : "Acervo";
  }, [article]);

  const openLexeme = useCallback((id: string) => {
    setOpenId(id);
    setProblems([]);
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
      // Innermost first: leave what you are composing before leaving the entry it belongs to.
      if (event.key === "Escape") {
        if (addTab) { setProblems([]); setAddTab(null); }
        else if (mode === "edit") { setProblems([]); setMode("read"); }
        else if (openId) setOpenId(null);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [addTab, mode, openId]);

  /**
   * The one path a YAML document takes, whether it came from the article editor or the add sheet.
   * Parsing reports every problem at once; the repository decides what is a create, an update or a
   * removal and sends the lot as one write. A refusal leaves both the replica and the draft alone,
   * so nothing typed is lost to a failed save.
   */
  async function applyYaml(text: string): Promise<string | null> {
    setSaving(true);
    setProblems([]);
    try {
      const id = await repository.saveArticle(parseArticle(text));
      setSnapshot(repository.snapshot());
      return id;
    } catch (error) {
      if (error instanceof YamlProblems) setProblems(error.problems);
      else setProblems([{ line: null, message: error instanceof Error ? error.message : String(error) }]);
      return null;
    } finally {
      setSaving(false);
    }
  }

  async function saveArticleYaml(text: string) {
    const id = await applyYaml(text);
    if (!id) return;
    setMode("read");
    notify("Saved to the server");
  }

  async function createFromYaml(text: string) {
    const id = await applyYaml(text);
    if (!id) return;
    setAddTab(null);
    openLexeme(id);
    notify("Added to your vocabulary");
  }

  /**
   * Capture submits text and gets back a proposal — never a stored record. Everything that saves
   * still goes through `createFromYaml`, so a generated entry and a typed one are the same write.
   */
  const captureText = useCallback((request: CaptureRequest) => {
    const deviceId = repository.snapshot().deviceId;
    return backendSession.captureText(deviceId, request);
  }, []);

  async function removeLexeme(id: string) {
    try {
      await repository.delete("lexemes", id);
    } catch (error) {
      // Nothing was changed locally. Saying so is the point: the entry is still there.
      notify(error instanceof Error ? error.message : "That entry could not be deleted.");
      return;
    }
    setSnapshot(repository.snapshot());
    setOpenId(null);
    notify("Deleted everywhere — the entry is kept as a tombstone");
  }

  async function signOut() {
    syncEngine.stop();
    await backendSession.logout();
    await repository.clear();
    setSnapshot(null);
    setSettings(false);
    setSession(null);
  }

  const dismissInstall = useCallback(() => {
    sessionStorage.setItem("acervo-install-dismissed", "true");
    setShowInstall(false);
  }, []);

  if (showInstall) return <InstallGate onContinue={dismissInstall} />;
  if (session === undefined) return <div className="signin-page" />;
  if (session === null) return <SignIn onSignedIn={setSession} />;

  const active = languageOf(language || "en");
  /** Both surfaces you compose in. The main region stops scrolling and hands that to the view. */
  const composing = Boolean(addTab) || Boolean(article && mode === "edit");
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

          {/* Shown on the native host too. The Mac window owns where the server is and how the
              app updates; sync status, signing out and deleting the vocabulary are operations on
              the vocabulary, which the host deliberately does not own — so they live here, and
              without this they were unreachable on macOS altogether. */}
          <SyncChip status={syncStatus} onOpen={() => setSettings(true)} />

          <button
            className={`icon-btn gear ${update === "ready" ? "has-update" : ""}`}
            onClick={() => setSettings(true)}
            aria-label={update === "ready" ? "Open settings; an update is ready" : "Open settings"}
          ><GearIcon /></button>

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

        {/* Composing replaces the list rather than covering it: the entry you are writing is the
            work, the list behind it is not, and a bounded column is the only shape that keeps a
            title and a save button on screen at every window size. */}
        <main className={`main ${composing ? "composing" : ""}`} ref={main}>
          {addTab ? <AddView
            tab={addTab} onTab={setAddTab} problems={problems} busy={saving}
            onClose={() => { setProblems([]); setAddTab(null); }}
            onCreate={(draft) => void createFromYaml(draft)}
            onCapture={captureText}
            onOpenLexeme={(id) => { setProblems([]); setAddTab(null); openLexeme(id); }}
          /> : article && mode === "edit" ? <YamlEditor
            // Remounts for a different entry, and only then: the draft must survive a sync.
            key={article.lexeme.id}
            name={article.lexeme.headword} yaml={yamlFor(article)}
            problems={problems} notice={null} busy={saving}
            onCancel={() => { setProblems([]); setMode("read"); }}
            onSave={(draft) => void saveArticleYaml(draft)}
          /> : <div className="pane">
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
              // Editing is a composer above, so only reading and the read-only projection get here.
              : <YamlView name={article.lexeme.headword} yaml={yamlFor(article)} />}
          </div>}
        </main>
      </div>
    </div>

    {settings && <Settings
      update={update} email={session.email} status={syncStatus} snapshot={snapshot} language={language}
      onSignOut={() => void signOut()} onClose={() => setSettings(false)} onNotify={notify}
      onChanged={() => setSnapshot(repository.snapshot())}
    />}
    <div className={`toast ${toast ? "show" : ""}`}>{toast}</div>
  </>;
}
