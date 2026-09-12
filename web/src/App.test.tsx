import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EditorView } from "@codemirror/view";
import App from "./App";
import { AcervoApiError, backendSession, SCHEMA_VERSION, type CaptureHealth } from "./api";
import { hydrateGlosses, lookup as lookupDictionaries, searchDictionaries } from "./dictionaries";
import { INSTALLED_EVENT, UPDATE_EVENT } from "./pwa";
import { repository } from "./repository";
import { TEST_OWNER, testGraph } from "./testGraph";

vi.mock("virtual:pwa-register", () => ({ registerSW: vi.fn() }));

/* The dictionary transports are the network and the device store; the tests below are about what
   the interface does with their answers, so they are spied rather than reimplemented. Everything
   else in the module — the merging, the ranking, the resolution order — stays real. */
vi.mock("./dictionaries", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./dictionaries")>();
  return {
    ...actual,
    searchDictionaries: vi.fn(actual.searchDictionaries),
    hydrateGlosses: vi.fn(actual.hydrateGlosses),
    lookup: vi.fn(actual.lookup)
  };
});

/* The mocks above are module-level `vi.fn`s, so their call history and any implementation a test
   installs outlive `restoreAllMocks`. Each test starts from the real behaviour again. */
const realDictionaries = await vi.importActual<typeof import("./dictionaries")>("./dictionaries");

const SESSION = {
  baseUrl: "https://acervo.example.com", email: "learner@account.example.com",
  token: "token", userId: TEST_OWNER
};

const DATASET = "dataset00000001";

/** The server numbers every row it hands back; the cursor is the highest of them. */
function numberedGraph() {
  const graph = testGraph();
  let revision = 0;
  (Object.keys(graph) as (keyof typeof graph)[]).forEach((kind) => {
    (graph[kind] as { revision: number }[]).forEach((record) => { record.revision = ++revision; });
  });
  return { graph, cursor: revision };
}

/** A server that can build entries, which is the ordinary case every other test assumes. */
function serverHealth(capture: Partial<CaptureHealth> = {}) {
  vi.spyOn(backendSession, "health").mockResolvedValue({
    name: "Acervo", version: "0.1.0", build: "1", schemaVersion: SCHEMA_VERSION,
    capture: { available: true, provider: "gemini", model: "gemini-3.1-flash-lite", reason: null, ...capture },
  });
}

function signedIn() {
  const { graph, cursor } = numberedGraph();
  serverHealth();
  vi.spyOn(backendSession, "restore").mockResolvedValue(SESSION);
  vi.spyOn(backendSession, "current").mockReturnValue(SESSION);
  vi.spyOn(backendSession, "refresh").mockResolvedValue(SESSION);
  vi.spyOn(backendSession, "pullGraph").mockResolvedValue({
    schemaVersion: SCHEMA_VERSION, datasetId: DATASET, cursor,
    serverTime: "2026-08-29T12:00:00.000Z", changes: graph
  });
}

/* One counter for the whole file, never reset. A revision is only ever allocated upward, so a write
   always beats whatever the fixture pulled — and a second write in the same test always beats the
   first. Resetting it per test reintroduced exactly the collision it exists to avoid. */
let allocated = 1000;

/** A server that accepts every write and numbers the rows it hands back, as the real one does. */
function acceptWrites() {
  /* One ever-increasing counter per owner, which is what the server actually keeps — deliberately
     not derived from the cursor. A pull can move the cursor back to what the fixture hands out, and
     a write numbered from it would then collide with a revision already stored, so the merge would
     drop it as stale. Seeded above anything the fixture pulls, so a write always wins. */
  vi.spyOn(backendSession, "pushGraph").mockImplementation(async (_device, changes) => {
    const records = Object.fromEntries(Object.entries(changes).map(([kind, list]) =>
      [kind, (list ?? []).map((record) => ({ ...record, revision: ++allocated }))]));
    // The cursor is the highest revision allocated, exactly as the server reports it.
    return {
      schemaVersion: SCHEMA_VERSION, datasetId: DATASET, cursor: allocated,
      serverTime: "2026-08-29T12:00:01.000Z", records
    };
  });
}

/**
 * The editing surface is CodeMirror, so a test drives the real editor rather than a textarea:
 * `findFromDOM` hands back the live view and a dispatch is exactly what typing does.
 */
function editorView(): EditorView {
  const dom = document.querySelector(".code-scroll .cm-editor") as HTMLElement;
  const view = EditorView.findFromDOM(dom);
  if (!view) throw new Error("no editor is mounted");
  return view;
}

const editorText = () => editorView().state.doc.toString();

function replaceInEditor(find: string, replacement: string) {
  const view = editorView();
  act(() => {
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: view.state.doc.toString().replace(find, replacement) } });
  });
}

/** CodeMirror is loaded on demand, so a mount that follows a tab/mode switch takes an extra tick. */
async function waitForEditor() {
  await waitFor(() => expect(document.querySelector(".cm-editor")).not.toBeNull());
}

/**
 * A capture the server answered with a full proposal: one sense, the learner's own sentence kept as
 * an attestation, and the example that draws on it naming that attestation.
 */
function mockGarfioCapture() {
  vi.spyOn(backendSession, "captureText").mockResolvedValue({
    resolution: {
      language: "es", headword: "el garfio", lemma: "garfio", pos: "noun",
      sentences: [{ text: "El disfraz de pirata viene con un garfio.", translation: null }],
      note: null, consumedLines: 1, consumedText: null
    },
    duplicates: [],
    applied: null,
    draft: {
      id: null, language: "es", headword: "el garfio", lemma: "garfio", reading: null,
      ipa: null, pos: "noun", gender: "masculine", register: "neutral", dialect: null, emoji: "🪝",
      topics: ["Travel"], status: "inbox", shortGloss: "hook", notes: [],
      senses: [{
        id: "sense0000000091", order: 0, definition: "Gancho de metal curvo y puntiagudo.",
        definitionLang: "es", glosses: [{ lang: "en", terms: ["hook", "grappling hook"] }],
        domain: null, images: [],
        examples: [{
          id: "example00000091", text: "El disfraz de pirata viene con un garfio.", textLang: "es",
          translation: "The pirate costume comes with a hook.", translationLang: "en",
          // The learner's own sentence, linked to the attestation created by the same save.
          origin: "attestation", sourceAttestationId: "attest000000091", modelId: null,
          videoRef: null, videoTitle: null, videoChannel: null, videoStart: null, videoEnd: null,
          clipRef: null, imageRef: null, audioRef: null,
          note: null, matchedForm: "un garfio", matchedTranslationForm: "hook",
          approved: false
        }]
      }],
      attestations: [{
        id: "attest000000091", text: "El disfraz de pirata viene con un garfio.", translation: null,
        sourceUrl: null, sourceTitle: null, sourceKind: "unknown",
        capturedAt: "2026-08-29T12:00:00.000Z"
      }],
      images: []
    }
  });
}

/** Renders the app and waits for the pulled replica to reach the word list. */
async function openList() {
  render(<App />);
  await screen.findByRole("heading", { name: /All words/ });
  await screen.findByRole("button", { name: /picar/ });
}

describe("Acervo application", () => {
  beforeEach(async () => {
    delete window.webkit;
    localStorage.clear();
    sessionStorage.clear();
    await repository.clear();
    vi.mocked(searchDictionaries).mockReset().mockImplementation(realDictionaries.searchDictionaries);
    vi.mocked(hydrateGlosses).mockReset().mockImplementation(realDictionaries.hydrateGlosses);
    vi.mocked(lookupDictionaries).mockReset().mockImplementation(realDictionaries.lookup);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ data: null }) }));
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("uses the web page origin when signing in from a browser", async () => {
    vi.spyOn(backendSession, "restore").mockResolvedValue(null);
    const login = vi.spyOn(backendSession, "login").mockResolvedValue({
      baseUrl: window.location.origin, email: "learner@account.example.com", token: "token", userId: TEST_OWNER
    });
    render(<App />);
    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
    expect(screen.queryByLabelText("Server")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "learner@account.example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(login).toHaveBeenCalledWith(
      window.location.origin, "learner@account.example.com", "secret-password"
    ));
  });

  it("keeps explicit server selection in the native macOS host", async () => {
    window.webkit = { messageHandlers: { acervo: { postMessage: vi.fn() } } };
    vi.spyOn(backendSession, "restore").mockResolvedValue(null);
    render(<App />);
    expect(await screen.findByLabelText("Server")).toBeInTheDocument();
  });

  it("reports why a sign in failed without leaving the form", async () => {
    vi.spyOn(backendSession, "restore").mockResolvedValue(null);
    vi.spyOn(backendSession, "login")
      .mockRejectedValue(new AcervoApiError("The email or password is incorrect.", 401, "invalid_credentials"));
    render(<App />);
    fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "learner@account.example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("The email or password is incorrect.")).toBeInTheDocument();
  });

  it("offers Android installation before sign in", async () => {
    vi.stubGlobal("navigator", {
      userAgent: "Mozilla/5.0 (Linux; Android 15)", platform: "Linux armv8l", maxTouchPoints: 5
    });
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false })));
    vi.spyOn(backendSession, "restore").mockResolvedValue(null);
    render(<App />);

    expect(await screen.findByRole("heading", { name: "Install the app" })).toBeInTheDocument();
    expect(screen.getByText(/offers Install app when Acervo is not installed yet/i)).toBeInTheDocument();
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Continue in browser" }));
    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
  });

  it("stays on the install screen once installed, rather than falling through to signing in", async () => {
    // Landing on the browser's sign-in form the moment the app is installed reads as though the
    // installation went nowhere, and signs you in somewhere other than the app you just added.
    vi.stubGlobal("navigator", {
      userAgent: "Mozilla/5.0 (Linux; Android 15)", platform: "Linux armv8l", maxTouchPoints: 5
    });
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false })));
    vi.spyOn(backendSession, "restore").mockResolvedValue(null);
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Install the app" })).toBeInTheDocument();

    act(() => { window.dispatchEvent(new CustomEvent(INSTALLED_EVENT)); });

    expect(await screen.findByRole("heading", { name: "Acervo is installed" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
    // Continuing in the browser stays available, as the deliberate choice it already was.
    fireEvent.click(screen.getByRole("button", { name: "Continue in browser" }));
    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
  });

  it("shows the Safari home-screen steps on iPhone and iPad", async () => {
    vi.stubGlobal("navigator", {
      userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)",
      platform: "iPhone", maxTouchPoints: 5
    });
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false })));
    vi.spyOn(backendSession, "restore").mockResolvedValue(null);
    render(<App />);

    expect(await screen.findByText("Open this page in ", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Share")).toBeInTheDocument();
    expect(screen.getByText("Add to Home Screen")).toBeInTheDocument();
  });

  it("lists the owner's words pulled from the server", async () => {
    signedIn();
    await openList();
    expect(screen.getByRole("button", { name: /picar/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /la balsa/ })).toBeInTheDocument();
    // The inbox word is filed separately, not among the filed collections.
    expect(screen.queryByRole("button", { name: /espolvorear/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Inbox/ })).toBeInTheDocument();
  });

  it("still opens on the stored replica when the server is unreachable", async () => {
    signedIn();
    await openList();
    vi.spyOn(backendSession, "pullGraph")
      .mockRejectedValue(new AcervoApiError("The Acervo server could not be reached. Local vocabulary remains available.", 0, "offline"));
    render(<App />);
    expect((await screen.findAllByRole("button", { name: /Offline/ })).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /picar/ }).length).toBeGreaterThan(0);
  });

  it("narrows the list by topic and by search", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /Travel/ }));
    expect(await screen.findByRole("heading", { name: /Travel/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /picar/ })).not.toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("Search your words…"), { target: { value: "itch" } });
    expect(await screen.findByRole("heading", { name: /Search/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /picar/ })).toBeInTheDocument();
  });

  /* ── external dictionaries ─────────────────────────────────────────
     Your words answer first and always; anything else is below a rule and says whose it is. */

  const DEVICE_HIT = {
    word: "picadura", dictionaryId: "kaikki-es-es", name: "Wiktionary (es→es)",
    origin: "device" as const, gloss: "mordedura de un insecto"
  };
  const ONLINE_HIT = {
    word: "picar", dictionaryId: "freedictionaryapi", name: "Free Dictionary API",
    origin: "online" as const, gloss: "to itch"
  };

  /** Answers each tier separately, the way the real transports do. */
  function dictionariesAnswer(byTier: Partial<Record<"device" | "server" | "online", unknown[]>>) {
    vi.mocked(hydrateGlosses).mockImplementation(async (rows) => rows);
    vi.mocked(searchDictionaries).mockImplementation(async (_word, { tiers }) => {
      const hits = (byTier[tiers[0] as "device"] ?? []) as never[];
      // `asked` is what stops the section claiming a word is missing when nothing was switched on.
      return { hits, asked: 1, failed: [] };
    });
  }

  it("searches your words first and the dictionaries below a rule", async () => {
    signedIn();
    dictionariesAnswer({ device: [DEVICE_HIT] });
    await openList();
    fireEvent.change(screen.getByPlaceholderText("Search your words…"), { target: { value: "pica" } });

    // Yours answers immediately; the dictionaries follow, under their own heading.
    expect(await screen.findByRole("button", { name: /picar/ })).toBeInTheDocument();
    expect(await screen.findByText("Other dictionaries")).toBeInTheDocument();
    const external = await screen.findByRole("button", { name: /picadura/ });
    expect(within(external).getByText("mordedura de un insecto")).toBeInTheDocument();
    expect(within(external).getByText("Wiktionary (es→es)")).toBeInTheDocument();
    // No study statistics: nothing here is being studied.
    expect(external.querySelector(".strength")).toBeNull();
  });

  it("never asks an online source until ⏎ is pressed", async () => {
    signedIn();
    dictionariesAnswer({ device: [DEVICE_HIT], online: [ONLINE_HIT] });
    await openList();
    const box = screen.getByPlaceholderText("Search your words…");
    fireEvent.change(box, { target: { value: "picar" } });
    await screen.findByText("Other dictionaries");

    await waitFor(() => expect(vi.mocked(searchDictionaries).mock.calls.length).toBeGreaterThan(0));
    expect(vi.mocked(searchDictionaries).mock.calls.every(([, options]) => options.tiers[0] !== "online"))
      .toBe(true);
    expect(screen.getByText(/Press ⏎ to look/)).toBeInTheDocument();

    fireEvent.keyDown(box, { key: "Enter" });
    await waitFor(() => expect(
      vi.mocked(searchDictionaries).mock.calls.some(([, options]) => options.tiers[0] === "online")
    ).toBe(true));
    expect(await screen.findByRole("button", { name: /Free Dictionary API/ })).toBeInTheDocument();
  });

  it("says the server is unreachable rather than pretending the list is complete", async () => {
    signedIn();
    vi.spyOn(backendSession, "pullGraph").mockRejectedValue(
      new AcervoApiError("offline", 0, "offline"));
    dictionariesAnswer({ device: [] });
    render(<App />);
    await screen.findByRole("heading", { name: /All words/ });
    fireEvent.change(screen.getByPlaceholderText("Search your words…"), { target: { value: "pic" } });
    expect(await screen.findByText(/only the dictionaries stored on this device/)).toBeInTheDocument();
  });

  it("opens a dictionary entry as an article, and offers to add it", async () => {
    signedIn();
    dictionariesAnswer({ device: [DEVICE_HIT] });
    vi.mocked(lookupDictionaries).mockResolvedValue([{
      dictionaryId: "kaikki-es-es", name: "Wiktionary (es→es)", origin: "device",
      attribution: "Wiktionary contributors. CC BY-SA 4.0.", licence: "CC BY-SA 4.0", sourceLang: "es",
      entry: { dictionaryId: "kaikki-es-es", word: "picadura", tier: "fields", articles: [{
        headword: "picadura", posLabel: "noun", ipa: "[pikaˈðuɾa]",
        senses: [{ definition: "Mordedura de un insecto." }]
      }] }
    }]);
    await openList();
    fireEvent.change(screen.getByPlaceholderText("Search your words…"), { target: { value: "pica" } });
    fireEvent.click(await screen.findByRole("button", { name: /picadura/ }));

    expect(await screen.findByRole("heading", { name: "picadura" })).toBeInTheDocument();
    expect(screen.getByText("Mordedura de un insecto.")).toBeInTheDocument();
    // Said where it came from, because CC BY-SA asks that of whoever displays it.
    expect(screen.getByText(/Wiktionary contributors/)).toBeInTheDocument();
    expect(screen.getByText("not in your words")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add to my words" })).toBeInTheDocument();
  });

  it("adds a dictionary entry through capture, carrying it as reference and not as your sentence", async () => {
    signedIn();
    dictionariesAnswer({ device: [DEVICE_HIT] });
    vi.mocked(lookupDictionaries).mockResolvedValue([{
      dictionaryId: "kaikki-es-es", name: "Wiktionary (es→es)", origin: "device",
      attribution: "Wiktionary contributors.", licence: "CC BY-SA 4.0", sourceLang: "es",
      entry: { dictionaryId: "kaikki-es-es", word: "picadura", tier: "fields", articles: [{
        headword: "picadura", posLabel: "noun",
        senses: [{ definition: "Mordedura de un insecto.",
                   examples: [{ text: "Una picadura de mosquito." }] }]
      }] }
    }]);
    const capture = vi.spyOn(backendSession, "captureText")
      .mockRejectedValue(new AcervoApiError("nothing to build", 502, "llm_unusable"));

    await openList();
    fireEvent.change(screen.getByPlaceholderText("Search your words…"), { target: { value: "pica" } });
    fireEvent.click(await screen.findByRole("button", { name: /picadura/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Add to my words" }));
    fireEvent.click(screen.getByRole("button", { name: "Build entry" }));

    await waitFor(() => expect(capture).toHaveBeenCalled());
    const [, request] = capture.mock.calls[0];
    expect(request.headword).toBe("picadura");
    expect(request.referenceMode).toBe("expand");
    expect(request.reference).toContain("Mordedura de un insecto.");
    // The dictionary's own example is reference, never the text a capture turns into attestations.
    expect(request.text).toBe("picadura");
    expect(request.text).not.toContain("mosquito");
  });

  it("looks the dictionary form up too, not only the headword you read", async () => {
    signedIn();
    vi.mocked(lookupDictionaries).mockResolvedValue([]);
    await openList();
    // `la balsa` is how a Spanish learner needs to see the word; `balsa` is how a dictionary is
    // keyed. Only the first was ever asked for, so every gendered noun missed.
    fireEvent.click(await screen.findByRole("button", { name: /la balsa/ }));
    const details = (await screen.findByText("Other dictionaries")).closest("details")!;
    details.open = true;
    fireEvent(details, new Event("toggle"));
    await waitFor(() => expect(lookupDictionaries)
      .toHaveBeenCalledWith("la balsa", "es", ["device", "server"], ["balsa"]));
    expect(await screen.findByText(/“la balsa” or “balsa”/)).toBeInTheDocument();
  });

  it("looks a word up in the dictionaries only when the fold is opened", async () => {
    signedIn();
    vi.mocked(lookupDictionaries).mockResolvedValue([]);
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));

    const fold = await screen.findByText("Other dictionaries");
    // Reading your own article must not quietly issue byte-range reads on the chance you are curious.
    expect(lookupDictionaries).not.toHaveBeenCalled();

    const details = fold.closest("details") as HTMLDetailsElement;
    details.open = true;
    fireEvent(details, new Event("toggle"));
    await waitFor(() => expect(lookupDictionaries)
      .toHaveBeenCalledWith("picar", "es", ["device", "server"], ["picar"]));
    expect(await screen.findByText(/No dictionary on this device or your server holds/))
      .toBeInTheDocument();
  });

  it("opens the article with its senses, lineage, schedule and provenance", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    expect(await screen.findByRole("heading", { name: "picar" })).toBeInTheDocument();
    expect(screen.getByText("/piˈkaɾ/")).toBeInTheDocument();
    expect(screen.getByText("Producir comezón.")).toBeInTheDocument();
    expect(screen.getByText("Cortar en trozos pequeños.")).toBeInTheDocument();
    expect(screen.getByText("unapproved")).toBeInTheDocument();
    expect(screen.getByText(/Comiendo en un mercado/)).toBeInTheDocument();
    expect(screen.getByText(/starts at 7:41/)).toBeInTheDocument();
    expect(screen.getByText("cuidado que esa salsa pica un monton")).toBeInTheDocument();
    expect(screen.getByText("18.3")).toBeInTheDocument();
  });

  it("projects the open record as YAML", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    fireEvent.click(await screen.findByRole("button", { name: "YAML" }));
    expect(await screen.findByText("picar.yaml")).toBeInTheDocument();
    expect(editorText()).toContain("id: lexemepicar0001");
  });

  it("reaches sync, sign-out and delete on the native host, without its update controls", async () => {
    // The Mac window owns the server address and the app's own updates. Everything about the
    // vocabulary is here — and hiding the whole pane to keep the update controls out left none of
    // it reachable on macOS at all.
    window.webkit = { messageHandlers: { acervo: { postMessage: vi.fn() } } };
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /Open settings/ }));

    const settings = within(await screen.findByRole("dialog", { name: /Settings/ }));
    expect(settings.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    // A second update control here would conflict with the one the host already owns.
    expect(settings.queryByText("Acervo is up to date")).not.toBeInTheDocument();
    expect(settings.queryByText(/Download Acervo for macOS/)).not.toBeInTheDocument();
    expect(settings.getByText("Updates and server address")).toBeInTheDocument();

    fireEvent.click(settings.getByRole("tab", { name: "Sync" }));
    expect(settings.getByRole("button", { name: "Sync now" })).toBeInTheDocument();
    fireEvent.click(settings.getByRole("tab", { name: "Data" }));
    expect(settings.getByRole("button", { name: /Delete all words/ })).toBeInTheDocument();
  });

  it("puts export, import and deletion together on the Data page", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));

    const settings = within(await screen.findByRole("dialog", { name: /Settings/ }));
    fireEvent.click(settings.getByRole("tab", { name: "Data" }));
    expect(settings.getByRole("button", { name: "Export…" })).toBeInTheDocument();
    expect(settings.getByRole("combobox")).toHaveValue("all");
    expect(settings.getByRole("heading", { name: "Import" })).toBeInTheDocument();
    expect(settings.getByRole("button", { name: /Delete all words/ })).toBeInTheDocument();
  });

  it("opens the Data page armed for deletion when the Mac menu asks", async () => {
    signedIn();
    await openList();
    window.acervo!.command("delete");

    const settings = within(await screen.findByRole("dialog", { name: /Settings/ }));
    // The menu item ends in an ellipsis, so it owes the reader a confirmation rather than a page.
    expect(settings.getByLabelText(/Type DELETE to confirm/)).toBeInTheDocument();
    expect(settings.getByRole("button", { name: "Export…" })).toBeInTheDocument();
  });

  it("adds a topic from settings and files it into the rail", async () => {
    signedIn();
    await openList();
    acceptWrites();
    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));

    const settings = within(await screen.findByRole("dialog", { name: /Settings/ }));
    fireEvent.click(settings.getByRole("tab", { name: "Topics" }));
    fireEvent.click(settings.getByRole("button", { name: "Add a topic…" }));
    fireEvent.change(settings.getByLabelText("Name"), { target: { value: "Slang" } });
    fireEvent.change(settings.getByLabelText("Icon"), { target: { value: "💬" } });
    fireEvent.click(settings.getByRole("button", { name: "Add topic" }));

    // Generated entries can only be filed under topics that exist, so this is what unblocks capture
    // on an account that was not seeded.
    expect(await settings.findByText("Slang")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close settings" }));
    expect(await screen.findByRole("button", { name: /Slang/ })).toBeInTheDocument();
  });

  it("refuses to remove a vocabulary that still holds words", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));

    const settings = within(await screen.findByRole("dialog", { name: /Settings/ }));
    fireEvent.click(settings.getByRole("tab", { name: "Vocabularies" }));
    const spanish = settings.getByText(/^es · defined in es/).closest(".config-row")!;
    fireEvent.click(within(spanish as HTMLElement).getByRole("button", { name: "Remove" }));
    // Nothing is deleted, but the words would lose the gloss preference they are rendered with.
    expect(await screen.findByText(/still has 3 words/)).toBeInTheDocument();
    expect(repository.snapshot().vocabularies.filter((entry) => !entry.deleted)).toHaveLength(2);
  });

  it("says plainly which actions are not connected yet", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Listen" }));
    expect(await screen.findByText("Audio is not wired up yet")).toBeInTheDocument();
  });

  it("refuses to build a second entry for a word already in the vocabulary", async () => {
    signedIn();
    await openList();
    const capture = vi.spyOn(backendSession, "captureText").mockResolvedValue({
      resolution: {
        language: "es", headword: "picar", lemma: "picar", pos: "verb",
        sentences: [], note: null, consumedLines: 1, consumedText: null
      },
      duplicates: [{ id: "lexemepicar0001", headword: "picar", shortGloss: "to itch; to chop" }],
      draft: null,
      applied: null
    });

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.change(await screen.findByLabelText(/Paste a word/), {
      target: { value: "¿Te pica mucho la salsa?" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Process" }));

    expect(await screen.findByText("You already have this word.")).toBeInTheDocument();
    // Nothing was generated and nothing was written; the entry it already has is one tap away.
    expect(capture).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "picar" }));
    expect(await screen.findByRole("button", { name: "Edit as YAML" })).toBeInTheDocument();
  });

  it("captures a sentence, reviews the generated entry as an article and saves it", async () => {
    signedIn();
    await openList();
    acceptWrites();
    mockGarfioCapture();

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.change(await screen.findByLabelText(/Paste a word/), {
      target: { value: "El disfraz de pirata viene con un garfio." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Process" }));

    // The proposal arrives rendered, not serialized: reviewing a generated entry is reading the
    // thing you are about to get, in the component a stored entry uses.
    expect(await screen.findByRole("heading", { name: "el garfio" })).toBeInTheDocument();
    expect(screen.getByText("Gancho de metal curvo y puntiagudo.")).toBeInTheDocument();
    expect(screen.getByText("grappling hook")).toBeInTheDocument();
    // Provenance is on the face of it, which is what makes the review worth doing.
    expect(screen.getByText("attestation")).toBeInTheDocument();
    // Nothing is stored, so there is no id, revision or date to claim there is.
    expect(document.querySelector(".meta-foot")).toBeNull();

    // Going back to the capture keeps what was submitted, so the text can be adjusted and re-run
    // rather than retyped.
    fireEvent.click(screen.getByRole("button", { name: "Capture" }));
    expect(await screen.findByLabelText(/Paste a word/))
      .toHaveValue("El disfraz de pirata viene con un garfio.");

    fireEvent.click(screen.getByRole("button", { name: "YAML" }));
    await screen.findByText("new-entry.yaml");
    await waitForEditor();
    expect(editorText()).toContain("headword: el garfio");
    expect(editorText()).toContain("origin: attestation");

    fireEvent.click(screen.getByRole("button", { name: "Validate & save" }));
    expect(await screen.findByRole("heading", { name: /garfio/ })).toBeInTheDocument();

    const saved = repository.snapshot();
    const lexeme = saved.lexemes.find((record) => record.headword === "el garfio");
    expect(lexeme?.status).toBe("inbox");
    const attestation = saved.attestations.find((record) => record.lexemeId === lexeme?.id);
    const example = saved.examples.find((record) => record.text.startsWith("El disfraz"));
    // Provenance is the point: the sentence survives as its own record, and the example says so.
    expect(example?.origin).toBe("attestation");
    expect(example?.sourceAttestationId).toBe(attestation?.id);
  });

  it("renders the proposal from the document, so a YAML edit shows in the article", async () => {
    signedIn();
    await openList();
    mockGarfioCapture();

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.change(await screen.findByLabelText(/Paste a word/), {
      target: { value: "El disfraz de pirata viene con un garfio." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Process" }));
    await screen.findByRole("heading", { name: "el garfio" });

    // The preview is derived from the editor text rather than kept beside it, so the two cannot
    // disagree about what is being approved.
    fireEvent.click(screen.getByRole("button", { name: "YAML" }));
    await screen.findByText("new-entry.yaml");
    await waitForEditor();
    replaceInEditor("headword: el garfio", "headword: el gancho");
    fireEvent.click(screen.getByRole("button", { name: "Article" }));
    expect(await screen.findByRole("heading", { name: "el gancho" })).toBeInTheDocument();

    // A document that cannot be read has nothing to show and nothing to approve.
    fireEvent.click(screen.getByRole("button", { name: "YAML" }));
    await waitForEditor();
    replaceInEditor("pos: noun", "pos: preposition");
    fireEvent.click(screen.getByRole("button", { name: "Article" }));
    expect(await screen.findByText(/must be one of/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("takes the word on its own, and says which one it is when the sentence does not", async () => {
    signedIn();
    await openList();
    const capture = vi.spyOn(backendSession, "captureText").mockResolvedValue({
      resolution: {
        language: "es", headword: "picar", lemma: "picar", pos: "verb",
        sentences: [], note: null, consumedLines: 1, consumedText: null
      },
      duplicates: [{ id: "lexemepicar0001", headword: "picar", shortGloss: "to itch; to chop" }],
      draft: null,
      applied: null
    });

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.change(await screen.findByLabelText(/Which word/), { target: { value: "  picar  " } });
    // The sentence is empty, so the word is the whole capture — one request shape, not two.
    fireEvent.click(screen.getByRole("button", { name: "Process" }));

    await screen.findByText("You already have this word.");
    expect(capture).toHaveBeenCalledWith(
      expect.any(String), expect.objectContaining({ text: "picar", headword: "picar" }));
  });

  it("saves an article edited as YAML and shows the change", async () => {
    signedIn();
    await openList();
    acceptWrites();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Edit as YAML" }));
    await waitForEditor();

    replaceInEditor("emoji: 🌶️", "emoji: 🫠");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Saved to the server")).toBeInTheDocument();
    await waitFor(() =>
      expect(repository.snapshot().lexemes.find((lexeme) => lexeme.id === "lexemepicar0001")!.emoji).toBe("🫠"));
  });

  it("keeps the draft and says what is wrong when the document does not parse", async () => {
    signedIn();
    await openList();
    acceptWrites();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Edit as YAML" }));
    await waitForEditor();

    replaceInEditor("pos: verb", "pos: preposition");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(/must be one of/)).toBeInTheDocument();
    // Still in the editor, with the rejected text intact rather than reverted.
    expect(editorText())
      .toContain("pos: preposition");
    expect(repository.snapshot().lexemes.find((lexeme) => lexeme.id === "lexemepicar0001")!.pos).toBe("verb");
  });

  it("replaces the word list while composing, and puts it back on cancel", async () => {
    signedIn();
    await openList();

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    await screen.findByRole("region", { name: "Add a word" });
    // The list is gone rather than covered, so the composer owns the height and can pin its own
    // header and buttons — which is the whole reason it is a view and not a dialog.
    expect(screen.queryByRole("button", { name: /picar/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(await screen.findByRole("button", { name: /picar/ })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Add a word" })).not.toBeInTheDocument();
  });

  it("edits an article in the same composer, not inside the scrolling pane", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Edit as YAML" }));

    // Same shell as Add, so the Save button cannot scroll away on a long entry.
    const editor = within(await screen.findByRole("region", { name: /Edit picar/ }));
    expect(editor.getByRole("button", { name: "Save" })).toBeInTheDocument();
    expect(document.querySelector(".main.composing")).not.toBeNull();

    fireEvent.click(editor.getByRole("button", { name: "Cancel" }));
    expect(await screen.findByRole("heading", { name: /picar/ })).toBeInTheDocument();
    expect(document.querySelector(".main.composing")).toBeNull();
  });

  it("wraps long lines by default, and keeps line numbers off", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Edit as YAML" }));
    await waitForEditor();

    // Wrapping is the default: these documents are prose, and a clipped definition was unreadable
    // and unscrollable both. The class is what the editor actually applies to wrap its lines.
    expect(document.querySelector(".cm-content")!.classList.contains("cm-lineWrapping")).toBe(true);
    // Numbers are off by default, and the gutter is absent rather than empty.
    expect(document.querySelector(".cm-lineNumbers")).toBeNull();
  });

  it("turns on line numbers from settings, and the editor picks them up", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));

    // Wrap and numbers describe this screen, not the vocabulary, so they live in settings rather
    // than as controls you step over on the way to the editor.
    const settings = within(await screen.findByRole("dialog", { name: /Settings/ }));
    fireEvent.click(settings.getByRole("tab", { name: "Editor" }));
    fireEvent.click(settings.getByRole("checkbox", { name: /Show line numbers/ }));
    fireEvent.click(screen.getByRole("button", { name: "Close settings" }));

    fireEvent.click(await screen.findByRole("button", { name: /picar/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Edit as YAML" }));
    await waitForEditor();
    // The editor draws a number per line and keeps it beside a line that wraps — which is the
    // reason numbers are worth offering at all.
    expect(document.querySelector(".cm-lineNumbers")).not.toBeNull();
    expect(localStorage.getItem("acervo-editor-numbers")).toBe("on");
  });

  it("creates an entry from the YAML template and opens it", async () => {
    signedIn();
    await openList();
    acceptWrites();
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    // A region, not a dialog: composing replaces the list rather than covering it.
    const sheet = within(screen.getByRole("region", { name: "Add a word" }));
    fireEvent.click(sheet.getByRole("button", { name: "YAML" }));
    await waitForEditor();

    const view = editorView();
    act(() => {
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: view.state.doc.toString()
        .replace('headword: ""', "headword: sobremesa")
        .replace('definition: ""', "definition: Charla tras la comida.")
        .replace('terms: [""]', "terms: [after-dinner talk]")
        .replace('- text: ""', "- text: La sobremesa duró dos horas.")
        .replace('translation: ""', "translation: The talk lasted two hours.") } });
    });
    fireEvent.click(sheet.getByRole("button", { name: "Validate & save" }));

    expect(await screen.findByText("Added to your vocabulary")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /sobremesa/ })).toBeInTheDocument();
  });

  it("reports a refused save without changing anything locally", async () => {
    signedIn();
    await openList();
    vi.spyOn(backendSession, "pushGraph")
      .mockRejectedValue(new AcervoApiError("This entry was changed somewhere else.", 409, "stale_record"));
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Edit as YAML" }));
    await waitForEditor();

    replaceInEditor("headword: picar", "headword: picarse");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(/changed somewhere else/)).toBeInTheDocument();
    expect(repository.snapshot().lexemes.find((lexeme) => lexeme.id === "lexemepicar0001")!.headword).toBe("picar");
  });

  it("deletes a word once the server has accepted the tombstone", async () => {
    signedIn();
    await openList();
    acceptWrites();
    fireEvent.click(screen.getByRole("button", { name: /la balsa/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
    expect(await screen.findByText(/tombstone/)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("button", { name: /la balsa/ })).not.toBeInTheDocument());
    expect(repository.snapshot().lexemes.find((lexeme) => lexeme.id === "lexemebalsa0001")?.deleted).toBe(true);
  });

  it("refuses to delete while offline, and changes nothing", async () => {
    signedIn();
    await openList();
    vi.spyOn(backendSession, "pushGraph")
      .mockRejectedValue(new AcervoApiError("The Acervo server could not be reached. Local vocabulary remains available.", 0, "offline"));
    fireEvent.click(screen.getByRole("button", { name: /la balsa/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
    expect(await screen.findByText(/could not be reached/)).toBeInTheDocument();
    // The entry is still open, still undeleted, and nothing was queued for later.
    expect(screen.getByRole("heading", { name: /la balsa/ })).toBeInTheDocument();
    expect(repository.snapshot().lexemes.find((lexeme) => lexeme.id === "lexemebalsa0001")?.deleted).toBe(false);
  });

  it("switches between the languages the replica holds", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: "Vocabulary language" }));
    fireEvent.click(await screen.findByRole("button", { name: /English/ }));
    expect(await screen.findByRole("button", { name: /turmoil/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /picar/ })).not.toBeInTheDocument();
  });

  it("announces and installs a waiting update explicitly", async () => {
    signedIn();
    await openList();
    act(() => { window.dispatchEvent(new CustomEvent(UPDATE_EVENT, { detail: "ready" })); });
    const gear = screen.getByRole("button", { name: "Open settings; an update is ready" });
    expect(gear).toHaveClass("has-update");
    fireEvent.click(gear);
    expect(await screen.findByRole("button", { name: /Update Acervo/ })).toBeInTheDocument();
  });

  it("offers the native macOS release from browser settings", async () => {
    vi.stubGlobal("navigator", {
      userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", platform: "MacIntel", maxTouchPoints: 0
    });
    signedIn();
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: {
        version: "0.1.0", build: "202608270001", file: "Acervo.zip", size: 42, sha256: "abc",
        url: "/api/acervo/downloads/Acervo.zip"
      } })
    } as Response);
    await openList();
    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));
    const link = await screen.findByRole("link", { name: /Download Acervo for macOS/ });
    expect(link).toHaveAttribute("href", "/api/acervo/downloads/Acervo.zip");
    expect(link).toHaveAttribute("download", "Acervo.zip");
  });

  /* The failure this guards against is a configured provider whose key is absent: the button looked
     live, and the only way to learn otherwise was to press it and read a 503. */
  it("turns Capture off with a reason when the server cannot build entries", async () => {
    signedIn();
    serverHealth({ available: false, provider: null, model: null, reason: "GEMINI_API_KEY is not set" });
    const capture = vi.spyOn(backendSession, "captureText");
    await openList();

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    const refusal = await screen.findByRole("alert");
    expect(refusal).toHaveTextContent("This server cannot build entries right now.");
    expect(refusal).toHaveTextContent("GEMINI_API_KEY is not set");

    fireEvent.change(screen.getByLabelText(/Paste a word/), { target: { value: "el garfio" } });
    expect(screen.getByRole("button", { name: "Process" })).toBeDisabled();
    expect(capture).not.toHaveBeenCalled();
    // Writing the entry by hand needs no model, so that way out stays open.
    expect(screen.getByRole("button", { name: "Write YAML instead" })).toBeEnabled();
  });

  it("leaves Capture live when the server never answered about it", async () => {
    signedIn();
    vi.spyOn(backendSession, "health").mockRejectedValue(new Error("offline"));
    await openList();

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.change(await screen.findByLabelText(/Paste a word/), { target: { value: "el garfio" } });
    // Unknown is not unavailable: a write is allowed to try, and to fail loudly if it must.
    expect(screen.getByRole("button", { name: "Process" })).toBeEnabled();
  });

  it("names the provider and model that build entries, in Settings \u25B8 Providers", async () => {
    /* Moved out of General, not duplicated: General read the *deployment's* provider from health,
       and Models reads the owner's own chain. Two readouts of "what builds an entry" would drift
       the moment a chain was chosen. */
    signedIn();
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue({
      providers: [{
        id: "gemini-free", label: "Gemini (free tier)", kinds: ["text"],
        models: { text: ["gemini/gemini-3.1-flash-lite"] },
        available: true, reason: null, usageUrl: null, notes: null
      }],
      chains: {
        text: { source: "deployment", reason: null, pairs: [] },
        image: { source: "deployment", reason: null, pairs: [] },
        audio: { source: "deployment", reason: null, pairs: [] }
      }
    });
    await openList();
    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));
    const settings = within(await screen.findByRole("dialog", { name: /Settings/ }));

    expect(settings.queryByText(/Entries are built by/)).not.toBeInTheDocument();
    fireEvent.click(settings.getByRole("tab", { name: "Providers" }));
    // Twice on purpose: once as a row in the text chain, once in the credentials table below it.
    expect(await settings.findAllByText("Gemini (free tier)")).toHaveLength(2);
    expect(settings.getByText("gemini/gemini-3.1-flash-lite")).toBeInTheDocument();
  });
});

/* ── the article conversation (design §06) ──────────────────────────────
   Chat is a consumer of the core: no storage, no second writer, and every change goes through
   `repository.saveArticle` at the entry's own revision. What is asserted here is that shape — that
   a proposal reaches the article as marks and nothing else, that saving is one ordinary write, and
   that undo is the previous document saved again. */

/** A turn that answers in prose and proposes one small edit. */
function mockChat(reply: string, proposal: unknown = null) {
  const chat = vi.spyOn(backendSession, "chat");
  // Reset rather than only re-implement: a spy on a method that was already spied keeps the call
  // history, and "asks nothing" would then be asserting against the previous test's turn.
  chat.mockReset();
  chat.mockResolvedValue({
    reply, followUps: ["One more example"],
    proposal: proposal as never, capture: null, modelId: "gemini-3.1-flash-lite"
  });
  return chat;
}

async function openPicar() {
  await openList();
  fireEvent.click(screen.getByRole("button", { name: /picar/ }));
  await screen.findByRole("heading", { name: "picar" });
}

async function ask(question: string) {
  const composer = screen.getByLabelText("Ask about picar");
  fireEvent.change(composer, { target: { value: question } });
  fireEvent.submit(composer.closest("form")!);
}

describe("asking about an article", () => {
  it("offers the dock on a stored article and answers in the thread", async () => {
    signedIn();
    const chat = mockChat("«picar» is to itch, and also to chop.");
    await openPicar();
    await ask("what does this mean?");
    expect(await screen.findByText("«picar» is to itch, and also to chop.")).toBeInTheDocument();
    expect(chat).toHaveBeenCalledTimes(1);
    // The document goes with the question: `yaml.ts` is the only place the projection is understood,
    // so the device serialises it rather than the server.
    const [, request] = chat.mock.calls[0];
    expect(request.subject.kind).toBe("article");
    expect((request.subject as { document: string }).document).toContain("headword: picar");
    // Chosen from the replica before the request left, which is why there is no tool loop.
    expect(request.neighbours?.length).toBeGreaterThan(0);
    // A follow-up is one tap instead of a sentence of typing.
    expect(screen.getByRole("button", { name: "One more example" })).toBeInTheDocument();
  });

  it("says the server is needed when it is unreachable, and asks nothing", async () => {
    signedIn();
    const chat = mockChat("never reached");
    await openList();
    vi.spyOn(backendSession, "pullGraph")
      .mockRejectedValue(new AcervoApiError("unreachable", 0, "offline"));
    render(<App />);
    fireEvent.click((await screen.findAllByRole("button", { name: /picar/ }))[0]);
    await screen.findAllByRole("heading", { name: "picar" });
    // Reading never depends on the server; this is the only part of the article view that does.
    // The second render is the reload; the first is still mounted, so take the latest.
    await waitFor(() => {
      const composers = screen.getAllByLabelText("Ask about picar");
      expect(composers[composers.length - 1]).toBeDisabled();
    });
    expect(chat).not.toHaveBeenCalled();
  });

  it("hides the dock entirely when the server has no model configured", async () => {
    signedIn();
    serverHealth({ available: false, reason: "no key" });
    await openPicar();
    await waitFor(() =>
      expect(screen.queryByLabelText("Ask about picar")).not.toBeInTheDocument());
  });

  it("shows a proposal as marks on the article, writing nothing until asked", async () => {
    signedIn();
    acceptWrites();
    mockChat("Worth noting the contrast.", {
      summary: "Adds a note.",
      ops: [{ op: "set", target: "lexeme", field: "notes", value: ["Not «rascar»."] }]
    });
    await openPicar();
    await ask("add a note about rascar");

    // The proposal arrives as a card in the thread, not as an applied change.
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    expect(await screen.findByText("Not «rascar».")).toBeInTheDocument();
    /* `set notes` takes the whole list, so replacing it is one note added and one removed — and
       both are marked. The removed line is still drawn, struck through: nothing vanishes without
       being seen going. */
    expect(screen.getByText(/2 changes proposed/)).toBeInTheDocument();
    expect(document.querySelector(".mark-add")).not.toBeNull();
    expect(document.querySelector(".mark-cut")).not.toBeNull();
    expect(screen.getByText("The sense is carried by the object, not the verb."))
      .toHaveClass("mark-cut");
    // Nothing is written until a second press.
    expect(backendSession.pushGraph).not.toHaveBeenCalled();
  });

  it("saves a reviewed proposal as one ordinary write, and undoes it as another", async () => {
    signedIn();
    acceptWrites();
    mockChat("Worth noting.", {
      summary: "Adds a note.",
      ops: [{ op: "set", target: "lexeme", field: "notes", value: ["Not «rascar»."] }]
    });
    await openPicar();
    await ask("add a note");
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    fireEvent.click(await screen.findByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(backendSession.pushGraph).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(repository.snapshot().lexemes.find((one) => one.id === "lexemepicar0001")!.notes)
        .toContain("Not «rascar»."));

    // Undo is the previous document, saved again — an ordinary online write like everything else.
    fireEvent.click(await screen.findByRole("button", { name: "Undo" }));
    await waitFor(() => expect(backendSession.pushGraph).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(repository.snapshot().lexemes.find((one) => one.id === "lexemepicar0001")!.notes)
        .not.toContain("Not «rascar»."));
  });

  it("brings a removed example back with its own id when the save is undone", async () => {
    signedIn();
    acceptWrites();
    mockChat("That one duplicates the other.", {
      summary: "Removes an example.",
      ops: [{ op: "remove", target: "example:examplepicar010", reason: "duplicate" }]
    });
    await openPicar();
    await ask("drop the first example");
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    fireEvent.click(await screen.findByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(
      repository.snapshot().examples.find((one) => one.id === "examplepicar010")!.deleted).toBe(true));

    fireEvent.click(await screen.findByRole("button", { name: "Undo" }));
    // A tombstone, not an erasure, and `stamp` sets `deleted: false` — so naming the id again
    // brings the record back rather than creating a second one under a new id.
    await waitFor(() => expect(
      repository.snapshot().examples.find((one) => one.id === "examplepicar010")!.deleted).toBe(false));
  });

  it("drops a proposal rather than applying it when the model names something that is not there", async () => {
    signedIn();
    mockChat("Here you go.", {
      summary: "Edits a sense that does not exist.",
      ops: [{ op: "set", target: "sense:nosuchsense001", field: "domain", value: "cooking" }]
    });
    await openPicar();
    await ask("fix sense three");
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    expect(await screen.findByText(/not there, so nothing was changed/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
  });

  it("keeps the dock out of the Add view's own preview", async () => {
    signedIn();
    mockGarfioCapture();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /Add/ }));
    fireEvent.change(await screen.findByLabelText(/Paste a word/), {
      target: { value: "El disfraz de pirata viene con un garfio." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Process" }));
    await screen.findByRole("heading", { name: "el garfio" });
    // The Add view replaces the pane rather than sharing it, so the stored article's dock is gone…
    expect(screen.queryByLabelText("Ask about picar")).not.toBeInTheDocument();
    // …and the one over the unsaved proposal is about the word being added (§8.4).
    expect(screen.getByLabelText("Ask about el garfio")).toBeInTheDocument();
  });
});
