import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { AcervoApiError, backendSession, SCHEMA_VERSION } from "./api";
import { UPDATE_EVENT } from "./pwa";
import { repository } from "./repository";
import { TEST_OWNER, testGraph } from "./testGraph";

vi.mock("virtual:pwa-register", () => ({ registerSW: vi.fn() }));

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

function signedIn() {
  const { graph, cursor } = numberedGraph();
  vi.spyOn(backendSession, "restore").mockResolvedValue(SESSION);
  vi.spyOn(backendSession, "current").mockReturnValue(SESSION);
  vi.spyOn(backendSession, "refresh").mockResolvedValue(SESSION);
  vi.spyOn(backendSession, "pullGraph").mockResolvedValue({
    schemaVersion: SCHEMA_VERSION, datasetId: DATASET, cursor,
    serverTime: "2026-08-29T12:00:00.000Z", changes: graph
  });
}

/** A server that accepts every write and numbers the rows it hands back, as the real one does. */
function acceptWrites() {
  vi.spyOn(backendSession, "pushGraph").mockImplementation(async (_device, changes) => ({
    schemaVersion: SCHEMA_VERSION, datasetId: DATASET,
    cursor: repository.snapshot().cursor + 1, serverTime: "2026-08-29T12:00:01.000Z",
    records: Object.fromEntries(Object.entries(changes).map(([kind, records]) =>
      [kind, (records ?? []).map((record, index) => ({ ...record, revision: repository.snapshot().cursor + 1 + index }))]))
  }));
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
    expect(document.querySelector(".code-scroll code")!.textContent).toContain("id: lexemepicar0001");
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
    expect(settings.getByRole("button", { name: "Sync now" })).toBeInTheDocument();
    expect(settings.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    expect(settings.getByRole("button", { name: /Delete all vocabulary/ })).toBeInTheDocument();
    // A second update control here would conflict with the one the host already owns.
    expect(settings.queryByText("Acervo is up to date")).not.toBeInTheDocument();
    expect(settings.queryByText(/Download Acervo for macOS/)).not.toBeInTheDocument();
    expect(settings.getByText("Updates and server address")).toBeInTheDocument();
  });

  it("says plainly which actions are not connected yet", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Listen" }));
    expect(await screen.findByText("Audio is not wired up yet")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.click(await screen.findByRole("button", { name: "Process" }));
    expect(await screen.findByText("Capture pipeline is not wired up yet")).toBeInTheDocument();
  });

  it("saves an article edited as YAML and shows the change", async () => {
    signedIn();
    await openList();
    acceptWrites();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Edit as YAML" }));

    const editor = document.querySelector(".code-scroll textarea") as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: editor.value.replace("emoji: 🌶️", "emoji: 🫠") } });
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

    const editor = document.querySelector(".code-scroll textarea") as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: editor.value.replace("pos: verb", "pos: preposition") } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(/must be one of/)).toBeInTheDocument();
    // Still in the editor, with the rejected text intact rather than reverted.
    expect((document.querySelector(".code-scroll textarea") as HTMLTextAreaElement).value)
      .toContain("pos: preposition");
    expect(repository.snapshot().lexemes.find((lexeme) => lexeme.id === "lexemepicar0001")!.pos).toBe("verb");
  });

  it("creates an entry from the YAML template and opens it", async () => {
    signedIn();
    await openList();
    acceptWrites();
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    const sheet = within(screen.getByRole("dialog", { name: "Add a word" }));
    fireEvent.click(sheet.getByRole("button", { name: "YAML" }));

    const editor = document.querySelector(".sheet .code-scroll textarea") as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: editor.value
      .replace('headword: ""', "headword: sobremesa")
      .replace('definition: ""', "definition: Charla tras la comida.")
      .replace('terms: [""]', "terms: [after-dinner talk]")
      .replace('- text: ""', "- text: La sobremesa duró dos horas.")
      .replace('translation: ""', "translation: The talk lasted two hours.") } });
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

    const editor = document.querySelector(".code-scroll textarea") as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: editor.value.replace("headword: picar", "headword: picarse") } });
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
});
