import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import AddView, { type AddTab, type CaptureSeed } from "./AddView";
import type { ImagePrompt } from "./domain";
import AskDock, { type Detent } from "./AskDock";
import ReviewBar from "./ReviewBar";
import LoopBar from "./LoopBar";
import LoopDialog from "./LoopDialog";
import LoopView from "./LoopView";
import * as loopPlayer from "./loops";
import {
  applyOps, diffDrafts, EditRefused, type DraftDiff, type EditOp
} from "./articleEdit";
import { newId } from "./ids";
import {
  backendSession, type CaptureFoldable, type CaptureHealth, type CaptureRequest,
  type ChatCapture, type ChatNeighbour,
  type ChatProposal, type ChatSubject, type ChatTurn, type ImageStyle
} from "./api";
import {
  forgetCachedLookups, hydrateGlosses, lookup as lookupDictionaries, searchDictionaries,
  type SearchTier
} from "./dictionaries";
import ExternalArticle, { type DictionaryAddRequest } from "./ExternalArticle";
import {
  externalEntryOf, EXTERNAL_ROW_LIMIT, mergeHits, referenceTextOf,
  type ExternalEntry, type ExternalRow, type RawHit
} from "./externalEntries";
import { BackIcon, FileIcon, GearIcon, MoreIcon, PencilIcon, PlusIcon, SearchIcon, TrashIcon } from "./icons";
import { useDefaultArticleView, type ArticleView } from "./editorPreferences";
import LexemeArticle, {
  type AskSlot, type AskTarget, type ClipSlot, type MarkSlot, type PictureSlot, HeadwordListen
} from "./LexemeArticle";
import LexemeList, { type ExternalSearch } from "./LexemeList";
import { languageOf } from "./languages";
import {
  alreadyInstalledOnThisDevice, canPromptInstall, detectedInstallPlatform,
  INSTALL_AVAILABLE_EVENT, INSTALLED_EVENT, promptInstall,
  shouldOfferMobileInstall, UPDATE_EVENT, updateStage, type UpdateStage
} from "./pwa";
import { repository, type ReplicaSnapshot } from "./repository";
import {
  articleFor, articleFromDraft, inboxCount, languageOptions, lexemesIn, shortGlossOf,
  topicOptions, visibleRows, type SortKey, type TopicSelection
} from "./selectors";
import Settings, { type Page as SettingsPage } from "./Settings";
import SignIn from "./SignIn";
import { setSearchScope, useSearchScope, type SearchScope } from "./searchScope";
import type { StoredSession } from "./session";
import { syncEngine } from "./sync";
import {
  clipSearchOf, drawingPictures, enrichmentOf, isEnriching, isOpen, jobFor, jobStream
} from "./jobs";
import ProgressStrip from "./ProgressStrip";
import { ImageDialog } from "./ImageDialog";
import { clearPictures } from "./media";
import { fill, forgetPronunciations } from "./pronunciation";
import { SyncChip } from "./SyncStatus";
import {
  draftFor, parseArticle, yamlFor, yamlForDraft, YamlProblems,
  type ArticleDraft, type YamlProblem
} from "./yaml";
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
  /* Which view an article is read in. The device's default comes from Settings; the switch above an
     article overrides it for this sitting and no longer. */
  const defaultView = useDefaultArticleView();
  const [viewChoice, setViewChoice] = useState<ArticleView | null>(null);
  const [problems, setProblems] = useState<YamlProblem[]>([]);
  const [saving, setSaving] = useState(false);

  /* The conversation, in memory and keyed by what is being discussed. Design §06 §3.3: §01's test
     for whether something belongs in the core is whether losing it would hurt, and losing a
     transcript costs nothing — the *article* is where the value landed. So no collection, no sync
     state, nothing to tombstone, and it is gone on reload on purpose. A ref holds it across the
     dock unmounting; the state beside it is only what makes the dock re-render. */
  const threads = useRef(new Map<string, ChatTurn[]>());
  const [thread, setThread] = useState<ChatTurn[]>([]);
  const [askFocus, setAskFocus] = useState<AskTarget | null>(null);
  /** What the dictionary fold has open beneath the article, if anything. Read-only context. */
  const [reference, setReference] = useState<ExternalEntry | null>(null);
  const [seededTurn, setSeededTurn] = useState<string | null>(null);
  /**
   * How far open the conversation is, mirrored from the dock.
   *
   * `App` does not own the detent — the dock does — but at `full` the article must not be drawn at
   * all, and only this component holds both. Reaching `full` used to leave a one-line strip of
   * article above the sheet, which was useless on a phone and no better on a desktop.
   */
  const [askDetent, setAskDetent] = useState<Detent>("dock");
  /** Where the article was, so a trip to `full` and back does not land you at the masthead. */
  const parked = useRef(0);
  /**
   * A proposal under review. Never stored, never replicated, and dropped rather than kept: it is a
   * suggestion, not a state (§6.3). `before` is what undo saves; `after` is what save saves;
   * `diff.shown` is what is rendered, and is `after` plus the removed records put back so they can
   * be drawn struck through.
   */
  const [proposal, setProposal] = useState<{
    before: ArticleDraft; after: ArticleDraft; diff: DraftDiff;
    minted: ReadonlySet<string>; summary: string;
  } | null>(null);
  /** The document a save replaced, so undo is one more ordinary write. */
  const undoable = useRef<{ id: string; text: string } | null>(null);
  const [addTab, setAddTab] = useState<AddTab | null>(null);
  const [addSeed, setAddSeed] = useState<CaptureSeed | null>(null);
  /* A composition has a lifetime, so it gets one door in and one door out. Closing used to be an
     ad-hoc edit of the two states above at five call sites, three of which cleared the tab and left
     the seed behind — so the next press of Add reopened the dictionary word you had walked away
     from and, because a seed processes itself on arrival, spent a capture on it. The counter is the
     composition's identity: keying the view on the headword instead meant two compositions of the
     same word shared a draft. */
  const [composition, setComposition] = useState(0);
  const openCapture = useCallback((seed: CaptureSeed | null) => {
    setProblems([]);
    setLoops(false);
    setAddSeed(seed);
    setAddTab("capture");
    setComposition((count) => count + 1);
  }, []);
  const closeCapture = useCallback(() => {
    setProblems([]);
    setAddTab(null);
    setAddSeed(null);
  }, []);
  const [langMenu, setLangMenu] = useState(false);
  const [articleMenu, setArticleMenu] = useState(false);
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
  /* Loops. Its own surface, reached from the bar at the foot of a phone or the chip in the top bar
     of a desktop — never a sheet over the list, because a player is a place you go to and the words
     it shows need the column. What is *playing* is the player module's, not this: a loop goes on
     playing while you read a word. */
  const [loops, setLoops] = useState(false);
  const [makingLoop, setMakingLoop] = useState(false);
  /* One door in, so everything that opens it also closes whatever it replaces — the same shape
     `openCapture` has. */
  const openLoops = useCallback(() => {
    setLoops(true);
    setOpenId(null);
    setExternal(null);
    setAddTab(null);
  }, []);
  const [settings, setSettings] = useState<SettingsPage | null>(null);
  const [armed, setArmed] = useState<"delete" | null>(null);
  const [toast, setToast] = useState("");
  /** One optional action on the toast. Undo after a chat edit is the only thing that uses it. */
  const [toastAction, setToastAction] = useState<{ label: string; run(): void } | null>(null);
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

  const notify = useCallback((message: string, action?: { label: string; run(): void }) => {
    setToast(message);
    setToastAction(action ?? null);
    clearTimeout(toastTimer.current);
    // An action needs long enough to read the sentence and decide. Without one, nothing is lost by
    // the toast going.
    toastTimer.current = setTimeout(() => { setToast(""); setToastAction(null); }, action ? 7000 : 2200);
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

  /* After every pull, bring the clips the replica names onto this device, so a word recorded on
     another device, or in advance, plays on a plane. `fill` does nothing while keeping is off. */
  useEffect(() => {
    if (syncStatus.lastPulledAt) void fill();
  }, [syncStatus.lastPulledAt]);

  useEffect(() => { void backendSession.restore().then(setSession); }, []);

  /* A rejected token drops the sign-in but keeps the replica: the vocabulary is still the owner's,
     and signing back in puts the article they were reading straight back on screen. */
  useEffect(() => {
    backendSession.onUnauthorized(() => {
      syncEngine.stop();
      jobStream.stop();
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
      // The server does the work; this only listens, so a word saved elsewhere fills in here too.
      jobStream.start();
      await syncEngine.syncNow();
      // Extending the token happens once the vocabulary is already on screen, and signs the owner
      // out only if the server answers and rejects it.
      await backendSession.refresh();
    })();
    return () => { cancelled = true; syncEngine.stop(); jobStream.stop(); };
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
  /* Two feeders, one renderer. A stored article is `articleFor`; a live proposal is an unsaved
     document under review, which is exactly what `articleFromDraft` exists for and exactly what
     `AddView` already does with a generated entry. A proposal puts this view into AddView's regime
     for as long as it lasts and leaves it the moment it is saved or discarded — same component,
     same rule, no third feeder. */
  const article = useMemo(
    () => (proposal && snapshot ? articleFromDraft(snapshot, proposal.diff.shown)
      : snapshot && openId ? articleFor(snapshot, openId) : null),
    [snapshot, openId, proposal]
  );

  const markSlot = useMemo<MarkSlot | null>(() => {
    if (!proposal) return null;
    const { records, notes } = proposal.diff;
    return {
      of: (id) => records.get(id)?.mark ?? null,
      field: (id, field) => records.get(id)?.fields.get(field) ?? null,
      note: (index) => notes.get(index) ?? null,
      movedFrom: (id) => records.get(id)?.wasAt ?? null
    };
  }, [proposal]);

  useEffect(() => {
    document.title = article ? `${article.lexeme.headword} — Acervo` : "Acervo";
  }, [article]);

  /* The server's work on each word, as this device last heard it. */
  const jobsStatus = useSyncExternalStore(jobStream.subscribe, jobStream.getStatus);
  const enrichJob = article ? enrichmentOf(jobsStatus, article.lexeme.id) : undefined;
  /* Cards re-flow as each result lands, so a word still filling in is read on the page, where the
     reserved slots keep the layout still. Nothing is held back and nothing refreshes by hand. */
  const enriching = isOpen(enrichJob);

  /* A proposal is reviewed on the page — its marks and the conversation that made it live there — so
     one being live overrides the choice rather than being hidden behind a card. */
  const view: ArticleView = proposal || enriching ? "page" : viewChoice ?? defaultView;
  const reading = mode === "read";
  const carding = Boolean(article) && reading && view === "cards" && !external;

  /** The conversation has taken the pane, so the article is not drawn. */
  const asking = askDetent === "full" && reading && Boolean(external || (article && view === "page"));

  /* `.main.composing` sets `overflow: hidden`, which clamps `scrollTop` to zero — so the offset is
     parked on the way into `full` and put back on the way out. Four lines, and the alternative was
     positioning the sheet against a topbar on one layout and a topbar plus a dynamic rail on the
     other. */
  useEffect(() => {
    const host = main.current;
    if (!host) return;
    if (asking) {
      parked.current = host.scrollTop;
      return () => { host.scrollTop = parked.current; };
    }
  }, [asking]);

  /* A proposal is written against one revision of one entry. If sync brings a newer one while the
     conversation is open, the proposal is dropped rather than rebased — the server would refuse the
     write anyway, and silently re-marking a document nobody proposed would be worse than saying so. */
  const openRevision = snapshot && openId
    ? snapshot.lexemes.find((one) => one.id === openId)?.revision ?? null
    : null;
  const reviewedAt = useRef<number | null>(null);
  useEffect(() => {
    if (!proposal) { reviewedAt.current = openRevision; return; }
    if (reviewedAt.current !== null && openRevision !== null && openRevision !== reviewedAt.current) {
      setProposal(null);
      notify("That entry changed elsewhere, so the proposal was dropped.");
    }
  }, [openRevision, proposal, notify]);

  /* ── pictures ─────────────────────────────────────────────────────────
     The article shows what the replica holds; the dialog is the only thing that changes a picture,
     and it writes through the image routes. A write is followed by a pull, so the record the server
     stored is what the article re-renders from rather than this component's optimism. */
  const [imageStyles, setImageStyles] = useState<ImageStyle[]>([]);
  const [editingImage, setEditingImage] = useState<{ senseId: string; prompt: ImagePrompt | null } | null>(null);

  /* The style list is needed only once a dialog opens, so it is fetched then rather than at start:
     it is server state behind auth, and an offline session should reach the article regardless. */
  useEffect(() => {
    if (!editingImage || imageStyles.length) return;
    void backendSession.imageSettings()
      .then((settings) => setImageStyles(settings.styles))
      .catch(() => notify("The style list could not be read from the server."));
  }, [editingImage, imageStyles.length, notify]);

  /* Senses whose picture is being replaced by a file or removed from this device. Local because it
     lasts exactly as long as the round trip; a redraw is a server job and shows through the job map. */
  const [replacing, setReplacing] = useState<ReadonlySet<string>>(new Set());

  /**
   * A write that replaces a picture, with the sense marked while it runs.
   *
   * Nothing is forgotten on the device and nothing needs to be: a picture's reference carries a
   * digest of its bytes, so the new picture is a new reference and the cache is simply asked for
   * something it has never held. The pull is what brings that reference down.
   */
  const replacePicture = useCallback(async (senseId: string, write: () => Promise<unknown>) => {
    setReplacing((held) => new Set(held).add(senseId));
    try {
      await write();
      await syncEngine.syncNow();
      setSnapshot(repository.snapshot());
    } catch (error) {
      notify(error instanceof Error ? error.message : "That did not work.");
    } finally {
      setReplacing((held) => {
        const next = new Set(held);
        next.delete(senseId);
        return next;
      });
    }
  }, [notify]);

  /** Try again: a new job, which the server runs whether or not this page stays open. */
  const retryEnrichment = useCallback((lexemeId: string) => {
    void backendSession.enqueueJob({ kind: "enrich", subject: { kind: "lexeme", id: lexemeId } })
      .then((job) => jobStream.apply(job))
      .catch((error) => notify(error instanceof Error ? error.message : "That could not be asked for again."));
  }, [notify]);

  const dismissEnrichment = useCallback((lexemeId: string) => {
    const job = enrichmentOf(jobStream.getStatus(), lexemeId);
    jobStream.forget("enrich", lexemeId);
    if (job) void backendSession.dismissJob(job.id).catch(() => undefined);
  }, []);

  /** A picture action is a job, so leaving the word does not lose it. */
  const askForPicture = useCallback((
    kind: "image.redraw" | "image.rebrief", subject: { kind: string; id: string },
    input?: Record<string, string>
  ) => {
    void backendSession.enqueueJob({ kind, subject, ...(input ? { input } : {}) })
      .then((job) => jobStream.apply(job))
      .catch((error) => notify(error instanceof Error ? error.message : "That could not be asked for."));
  }, [notify]);

  /* A finished job's outcome is shown for as long as its word stays open, and not the next time. */
  const shownWord = useRef<string | null>(null);
  useEffect(() => {
    const left = shownWord.current;
    shownWord.current = openId;
    if (left && left !== openId) jobStream.forget("enrich", left);
  }, [openId]);

  const pictures = useMemo<PictureSlot | null>(() => {
    if (!article || mode !== "read") return null;
    const drawing = drawingPictures(enrichJob);
    const rebriefing = isOpen(jobFor(jobsStatus, "image.rebrief", article.lexeme.id));
    return {
      open: (senseId, prompt) => setEditingImage({ senseId, prompt }),
      retry: (prompt) => askForPicture("image.redraw", { kind: "imagePrompt", id: prompt.id }),
      busy: (senseId) => {
        if (replacing.has(senseId)) return true;
        const record = article.senses.find((entry) => entry.sense.id === senseId)?.images[0] ?? null;
        if (record && isOpen(jobFor(jobsStatus, "image.redraw", record.id))) return true;
        if (rebriefing && !record?.imageRef) return true;
        if (!drawing) return false;
        // Only a sense the job will draw: one with a picture, or one ruled out, is not waiting.
        return !record || (!record.imageRef && !record.suppressed && !record.failureReason);
      }
    };
  }, [article, mode, enrichJob, jobsStatus, replacing, askForPicture]);

  const clips = useMemo<ClipSlot | null>(() => {
    if (!article || mode !== "read") return null;
    const lexemeId = article.lexeme.id;
    return {
      search: clipSearchOf(enrichJob, article.lexeme.clipsSearchedAt),
      retry: () => retryEnrichment(lexemeId),
      remove: (exampleId) => {
        void repository.delete("examples", exampleId)
          .then(() => setSnapshot(repository.snapshot()))
          .catch((error) => notify(error instanceof Error ? error.message : "That clip could not be removed."));
      }
    };
  }, [article, mode, enrichJob, notify, retryEnrichment]);

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
    setExternal(null);
    openCapture({
      headword: request.headword,
      reference: request.reference,
      referenceMode: request.referenceMode,
      note: request.note,
      sources: request.sources
    });
  }, [openCapture]);

  const openLexeme = useCallback((id: string) => {
    setOpenId(id);
    // A proposal belongs to the entry it was written against, and is a suggestion rather than a
    // state: leaving the article drops it.
    setProposal(null);
    setExternal(null);
    setProblems([]);
    setMode("read");
    if (main.current) main.current.scrollTop = 0;
  }, []);

  const chooseTopic = useCallback((next: TopicSelection) => {
    setTopic(next);
    setLoops(false);
    setOpenId(null);
    setProposal(null);
    setExternal(null);
    setQuery("");
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        // Reaching for search is asking for the list, and the list is not drawn while a loop
        // surface owns the pane. The loop itself plays on; the bar is what it plays behind.
        setLoops(false);
        search.current?.focus();
        search.current?.select();
      }
      // Innermost first: leave what you are composing before leaving the entry it belongs to.
      if (event.key === "Escape") {
        if (addTab) closeCapture();
        else if (mode === "edit") { setProblems([]); setMode("read"); }
        else if (external) setExternal(null);
        else if (openId) setOpenId(null);
        else if (loops) setLoops(false);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [addTab, closeCapture, external, loops, mode, openId]);

  /**
   * The one path a YAML document takes, whether it came from the article editor or the add sheet.
   * Parsing reports every problem at once; the repository decides what is a create, an update or a
   * removal and sends the lot as one write. A refusal leaves both the replica and the draft alone,
   * so nothing typed is lost to a failed save.
   */
  async function applyYaml(text: string, minted?: ReadonlySet<string>): Promise<string | null> {
    setSaving(true);
    setProblems([]);
    try {
      const id = await repository.saveArticle(parseArticle(text), minted);
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
    closeCapture();
    openLexeme(id);
    /* The save queued the word's enrichment on the server. It opens on the page, whatever the
       device's default, because that is where its clips and pictures land without moving it. */
    setViewChoice("page");
    notify("Added to your vocabulary");
  }

  /* ── the article conversation (design §06) ────────────────────────────
     Chat is a consumer of the core, exactly as §06 and §01 place it: no storage, no second writer,
     no second serialiser, no offline anything. Every turn is a server round trip; reading the
     article never is. */

  /** What is being discussed, which is also the transcript's key. */
  const subjectKey = external ? `ref:${external.word}` : openId ? `lex:${openId}` : null;

  useEffect(() => {
    setThread(subjectKey ? threads.current.get(subjectKey) ?? [] : []);
    setAskFocus(null);
    // A fold is opened per article, so what it had loaded does not belong to the next one.
    setReference(null);
  }, [subjectKey]);

  const rememberTurns = useCallback((next: ChatTurn[]) => {
    if (subjectKey) threads.current.set(subjectKey, next);
    setThread(next);
  }, [subjectKey]);

  const askSlot = useMemo<AskSlot | null>(() => {
    // Absent while a proposal is live: its added records carry `articleFromDraft`'s placeholder
    // ids, which are deliberately not record ids, so there would be nothing an anchor could name.
    if (!article || mode !== "read" || proposal) return null;
    return { focus: setAskFocus, focused: askFocus?.id ?? null };
  }, [article, mode, proposal, askFocus]);

  /**
   * One turn. The request is assembled *here*, on every turn, rather than held — so after a
   * proposal is saved the model sees the applied article rather than the one it was asked about.
   *
   * The document is serialised on this device because `yaml.ts` is the only place the projection is
   * understood; a server-side serialiser would be a second implementation of it (§06 REVISED).
   */
  const askAbout = useCallback((turns: ChatTurn[]) => {
    const deviceId = repository.snapshot().deviceId;
    let subject: ChatSubject;
    let neighbours: ChatNeighbour[] = [];
    if (article) {
      subject = {
        kind: "article",
        lexemeId: article.lexeme.id,
        // What the proposal would save, when one is live — not `diff.shown`, which carries removed
        // records back for the reader's sake and would show the model records it just took away.
        document: proposal ? yamlForDraft(proposal.after) : yamlFor(article),
        focus: askFocus ? `${askFocus.kind}:${askFocus.id}` : null
      };
      // Chosen from the replica before the request leaves, offline and for free — which is most of
      // why there is no tool loop. Topic-mates, capped at twenty, headword and gloss only.
      if (snapshot) {
        const mates = new Set(article.lexeme.topicIds);
        neighbours = lexemesIn(snapshot, article.lexeme.language)
          .filter((lexeme) => lexeme.id !== article.lexeme.id
            && lexeme.topicIds.some((id) => mates.has(id)))
          .slice(0, 20)
          .map((lexeme) => ({ headword: lexeme.headword, shortGloss: shortGlossOf(snapshot, lexeme) }));
      }
    } else if (external) {
      // They do not hold this word, so there is no replica of it to send and nothing to propose.
      subject = { kind: "reference", headword: external.word, language: external.language };
    } else {
      return Promise.reject(new Error("There is nothing to ask about."));
    }
    const open = external ?? reference;
    return backendSession.chat(deviceId, {
      subject,
      reference: open ? referenceTextOf(open) : null,
      referenceSources: open ? open.sections.map((section) => section.name) : [],
      neighbours,
      turns
    });
  }, [article, askFocus, snapshot, external, reference, proposal]);

  /** Pressing *Add to my words* on a reference conversation: the existing capture, one field filled. */
  const captureFromChat = useCallback((capture: ChatCapture) => {
    if (!external) return;
    addFromDictionary({
      headword: capture.headword || external.word,
      language: external.language,
      reference: referenceTextOf(external),
      referenceMode: capture.referenceMode,
      note: capture.note || null,
      sources: external.sections.map((section) => section.name)
    });
  }, [external, addFromDictionary]);

  /**
   * Pressing *Review* on a proposal card: apply the operations to a draft and show the article with
   * the change marks. Nothing is written — that needs a second press.
   *
   * The operations are refused here rather than on the server, because refusing them needs the
   * document's *meaning* — whether an id exists, whether a field may be set on that kind of record —
   * and `yaml.ts` is the only place the projection is understood.
   */
  const reviewProposal = useCallback((ops: EditOp[], summary: string, modelId: string) => {
    if (!article || !snapshot) return;
    /* A second turn builds on what the first one proposed, not on what is being *shown*.
       `diff.shown` carries removed records back so they can be drawn struck through, so applying
       to it would quietly resurrect everything the proposal takes away. The comparison stays
       against the stored document, so the bar counts everything still outstanding and Undo has one
       thing to put back however many turns it took to get here. */
    const origin = proposal ? proposal.before : draftFor(article);
    const base = proposal ? proposal.after : origin;
    try {
      const applied = applyOps(base, ops, {
        modelId,
        glossLang: article.glossLangs[0] ?? null,
        mintId: newId
      });
      setProposal({
        before: origin, after: applied.draft, diff: diffDrafts(origin, applied.draft),
        minted: new Set([...(proposal?.minted ?? []), ...applied.minted]),
        summary
      });
      /* No scroll to the top: `ReviewBar` brings the *first change* into view instead, which is
         what design §6.2 asked for and what makes an edit to the third sense of a long entry
         something you can see rather than something you have to go looking for. */
    } catch (error) {
      notify(error instanceof EditRefused ? error.message
        : "That proposal could not be applied, so nothing was changed.");
    }
  }, [article, snapshot, proposal, notify]);

  const saveProposal = useCallback(async () => {
    if (!proposal || !openId) return;
    const previous = yamlForDraft(proposal.before);
    // The same call a hand-edited document makes: same validation, same id diffing, same revision
    // check. A chat-driven edit is indistinguishable downstream from a typed one.
    const id = await applyYaml(yamlForDraft(proposal.after), proposal.minted);
    if (!id) {
      // A stale entry is refused, never merged. The proposal goes with it: it was written against a
      // document that has moved.
      setProposal(null);
      notify("That entry changed elsewhere, so the proposal was dropped.");
      return;
    }
    undoable.current = { id, text: previous };
    // A sense the proposal added is enriched on the server, and filled in on the page.
    const known = new Set(proposal.before.senses.map((sense) => sense.id));
    if (proposal.after.senses.some((sense) => !known.has(sense.id))) setViewChoice("page");
    setProposal(null);
    notify("Saved to the server", { label: "Undo", run: () => void undoProposal() });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proposal, openId, notify]);

  /**
   * Undo is the previous document, saved again.
   *
   * It needs no special support: `saveArticle` tombstones what a document stops mentioning rather
   * than erasing it, and `stamp` sets `deleted: false`, so naming a tombstoned id brings the record
   * back with its id intact. An ordinary online write like everything else.
   */
  const undoProposal = useCallback(async () => {
    const held = undoable.current;
    if (!held) return;
    undoable.current = null;
    const id = await applyYaml(held.text);
    notify(id ? "Put back" : "That could not be undone.");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notify]);

  /**
   * Asking about a proposal the Add view has not saved yet.
   *
   * The document comes from the editor rather than from the graph — it is not stored, so there is
   * nothing to read it out of — and the neighbours are left empty: a word being added has no topics
   * chosen yet, and guessing at them would be conditioning on nothing.
   */
  const askAboutDraft = useCallback((document: string, turns: ChatTurn[]) => {
    const deviceId = repository.snapshot().deviceId;
    return backendSession.chat(deviceId, {
      subject: { kind: "article", lexemeId: "", document, focus: null },
      turns
    });
  }, []);

  /**
   * A repeat capture, folded into the word you already have (§05, §8.3).
   *
   * The decision was taken on the duplicate panel, so the turn is *sent* rather than typed into the
   * composer — following `AddView`'s own precedent for a seeded composition. Nothing about this
   * reaches the prompt as a special mode: it is one ordinary question producing one ordinary
   * proposal, reviewed and saved like any other.
   */
  const foldIn = useCallback((lexemeId: string, foldable: CaptureFoldable) => {
    const quoted = foldable.sentences.map((sentence) => `«${sentence.text}»`).join(" ");
    const note = foldable.note ? ` ${foldable.note}` : "";
    closeCapture();
    openLexeme(lexemeId);
    setSeededTurn(quoted
      ? `Fold this in: ${quoted}.${note}`
      : `I met this word again.${note || " Is there anything worth adding?"}`);
  }, [closeCapture, openLexeme]);

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

  /**
   * Delete a loop: its row, its words and its track.
   *
   * A route rather than `repository.delete`, because the track is the server's to remove and nothing
   * else would ever remove it. So it is a write followed by a pull, the shape `replacePicture` has,
   * and the device forgets its own copy of the bytes afterwards — the reference is gone, so nothing
   * would ever ask for them again.
   */
  async function removeLoop(loopId: string) {
    const loop = snapshot?.loops.find((row) => row.id === loopId) ?? null;
    try {
      await backendSession.deleteLoop(loopId, snapshot?.deviceId ?? "");
    } catch (error) {
      // Online-only, and nothing changed locally: the loop is still there and still plays.
      notify(error instanceof Error ? error.message : "That loop could not be deleted.");
      return;
    }
    if (loopPlayer.nowPlaying()?.loop.id === loopId) loopPlayer.stop();
    if (loop?.audioRef) await loopPlayer.forget(loop.audioRef);
    await syncEngine.syncNow();
    setSnapshot(repository.snapshot());
    notify("Deleted everywhere — the track is gone too");
  }

  /**
   * Out of the Inbox and into its topics — one word from its article, or the whole tab at once.
   *
   * The word stays open afterwards rather than closing the way a delete does: you have just read it,
   * which is what filing it means, and the only thing that changed is where it is filed.
   */
  async function fileWords(ids: string[]) {
    let moved = 0;
    try {
      moved = await repository.fileWords(ids);
    } catch (error) {
      // Nothing was changed locally, so the Inbox is exactly as it was.
      notify(error instanceof Error ? error.message : "Those words could not be filed.");
      return;
    }
    const next = repository.snapshot();
    setSnapshot(next);
    if (!moved) return;
    // The rail drops the Inbox tab once it is empty, so standing on it would leave you looking at a
    // list with no way back to itself. Only the tab moves; an open word stays open.
    if (topic === "inbox" && language && !inboxCount(next, language)) setTopic("all");
    notify(moved === 1 ? "Filed — it is in its topics now" : `Filed ${moved} words`);
  }

  async function signOut() {
    syncEngine.stop();
    jobStream.stop();
    // The next session may be a different account on a different server, so nothing an external
    // source answered under this one survives into it.
    forgetCachedLookups();
    await clearPictures();
    await forgetPronunciations();
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
  /* `asking` joins this for the same reason the other two are here: a surface that owns the height
     and scrolls itself must not sit inside a region that also scrolls. */
  const composing = Boolean(addTab) || Boolean(article && mode === "edit") || asking || loops;
  const inbox = snapshot && language ? inboxCount(snapshot, language) : 0;
  const currentTopic = topics.find((option) => option.id === topic);
  const topicLabel = topic === "all" ? "All words" : topic === "inbox" ? "Inbox" : currentTopic?.name ?? "Topic";
  const topicIcon = topic === "all" ? "📖" : topic === "inbox" ? "📥" : currentTopic?.icon ?? "📌";

  return <>
    <div className="viewport" onClick={() => { setLangMenu(false); setScopeMenu(false); setArticleMenu(false); }}>
      {/* Reading a word on a phone or a tablet does not need the topic rail beside it. */}
      {/* Reading a word on a phone or a tablet does not need the topic rail beside it. The loops
          surface is *not* given `article-open`: it keeps the rail wherever there is room for it,
          and drops it only on a phone, where an article drops it too. */}
      <div className={`app${(article || external) && !addTab ? " article-open" : ""}${loops ? " loops-open" : ""}`}>
        <div className="brand"><span className="mark">A.</span></div>

        <header className="topbar">
          <div className={`search ${query.trim() ? "searching" : ""}`}>
            <SearchIcon />
            <input
              ref={search} type="search" placeholder="Search your words…" autoComplete="off" spellCheck={false}
              value={query}
              // Typing is asking for the list, so it leaves the loops surface. Whatever is playing
              // keeps playing — that is what the bar and the chip are for.
              onChange={(event) => { setQuery(event.target.value); setOpenId(null); setExternal(null); setLoops(false); }}
              // ⏎ is the only thing that ever reaches an online dictionary. Everything else here
              // answers off this device or off your own server.
              onKeyDown={(event) => { if (event.key === "Enter") { setLoops(false); searchOnline(); } }}
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

          {/* The toolbar stays up while you compose, so this button means two things and only one
              of them is "start something new": pressing it mid-composition returns you to the
              capture box with what you typed still in it, which is how you correct the word after
              reading the article it produced and process it again. */}
          <button
            className="tb-btn primary"
            onClick={() => { if (addTab) setAddTab("capture"); else openCapture(null); }}
          >
            <PlusIcon /><span className="wide-only">Add</span>
          </button>

          {/* Wide windows only: on a phone this is the bar at the foot instead, which is where a
              player belongs on a device held in one hand. `styles.css` picks which. */}
          {snapshot && language && <LoopBar
            graph={snapshot} language={language} chip
            onOpen={openLoops} onMake={() => { openLoops(); setMakingLoop(true); }}
          />}

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
        <main className={`main ${composing ? "composing" : ""}${carding && !composing ? " cards-on" : ""}`} ref={main}>
          {loops && snapshot && language ? <LoopView
          graph={snapshot} language={language} onMake={() => setMakingLoop(true)}
          onClose={() => setLoops(false)}
          onDelete={removeLoop}
        /> : addTab ? <AddView
            // A new composition is a fresh view, not a prop change: remounting is what makes "add
            // this word, then that one" start clean rather than editing the previous draft. The key
            // is the composition's own count rather than its headword, because keying on the word
            // meant two goes at the same word shared a draft — and because switching tabs must not
            // change it, so the text you typed survives reading the article it produced.
            key={composition}
            tab={addTab} onTab={setAddTab} graph={snapshot} problems={problems} busy={saving}
            seed={addSeed} captureHealth={captureHealth}
            onClose={closeCapture}
            onCreate={(draft) => void createFromYaml(draft)}
            onCapture={captureText}
            onOpenLexeme={(id) => { closeCapture(); openLexeme(id); }}
            onFoldIn={foldIn}
            onChat={captureHealth?.available === false ? undefined : askAboutDraft}
            offline={syncStatus.state === "offline"}
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
          </Suspense> : <div className={`pane ${asking ? "ask-only" : ""}`}>
            {external && <div className="art-bar">
              <button className="icon-btn" aria-label="Back to the list" onClick={() => setExternal(null)}><BackIcon /></button>
              <span className="label">Other dictionaries</span>
              <span className="spacer" />
            </div>}
            {/* Live for as long as a proposal is. Nothing is written until Save changes, and
                Discard leaves the stored entry untouched because nothing ever reached it. */}
            {proposal && <ReviewBar
              count={proposal.diff.count}
              order={proposal.diff.order}
              saving={saving}
              scroller={main}
              onDiscard={() => setProposal(null)}
              onSave={() => void saveProposal()}
            />}
            {article && <div className={`art-bar${carding ? " carding" : ""}`}>
              <button className="icon-btn" aria-label="Back to the list" onClick={() => { setOpenId(null); setProposal(null); }}><BackIcon /></button>
              <span className="label art-where">{topicLabel}</span>
              {/* On a phone in Cards the word is the toolbar's title, which is what gives the card below
                  its room; wider screens set it under the toolbar instead, and hide this. */}
              {carding && <div className="art-title">
                <span className="art-title-word" data-length={article.lexeme.headword.length > 24 ? "long" : article.lexeme.headword.length > 14 ? "mid" : "short"}>
                  {article.lexeme.headword}
                </span>
                <HeadwordListen lexeme={article.lexeme} onNotify={notify} />
              </div>}
              <span className="spacer" />
              <div className="seg art-views">
                <button className={reading && view === "page" ? "on" : ""} onClick={() => { setViewChoice("page"); setMode("read"); }}>Page</button>
                <button
                  className={reading && view === "cards" ? "on" : ""}
                  // Cards has nowhere to draw a proposal's marks, so it waits until one is saved or
                  // discarded — and re-flows as results land, so it waits for a word to fill in too.
                  disabled={Boolean(proposal) || enriching}
                  title={proposal ? "Save or discard the proposed changes first"
                    : enriching ? "Cards open when pictures and clips are ready" : undefined}
                  onClick={() => { setViewChoice("cards"); setMode("read"); }}
                >Cards</button>
                <button className={mode !== "read" ? "on" : ""} onClick={() => setMode("yaml")}>YAML</button>
              </div>
              {/* Editing is a thing you do to the document, so its button appears where the document is.
                  Hand-editing drops a live proposal: two sets of unsaved changes over one entry is not a
                  state worth having. */}
              {mode === "yaml" && <button className="icon-btn" aria-label="Edit as YAML" title="Edit as YAML" onClick={() => { setProposal(null); setMode("edit"); }}><PencilIcon /></button>}
              {/* Reading the word is what takes it out of the Inbox, so the button is here, where you
                  have just read it — and in the bar rather than on the page, because Cards has no
                  masthead and the Inbox is exactly where an unread word is opened. */}
              {article.lexeme.status === "inbox" && <button
                className="icon-btn art-file" aria-label="File it" title="File it — out of the Inbox"
                onClick={() => void fileWords([article.lexeme.id])}
              ><FileIcon /></button>}
              <button className="icon-btn art-delete" aria-label="Delete" title="Delete" onClick={() => void removeLexeme(article.lexeme.id)}><TrashIcon /></button>
              {/* A phone has room for one control beside the word, so the views and Delete fold into this. */}
              <div className="art-more" onClick={(event) => event.stopPropagation()}>
                <button className="icon-btn" aria-label="Article menu" aria-haspopup="menu" aria-expanded={articleMenu}
                  onClick={() => setArticleMenu((open) => !open)}><MoreIcon /></button>
                {articleMenu && <div className="menu open" role="menu">
                  {([["page", "Page"], ["cards", "Cards"], ["yaml", "YAML"]] as const).map(([id, name]) => {
                    const on = id === "yaml" ? mode !== "read" : reading && view === id;
                    return <button key={id} role="menuitemradio" aria-checked={on} className={on ? "on" : ""}
                      disabled={id === "cards" && (Boolean(proposal) || enriching)}
                      onClick={() => {
                        setArticleMenu(false);
                        if (id === "yaml") setMode("yaml");
                        else { setViewChoice(id); setMode("read"); }
                      }}>{name}</button>;
                  })}
                  <div className="menu-sep" />
                  {article.lexeme.status === "inbox" && <button role="menuitem"
                    onClick={() => { setArticleMenu(false); void fileWords([article.lexeme.id]); }}
                  >File it</button>}
                  <button role="menuitem" className="danger" onClick={() => { setArticleMenu(false); void removeLexeme(article.lexeme.id); }}>Delete this word</button>
                </div>}
              </div>
            </div>}
            {article && reading && !proposal && <ProgressStrip
              job={enrichJob}
              onRetry={() => retryEnrichment(article.lexeme.id)}
              onDismiss={() => dismissEnrichment(article.lexeme.id)}
            />}

            {!snapshot ? <p className="empty">Opening your vocabulary…</p>
              // An external entry replaces the list the way one of your own does, and reads in the
              // same column: a word being looked up is the work, wherever it came from.
              : external ? <ExternalArticle entry={external} busy={saving} onAdd={addFromDictionary} />
              : !article ? <LexemeList
                  rows={rows} languageName={active.name} topic={topic}
                  topicLabel={topicLabel} topicIcon={topicIcon} query={query} sort={sort}
                  onSort={setSort} onOpen={openLexeme} onFileAll={(ids) => void fileWords(ids)}
                  external={externalSearch}
                  working={(id) => isEnriching(jobsStatus, id)}
                />
              : mode === "read" ? <LexemeArticle
                  article={article} view={view} onNotify={notify} pictures={pictures} clips={clips}
                  marks={markSlot} ask={askSlot} onReference={setReference}
                />
              // Editing is a composer above, so only reading and the read-only projection get here.
              : <Suspense fallback={<p className="empty">Loading the editor…</p>}>
                  {/* The proposed document when one is live, and deliberately *unmarked*: someone
                      who opens this wants to read or edit the text, and gutter decorations here
                      would answer a question the Article tab already answered. */}
                  <YamlView
                    name={article.lexeme.headword}
                    yaml={proposal ? yamlForDraft(proposal.after) : yamlFor(article)}
                  />
                </Suspense>}

            {/* The dock, pinned to the bottom of this pane at every width. Present on a stored
                article and on an external entry; never inside AddView, which replaces the pane
                rather than sharing it. Hidden entirely when the server has no model — the capture
                surface already knows how to say that. */}
            {/* Not in Cards: a conversation edits the whole entry, and needs the whole entry in view. */}
            {snapshot && (external || (article && view === "page")) && mode === "read" && captureHealth?.available !== false
              && <AskDock
                key={subjectKey ?? "none"}
                headword={article ? article.lexeme.headword : external!.word}
                emoji={article ? article.lexeme.emoji : null}
                turns={thread}
                onTurns={rememberTurns}
                ask={askAbout}
                offline={syncStatus.state === "offline"}
                focus={askFocus ? { label: askFocus.label } : null}
                onClearFocus={() => setAskFocus(null)}
                onPropose={article
                  ? (found, modelId) => reviewProposal(found.ops as EditOp[], found.summary, modelId)
                  : undefined}
                onCapture={external ? captureFromChat : undefined}
                seeded={seededTurn}
                onSeedUsed={() => setSeededTurn(null)}
                onDetent={setAskDetent}
              />}
          </div>}
        </main>

        {/* A row of `.app`, and drawn over the list and nowhere else: the article column already
            carries the view segments, the delete control, the progress strip and the ask dock, and
            §2.13 forbids a second one there. Narrow windows only — a wide one has the chip in the
            top bar instead, and `styles.css` is what picks. */}
        {snapshot && language && !article && !external && !addTab && !loops && <LoopBar
          graph={snapshot} language={language} chip={false}
          onOpen={openLoops} onMake={() => { openLoops(); setMakingLoop(true); }}
        />}
      </div>
    </div>

    {makingLoop && snapshot && language && <LoopDialog
      graph={snapshot} query={{ language, topic, query, sort }} deviceId={snapshot.deviceId}
      onClose={() => setMakingLoop(false)}
      onMade={() => notify("Making your loop — it takes a few minutes")}
      onNotify={notify}
    />}

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
    {editingImage && article && <ImageDialog
      // The live row rather than the one the dialog opened on, so a new brief shows when it lands.
      prompt={article.senses.find((entry) => entry.sense.id === editingImage.senseId)?.images[0]
        ?? editingImage.prompt}
      briefing={isOpen(jobFor(jobsStatus, "image.rebrief", article.lexeme.id))}
      onRebrief={() => askForPicture("image.rebrief", { kind: "lexeme", id: article.lexeme.id })}
      headword={article.lexeme.headword}
      styles={imageStyles}
      onClose={() => setEditingImage(null)}
      onAttach={(file) => { void replacePicture(editingImage.senseId, () =>
        backendSession.attachImage(editingImage.senseId, snapshot?.deviceId ?? "", file)); }}
      onRemove={() => {
        const held = editingImage.prompt;
        if (held) void replacePicture(editingImage.senseId, () =>
          backendSession.removeImage(held.id, snapshot?.deviceId ?? ""));
      }}
      onDraw={(overrides) => {
        const held = editingImage.prompt;
        if (!held) return;
        // The dialog closes and the picture says it is redrawing while the server draws it.
        askForPicture("image.redraw", { kind: "imagePrompt", id: held.id }, overrides);
      }}
    />}
    <div className={`toast ${toast ? "show" : ""}`}>
      {toast}
      {toastAction && <button className="toast-action" onClick={() => {
        const run = toastAction.run;
        setToast(""); setToastAction(null);
        run();
      }}>{toastAction.label}</button>}
    </div>
  </>;
}
