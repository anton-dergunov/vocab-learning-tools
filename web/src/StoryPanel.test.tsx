/**
 * Settings ▸ Stories: which voice reads a story and whether it is recorded when the story is made.
 *
 * Both live in the pronunciation settings the server keeps for the owner, so what is pinned here is
 * that the panel reads them from there, writes only what it changed, and puts things back when the
 * server refuses.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AcervoApiError, backendSession, type PronunciationSettings } from "./api";
import StoryPanel from "./StoryPanel";

function settings(overrides: Partial<PronunciationSettings> = {}): PronunciationSettings {
  return {
    pregenerate: { headword: false, definitions: false, examples: false, stories: true },
    delivery: { words: "plain", examples: "expressive", loops: "expressive", stories: "expressive" },
    voices: {}, chosen: false, languages: ["es"], orders: { plain: [], expressive: [] },
    ...overrides
  };
}

async function panel(stored = settings(), onNotify: (message: string) => void = () => undefined) {
  vi.spyOn(backendSession, "pronunciationSettings").mockResolvedValue(stored);
  const saved = vi.spyOn(backendSession, "savePronunciationSettings")
    .mockImplementation(async (changes) => ({
      ...stored,
      pregenerate: { ...stored.pregenerate, ...changes.pregenerate },
      delivery: { ...stored.delivery, ...changes.delivery },
      chosen: true
    }));
  render(<StoryPanel onNotify={onNotify} />);
  await screen.findByRole("radio", { name: /takes a direction/ });
  return saved;
}

afterEach(() => vi.restoreAllMocks());

describe("Settings ▸ Stories", () => {
  it("offers the directed voice as what is chosen until it is changed", async () => {
    await panel();
    expect(screen.getByRole("radio", { name: /takes a direction/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /clear, even voice/ })).not.toBeChecked();
  });

  it("chooses the voice that reads a story, and writes only that", async () => {
    const saved = await panel();

    fireEvent.click(screen.getByRole("radio", { name: /clear, even voice/ }));

    await waitFor(() => expect(saved).toHaveBeenCalledWith({ delivery: { stories: "plain" } }));
    expect(screen.getByRole("radio", { name: /clear, even voice/ })).toBeChecked();
  });

  it("says what each voice does to a story, because they are not the same price", async () => {
    await panel();
    expect(screen.getByText(/cut into passages/)).toBeInTheDocument();
    expect(screen.getByText(/One call a part/)).toBeInTheDocument();
  });

  it("records a story when it is made unless that is switched off", async () => {
    const saved = await panel();
    const recording = screen.getByRole("checkbox", { name: /Record a story’s narration when it is made/ });
    expect(recording).toBeChecked();

    fireEvent.click(recording);

    await waitFor(() => expect(saved).toHaveBeenCalledWith({ pregenerate: { stories: false } }));
    expect(recording).not.toBeChecked();
  });

  it("puts the choice back and says so when the server would not keep it", async () => {
    const notified = vi.fn();
    const saved = await panel(settings(), notified);
    saved.mockRejectedValueOnce(new AcervoApiError("The server cannot be reached.", 0, "offline"));

    fireEvent.click(screen.getByRole("radio", { name: /clear, even voice/ }));

    await waitFor(() => expect(notified).toHaveBeenCalledWith("The server cannot be reached."));
    expect(screen.getByRole("radio", { name: /takes a direction/ })).toBeChecked();
  });
});
