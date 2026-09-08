import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import AddView, { type AddTab, type CaptureSeed } from "./AddView";
import { backendSession, type CaptureHealth, type CaptureRequest } from "./api";
import {
  forgetCachedLookups, hydrateGlosses, lookup as lookupDictionaries, searchDictionaries,
  type SearchTier
} from "./dictionaries";
import ExternalArticle, { type DictionaryAddRequest } from "./ExternalArticle";
import {
  externalEntryOf, EXTERNAL_ROW_LIMIT, mergeHits,
  type ExternalEntry, type ExternalRow, type RawHit
} from "./externalEntries";
import { BackIcon, GearIcon, PencilIcon, PlusIcon, SearchIcon, TrashIcon } from "./icons";
import LexemeArticle from "./LexemeArticle";
import LexemeList, { type ExternalSearch } from "./LexemeList";
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
import Settings, { type Page as SettingsPage } from "./Settings";
import SignIn from "./SignIn";
import { setSearchScope, useSearchScope, type SearchScope } from "./searchScope";
import type { StoredSession } from "./session";
import { syncEngine } from "./sync";
import { SyncChip } from "./SyncStatus";
import { parseArticle, yamlFor, YamlProblems, type YamlProblem } from "./yaml";
import "./styles.css";

// CodeMirror is the largest dependency in the bundle and is only needed once the YAML tab or the
// YAML editor is actually opened, so it is loaded on demand rather than with everything else.
const YamlEditor = lazy(() => import("./YamlPane").then((module) => ({ default: module.YamlEditor })));
const YamlView = lazy(() => import("./YamlPane").then((module) => ({ default: module.YamlView })));

type Mode = "read" | "yaml" | "edit";

/** The scopes the chip offers. Your own words are deliberately absent — they are never optional. */
const SCOPES: [keyof SearchScope, string, string][] = [
  ["device", "Dictionaries on this device", "Instant, and answers with the server unreachable"],
  ["server", "Dictionaries on your server", "Read over the network as you pause"],
  ["online", "Online sources", "Asked only when you press ⏎"]
];

function scopeLabel(scope: SearchScope): string {
  const extra = SCOPES.filter(([key]) => scope[key]).length;
  return extra ? `yours +${extra}` : "yours";
}

function InstallGate({ onContinue }: { onContinue(): void }) {
  const platform = detectedInstallPlatform();
  const [promptAvailable, setPromptAvailable] = useState(canPromptInstall());
  const [installedHere, setInstalledHere] = useState(false);
  const [justInstalled, setJustInstalled] = useState(false);

  useEffect(() => {
    let active = true;
    void alreadyInstalledOnThisDevice().then((installed) => { if (active) setInstalledHere(installed); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    /* Chrome can fire its install event before this subscription exists, and the event is offered
       once. Re-reading the captured one here closes that gap; without it the button silently never
       appears and the only way in is Chrome's own menu. */
    setPromptAvailable(canPromptInstall());
    const available = () => setPromptAvailable(true);
    const installed = () => setJustInstalled(true);
    window.addEventListener(INSTALL_AVAILABLE_EVENT, available);
    window.addEventListener(INSTALLED_EVENT, installed);
    return () => {
      window.removeEventListener(INSTALL_AVAILABLE_EVENT, available);
      window.removeEventListener(INSTALLED_EVENT, installed);
    };
  }, []);

  const install = async () => {
    const accepted = await promptInstall();
    setPromptAvailable(false);
    if (accepted) setJustInstalled(true);
  };

  /* Installing and then landing on the browser's sign-in form reads as though the installation
     went nowhere. The app that was just added is the place to sign in, so this stops here and
     leaves continuing in the browser as the deliberate choice it was on the previous screen. */
  if (justInstalled) {
    return <div className="install-page"><section className="install-card" aria-labelledby="install-title">
      <p className="install-kicker">Acervo</p>
      <h1 id="install-title">Acervo is installed</h1>
      <p className="install-copy">Open Acervo from your home screen to sign in there.</p>
      <button className="continue-browser" onClick={onContinue}>Continue in browser</button>
    </section></div>;
  }

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
  const [addSeed, setAddSeed] = useState<CaptureSeed | null>(null);
  const [langMenu, setLangMenu] = useState(false);
  const [scopeMenu, setScopeMenu] = useState(false);

  /* What the dictionaries answered, and what is still being asked. Kept beside the search rather
     than inside `LexemeList` because ⏎ is handled on the input, which lives up here. */
  const scope = useSearchScope();
  const [externalRows, setExternalRows] = useState<ExternalRow[]>([]);
  const [externalSearching, setExternalSearching] = useState(false);
  const [onlineState, setOnlineState] = useState<ExternalSearch["online"]>("off");
  /* Why a tier came back empty. Silence is the one answer a search must never give: "no dictionary
     holds this word", "you have none switched on" and "the network refused" look identical without
     it, and only one of them is something the reader can act on. */
  const [externalTrouble, setExternalTrouble] = useState<string | null>(null);
  /** How many matched in total, so a cut list can say it was cut. */
  const [externalTotal, setExternalTotal] = useState(0);
  const [external, setExternal] = useState<ExternalEntry | null>(null);
  const [externalBusy, setExternalBusy] = useState(false);
  /* Which settings section is open, or null for closed. The native menu names a section, so
     "open settings" is not a boolean here. */
  const [settings, setSettings] = useState<SettingsPage | null>(null);
  const [armed, setArmed] = useState<"delete" | null>(null);
  const [toast, setToast] = useState("");
  const [update, setUpdate] = useState<UpdateStage | undefined>(() => updateStage());
  /* What the server can build entries with. `undefined` means unknown — still checking, or the
     server is unreachable — and unknown never disables anything: reads are offline-first, and a
     write that fails loudly is the behaviour everywhere else. Only a definite `available: false`
     turns Capture off, and then it says why. */
  const [captureHealth, setCaptureHealth] = useState<CaptureHealth | undefined>(undefined);

  const search = useRef<HTMLInputElement>(null);
  const main = useRef<HTMLElement>(null);
  /* Each tier answers on its own schedule, so the hits are kept apart and re-merged as they land.
     `token` drops the answer to a query nobody is asking any more. */
  const hits = useRef<Record<SearchTier, RawHit[]>>({ device: [], server: [], online: [] });
  const token = useRef(0);
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

  /* What the Mac menu bar calls. The native host owns a menu, not a second implementation: every
     one of these lands on the surface that already does the work, with its confirmations intact. */
  useEffect(() => {
    window.acervo = {
      command(name) {
        setSettings("data");
        setArmed(name === "delete" ? "delete" : null);
      }
    };
    return () => { delete window.acervo; };
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

  /* ── searching the dictionaries ───────────────────────────────────────
     Three speeds, and the difference between them is what each one costs. A dictionary stored on
     this device answers in under a millisecond, so it answers as you type. One only the server
     holds is read over byte ranges — a prefix search is a run of range requests — so it waits for a
     pause. An online source is never asked without ⏎ being pressed: §9 asks for no prefetching, and
     a rate limit should not be spent on a word someone was passing through. */

  const recount = useCallback((mine: number) => {
    const merged = mergeHits(search.current?.value ?? "", [
      ...hits.current.device, ...hits.current.server, ...hits.current.online]);
    /* Only as many rows as can be described. Reading a row's meaning costs a lookup in the
       dictionary that holds it — several range requests when that dictionary is on the server — so
       the list is cut to what is worth paying for. `casa` across seven dictionaries merged to
       thirty-four rows, and the twenty-two past the old hydration limit rendered as a column of
       em-dashes, which reads as a search that found nothing rather than as one that found plenty. */
    const shown = merged.slice(0, EXTERNAL_ROW_LIMIT);
    setExternalRows(shown);
    setExternalTotal(merged.length);
    void hydrateGlosses(shown, language).then((withGlosses) => {
      if (token.current === mine) setExternalRows(withGlosses);
    });
  }, [language]);

  useEffect(() => {
    const wanted = query.trim();
    const mine = (token.current += 1);
    hits.current = { device: [], server: [], online: [] };
    setExternalRows([]);
    setExternalTotal(0);
    setExternalTrouble(null);
    setOnlineState(wanted && scope.online ? "ready" : "off");
    if (!wanted || !language || (!scope.device && !scope.server)) {
      setExternalSearching(false);
      return;
    }
    setExternalSearching(true);

    const run = (tier: SearchTier, delay: number) => setTimeout(() => {
      void searchDictionaries(wanted, { language, tiers: [tier] })
        .then((found) => {
          if (token.current !== mine) return;
          hits.current[tier] = found.hits;
          if (found.failed.length) {
            setExternalTrouble(`${found.failed.join(" and ")} could not be read just now.`);
          } else if (tier === "device" && !found.asked && !scope.server) {
            setExternalTrouble("No dictionaries are switched on for this language. Settings → Dictionaries.");
          }
          recount(mine);
        })
        .finally(() => { if (token.current === mine && tier === "server") setExternalSearching(false); });
    }, delay);

    const timers = [
      scope.device ? run("device", 120) : null,
      scope.server ? run("server", 450) : null
    ].filter((timer): timer is ReturnType<typeof setTimeout> => timer !== null);
    if (!scope.server) setExternalSearching(false);
    return () => timers.forEach(clearTimeout);
  }, [query, language, scope, recount]);

  const searchOnline = useCallback(() => {
    const wanted = query.trim();
    if (!wanted || !scope.online) return;
    const mine = token.current;
    setOnlineState("searching");
    setExternalTrouble(null);
    void searchDictionaries(wanted, { language, tiers: ["online"] })
      .then((found) => {
        if (token.current !== mine) return;
        hits.current.online = found.hits;
        if (!found.asked) {
          setExternalTrouble("No online source is switched on. Settings → Dictionaries.");
        } else if (found.failed.length) {
          setExternalTrouble(`${found.failed.join(" and ")} could not be reached. `
            + "An online lookup goes through your server, so it needs that to be up too.");
        }
        recount(mine);
      })
      .catch(() => { if (token.current === mine) setExternalTrouble("The online lookup failed."); })
      .finally(() => { if (token.current === mine) setOnlineState("done"); });
  }, [query, language, scope.online, recount]);

  /**
   * Open a word an external dictionary holds.
   *
   * Only the tiers that offered the row are asked again, so opening a result found on this device
   * never quietly reaches for the network. `lookup` answers an online row out of the cache the
   * search already filled.
   */
  const openExternal = useCallback((row: ExternalRow) => {
    setExternalBusy(true);
    setOpenId(null);
    const tiers = [...new Set(row.sources.map((source) => source.origin))];
    void lookupDictionaries(row.word, language, tiers)
      .then((results) => {
        setExternal(externalEntryOf(row.word, results));
        if (main.current) main.current.scrollTop = 0;
      })
      .catch(() => notify("That entry could not be read."))
      .finally(() => setExternalBusy(false));
  }, [language, notify]);

  const externalSearch = useMemo<ExternalSearch>(() => ({
    rows: externalRows,
    total: externalTotal,
    trouble: externalTrouble,
    searching: externalSearching || externalBusy,
    enabled: scope.device || scope.server || scope.online,
    offline: syncStatus.state === "offline",
    online: onlineState,
    onOpen: openExternal,
    onSearchOnline: searchOnline
  }), [externalRows, externalTotal, externalTrouble, externalSearching, externalBusy, scope,
       syncStatus.state, onlineState, openExternal, searchOnline]);

  /**
   * Take a word from a dictionary into your own vocabulary.
   *
   * Not a second way to write: this fills in a capture and lets the ordinary pipeline run, so what
   * arrives is a proposal to review and the one writer is still
   * `repository.saveArticle(parseArticle(text))`. What is new is that the capture carries the entry
   * you were just reading as *reference* — grounding for the article, never sentences of your own.
   */
  const addFromDictionary = useCallback((request: DictionaryAddRequest) => {
    setAddSeed({
      headword: request.headword,
      reference: request.reference,
      referenceMode: request.referenceMode,
      note: request.note,
      sources: request.sources
    });
    setExternal(null);
    setProblems([]);
    setAddTab("capture");
  }, []);

  const openLexeme = useCallback((id: string) => {
    setOpenId(id);
    setExternal(null);
    setProblems([]);
    setMode("read");
    if (main.current) main.current.scrollTop = 0;
  }, []);

  const chooseTopic = useCallback((next: TopicSelection) => {
    setTopic(next);
    setOpenId(null);
    setExternal(null);
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
        else if (external) setExternal(null);
        else if (openId) setOpenId(null);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [addTab, external, mode, openId]);

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

  /* Asked once for the session, here rather than in the two views that show it: AddView is keyed
     and remounts for every seeded composition, so an effect of its own would re-ask on each one.
     Nothing awaits this and every failure is silence — startup must not depend on the server. */
  useEffect(() => {
    if (!session) return;
    let live = true;
    void backendSession.health()
      .then((health) => { if (live) setCaptureHealth(health?.capture); })
      .catch(() => { /* unknown, which is not the same as unavailable */ });
    return () => { live = false; };
  }, [session]);

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
    // The next session may be a different account on a different server, so nothing an external
    // source answered under this one survives into it.
    forgetCachedLookups();
    await backendSession.logout();
    await repository.clear();
    setSnapshot(null);
    setSettings(null);
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
    <div className="viewport" onClick={() => { setLangMenu(false); setScopeMenu(false); }}>
      <div className="app">
        <div className="brand"><span className="mark">A.</span></div>

        <header className="topbar">
          <div className={`search ${query.trim() ? "searching" : ""}`}>
            <SearchIcon />
            <input
              ref={search} type="search" placeholder="Search your words…" autoComplete="off" spellCheck={false}
              value={query}
              onChange={(event) => { setQuery(event.target.value); setOpenId(null); setExternal(null); }}
              // ⏎ is the only thing that ever reaches an online dictionary. Everything else here
              // answers off this device or off your own server.
              onKeyDown={(event) => { if (event.key === "Enter") searchOnline(); }}
            />
            <span className="kbd">⌘K</span>
            <button
              className="scope" aria-haspopup="menu" aria-label="What search covers"
              onClick={(event) => { event.stopPropagation(); setScopeMenu((open) => !open); }}
            >{scopeLabel(scope)}</button>
            <div className={`menu scope-menu ${scopeMenu ? "open" : ""}`} onClick={(event) => event.stopPropagation()}>
              {/* Your own words are not on this list. They are always searched and always first —
                  that ordering is the product, not a preference. */}
              <div className="label menu-label">Your words, then…</div>
              {SCOPES.map(([key, label, help]) => <label key={key} className={scope[key] ? "on" : ""}>
                <input
                  type="checkbox" checked={scope[key]}
                  onChange={(event) => setSearchScope(key, event.target.checked)}
                />
                <span><span>{label}</span><span className="hint">{help}</span></span>
              </label>)}
            </div>
          </div>

          <button className="tb-btn primary" onClick={() => setAddTab("capture")}>
            <PlusIcon /><span className="wide-only">Add</span>
          </button>

          {/* Shown on the native host too. The Mac window owns where the server is and how the
              app updates; sync status, signing out and deleting the vocabulary are operations on
              the vocabulary, which the host deliberately does not own — so they live here, and
              without this they were unreachable on macOS altogether. */}
          <SyncChip status={syncStatus} onOpen={() => setSettings("general")} />

          <button
            className={`icon-btn gear ${update === "ready" ? "has-update" : ""}`}
            onClick={() => setSettings("general")}
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
            // A seed is a fresh composition, not a prop change: remounting is what makes "add this
            // word, then that one" start clean rather than editing the previous draft.
            key={addSeed?.headword ?? "blank"}
            tab={addTab} onTab={setAddTab} graph={snapshot} problems={problems} busy={saving}
            seed={addSeed} captureHealth={captureHealth}
            onClose={() => { setProblems([]); setAddTab(null); setAddSeed(null); }}
            onCreate={(draft) => void createFromYaml(draft)}
            onCapture={captureText}
            onOpenLexeme={(id) => { setProblems([]); setAddTab(null); openLexeme(id); }}
            onNotify={notify}
          /> : article && mode === "edit" ? <Suspense fallback={<p className="empty">Loading the editor…</p>}>
            <YamlEditor
              // Remounts for a different entry, and only then: the draft must survive a sync.
              key={article.lexeme.id}
              name={article.lexeme.headword} yaml={yamlFor(article)}
              problems={problems} notice={null} busy={saving}
              onCancel={() => { setProblems([]); setMode("read"); }}
              onSave={(draft) => void saveArticleYaml(draft)}
            />
          </Suspense> : <div className="pane">
            {external && <div className="art-bar">
              <button className="icon-btn" aria-label="Back to the list" onClick={() => setExternal(null)}><BackIcon /></button>
              <span className="label">Other dictionaries</span>
              <span className="spacer" />
            </div>}
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
              // An external entry replaces the list the way one of your own does, and reads in the
              // same column: a word being looked up is the work, wherever it came from.
              : external ? <ExternalArticle entry={external} busy={saving} onAdd={addFromDictionary} />
              : !article ? <LexemeList
                  rows={rows} languageName={active.name} topic={topic}
                  topicLabel={topicLabel} topicIcon={topicIcon} query={query} sort={sort}
                  onSort={setSort} onOpen={openLexeme}
                  external={externalSearch}
                />
              : mode === "read" ? <LexemeArticle article={article} onUnsupported={notify} />
              // Editing is a composer above, so only reading and the read-only projection get here.
              : <Suspense fallback={<p className="empty">Loading the editor…</p>}>
                  <YamlView name={article.lexeme.headword} yaml={yamlFor(article)} />
                </Suspense>}
          </div>}
        </main>
      </div>
    </div>

    {settings && <Settings
      // Directing the dialog at a section is a fresh open, not a prop change: the section and the
      // armed confirmation are where it starts, and it navigates itself from there.
      key={`${settings}:${armed ?? ""}`}
      update={update} email={session.email} status={syncStatus} snapshot={snapshot} language={language}
      captureHealth={captureHealth}
      page={settings} arm={armed}
      onSignOut={() => void signOut()}
      onClose={() => { setSettings(null); setArmed(null); }}
      onNotify={notify}
      onChanged={() => setSnapshot(repository.snapshot())}
    />}
    <div className={`toast ${toast ? "show" : ""}`}>{toast}</div>
  </>;
}
