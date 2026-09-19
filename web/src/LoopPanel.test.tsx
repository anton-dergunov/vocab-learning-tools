/**
 * Settings ▸ Loops: the three kinds of setting on one page, and which is which.
 *
 * The voice is the owner's and goes to the server, stored beside the other two pronunciation uses —
 * it is the same record, chosen here because what it costs and what it does to a track are loop
 * facts. Keeping a track is this device's and never leaves it. What the generator can do is the
 * deployment's and is read, not set.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { backendSession, type LoopSchema, type PronunciationSettings } from "./api";
import LoopPanel from "./LoopPanel";
import { replaceStoreForTests } from "./loops";
import { MemoryMediaStore } from "./mediaStore";

const SCHEMA: LoopSchema = {
  apiVersion: "1.0.0", engineVersion: "1.4.0", maxItems: 24,
  patterns: ["retrieval"], families: ["auto", "gentle-game"], productionBundle: true
};

function settings(loops: "plain" | "expressive" = "expressive"): PronunciationSettings {
  return {
    pregenerate: { headword: false, definitions: false, examples: false },
    delivery: { words: "plain", examples: "expressive", loops },
    voices: {}, chosen: false, languages: ["es"], orders: { plain: [], expressive: [] }
  };
}

async function panel(stored = settings()) {
  replaceStoreForTests(new MemoryMediaStore());
  vi.spyOn(backendSession, "loopSchema").mockResolvedValue(SCHEMA);
  vi.spyOn(backendSession, "pronunciationSettings").mockResolvedValue(stored);
  const saved = vi.spyOn(backendSession, "savePronunciationSettings")
    .mockImplementation(async (changes) => ({
      ...stored,
      pregenerate: { ...stored.pregenerate, ...changes.pregenerate },
      delivery: { ...stored.delivery, ...changes.delivery },
      voices: changes.voices ?? stored.voices,
      chosen: true
    }));
  render(<LoopPanel onNotify={() => undefined} />);
  await screen.findByRole("heading", { name: "Loops" });
  return saved;
}

afterEach(() => vi.restoreAllMocks());

describe("Settings ▸ Loops", () => {
  it("chooses the voice that speaks a loop, and stores it where the other two uses live", async () => {
    const saved = await panel();
    const directed = await screen.findByRole("radio", { name: /takes a direction/ });
    expect(directed).toBeChecked();

    fireEvent.click(screen.getByRole("radio", { name: /clear, even voice/ }));
    await waitFor(() => expect(saved).toHaveBeenCalledWith({ delivery: { loops: "plain" } }));
  });

  it("says what each order costs, because the two are not the same price", async () => {
    await panel();
    expect(await screen.findByText(/Three calls a line/)).toBeInTheDocument();
    expect(screen.getByText(/A third of the calls/)).toBeInTheDocument();
  });

  it("reads what the generator can do rather than offering to change it", async () => {
    await panel();
    expect(await screen.findByText(/Engine 1.4.0/)).toBeInTheDocument();
    expect(screen.getByText(/sample pack is installed/)).toBeInTheDocument();
  });
});
