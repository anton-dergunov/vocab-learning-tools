import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { backendSession, type ModelCatalogue, type ModelPair } from "./api";
import ModelPanel from "./ModelPanel";

const GEMINI = "gemini/gemini-3.1-flash-lite";
const GEMINI_SECOND = "gemini/gemini-3.5-flash-lite";
const CLOUDFLARE = "cloudflare/@cf/meta/llama-3.3-70b-instruct-fp8-fast";

const pair = (provider: string, model: string): ModelPair => ({ provider, model });

function catalogue(overrides: Partial<ModelCatalogue> = {}): ModelCatalogue {
  return {
    providers: [
      {
        id: "gemini-free", label: "Gemini (free tier)", kinds: ["text", "audio"],
        models: { text: [GEMINI, GEMINI_SECOND], audio: ["gemini/gemini-3.1-flash-tts-preview"] },
        available: true, reason: null,
        usageUrl: "https://aistudio.google.com/rate-limit", notes: "500 a day at no cost."
      },
      {
        id: "cloudflare", label: "Cloudflare Workers AI", kinds: ["text"],
        models: { text: [CLOUDFLARE] },
        available: false, reason: "CLOUDFLARE_API_TOKEN is not set",
        usageUrl: "https://dash.cloudflare.com/abc/ai/workers-ai", notes: null
      }
    ],
    chains: {
      text: { source: "deployment", reason: null, pairs: [pair("gemini-free", GEMINI)] },
      image: { source: "deployment", reason: null, pairs: [] },
      audio: { source: "deployment", reason: null, pairs: [] }
    },
    ...overrides
  };
}

function panel() {
  return render(<ModelPanel onNotify={() => {}} />);
}

const rowOf = (element: HTMLElement): HTMLElement => element.closest(".model-row") as HTMLElement;

describe("the Providers pane", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists every model a provider offers, because the choice is a pair and not a provider", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    panel();
    // Gemini's two free-tier models are separate 500-a-day buckets, so both must be selectable.
    expect(await screen.findByText(GEMINI)).toBeInTheDocument();
    expect(screen.getByText(GEMINI_SECOND)).toBeInTheDocument();
  });

  it("says the server's own order is in force until something is chosen", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    panel();
    expect(await screen.findAllByText(/own order is in force/i)).not.toHaveLength(0);
  });

  it("renders an unavailable provider with its reason instead of hiding it", async () => {
    /* It keeps its place in a saved order and is skipped when the chain is walked, so hiding it
       would make the order the owner saved unexplainable. */
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    panel();
    const row = rowOf(await screen.findByText(CLOUDFLARE));
    expect(row).toHaveClass("unavailable");
    expect(within(row).getByText(/CLOUDFLARE_API_TOKEN is not set/)).toBeInTheDocument();
  });

  it("shows the server's own order as switched on, because it is what will actually be asked", async () => {
    /* The bug this replaces: under the deployment default every box rendered unticked, so unticking
       the last model looked like switching capture off while the server carried on building entries
       with the model at the head of its own order. */
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    panel();
    expect(within(rowOf(await screen.findByText(GEMINI))).getByRole("checkbox")).toBeChecked();
    expect(screen.getByText(/own order is in force/i)).toBeInTheDocument();
  });

  it("lets an unavailable pair be switched on, because a rotated key must not lock the owner out", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    const save = vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(catalogue());
    panel();
    const row = rowOf(await screen.findByText(CLOUDFLARE));
    fireEvent.click(within(row).getByRole("checkbox"));
    // Adding to the inherited order, which is what was on screen — not replacing it.
    await waitFor(() => expect(save).toHaveBeenCalledWith({
      text: [pair("gemini-free", GEMINI), pair("cloudflare", CLOUDFLARE)]
    }));
  });

  it("changing anything makes the inherited order yours, in one write naming one kind", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    const save = vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(catalogue());
    panel();
    const row = rowOf(await screen.findByText(GEMINI_SECOND));
    fireEvent.click(within(row).getByRole("checkbox"));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save).toHaveBeenCalledWith({
      text: [pair("gemini-free", GEMINI), pair("gemini-free", GEMINI_SECOND)]
    });
  });

  it("marks an unavailable row with a badge and not only with dimmed text", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    panel();
    const row = rowOf(await screen.findByText(CLOUDFLARE));
    expect(within(row).getByText(/unavailable/i)).toBeInTheDocument();
  });

  it("says so when unticking the last one hands the order back to the server", async () => {
    /* There is no "use nothing" state — the route refuses an empty chain — so the server's models
       reappear ticked, and without a word that reads as the tick having been ignored. */
    const chosen = catalogue({
      chains: {
        text: { source: "owner", reason: null, pairs: [pair("gemini-free", GEMINI)] },
        image: { source: "deployment", reason: null, pairs: [] },
        audio: { source: "deployment", reason: null, pairs: [] }
      }
    });
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(chosen);
    vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(catalogue());
    const notified = vi.fn();
    render(<ModelPanel onNotify={notified} />);
    const row = rowOf(await screen.findByText(GEMINI));
    fireEvent.click(within(row).getByRole("checkbox"));
    await waitFor(() => expect(notified).toHaveBeenCalledWith(
      expect.stringMatching(/own order is back in force/i)));
  });

  it("reorders a chosen pair with the arrows", async () => {
    const chosen = catalogue({
      chains: {
        text: {
          source: "owner", reason: null,
          pairs: [pair("gemini-free", GEMINI), pair("gemini-free", GEMINI_SECOND)]
        },
        image: { source: "deployment", reason: null, pairs: [] },
        audio: { source: "deployment", reason: null, pairs: [] }
      }
    });
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(chosen);
    const save = vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(chosen);
    panel();
    const row = rowOf(await screen.findByText(GEMINI_SECOND));
    fireEvent.click(within(row).getByRole("button", { name: /up$/i }));
    await waitFor(() => expect(save).toHaveBeenCalledWith({
      text: [pair("gemini-free", GEMINI_SECOND), pair("gemini-free", GEMINI)]
    }));
  });

  it("cannot move a pair that is switched off", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    panel();
    // Cloudflare is not in the server's order, so it has no place to move within.
    const row = rowOf(await screen.findByText(CLOUDFLARE));
    expect(within(row).getByRole("button", { name: /up$/i })).toBeDisabled();
    expect(within(row).getByRole("button", { name: /down$/i })).toBeDisabled();
  });

  it("switching the last one off hands back rather than sending an empty chain", async () => {
    /* An empty chain is refused by the route, so without this the first choice would be a one-way
       door out of following the deployment default. */
    const chosen = catalogue({
      chains: {
        text: { source: "owner", reason: null, pairs: [pair("gemini-free", GEMINI)] },
        image: { source: "deployment", reason: null, pairs: [] },
        audio: { source: "deployment", reason: null, pairs: [] }
      }
    });
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(chosen);
    const save = vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(catalogue());
    panel();
    const row = rowOf(await screen.findByText(GEMINI));
    fireEvent.click(within(row).getByRole("checkbox"));
    await waitFor(() => expect(save).toHaveBeenCalledWith({ text: null }));
  });

  it("shows what the server answered rather than what was clicked", async () => {
    const after = catalogue({
      chains: {
        text: { source: "owner", reason: null, pairs: [pair("gemini-free", GEMINI_SECOND)] },
        image: { source: "deployment", reason: null, pairs: [] },
        audio: { source: "deployment", reason: null, pairs: [] }
      }
    });
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(after);
    panel();
    const row = rowOf(await screen.findByText(GEMINI_SECOND));
    fireEvent.click(within(row).getByRole("checkbox"));
    await waitFor(() =>
      expect(within(rowOf(screen.getByText(GEMINI_SECOND))).getByRole("checkbox")).toBeChecked());
  });

  it("fails loudly and leaves the shown order alone when the server refuses", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    vi.spyOn(backendSession, "saveModelSelection").mockRejectedValue(new Error("That is not a model."));
    const notified = vi.fn();
    render(<ModelPanel onNotify={notified} />);
    const row = rowOf(await screen.findByText(GEMINI_SECOND));
    fireEvent.click(within(row).getByRole("checkbox"));
    await waitFor(() => expect(notified).toHaveBeenCalledWith("That is not a model."));
    expect(within(rowOf(screen.getByText(GEMINI_SECOND))).getByRole("checkbox")).not.toBeChecked();
  });

  it("says the picture and pronunciation orders are kept but not yet read", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    panel();
    expect(await screen.findByText(/Nothing reads this order yet — the job that draws them/i))
      .toBeInTheDocument();
  });

  it("links out to each provider's own usage page", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    panel();
    const link = await screen.findByRole("link", { name: /Gemini \(free tier\) usage/i });
    expect(link).toHaveAttribute("href", "https://aistudio.google.com/rate-limit");
  });

  it("says so plainly when the server cannot be reached", async () => {
    vi.spyOn(backendSession, "fetchModels").mockRejectedValue(new Error("offline"));
    panel();
    expect(await screen.findByText(/could not be reached/i)).toBeInTheDocument();
  });
});
