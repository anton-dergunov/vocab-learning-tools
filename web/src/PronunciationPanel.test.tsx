/**
 * Settings ▸ Pronunciation: the two kinds of setting on one page, and which is which.
 *
 * What is recorded, how it is delivered and which voice reads are the owner's and go to the server.
 * Keeping clips is this device's, so it never does — and switching it off forgets what was kept.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { backendSession, type PronunciationSettings } from "./api";
import { pronunciationCacheEnabled, setPronunciationCacheEnabled } from "./editorPreferences";
import { MemoryMediaStore } from "./mediaStore";
import PronunciationPanel from "./PronunciationPanel";
import { replaceStoreForTests } from "./pronunciation";

const WAVENET = {
  provider: "google-tts", providerLabel: "Google Cloud Text-to-Speech", model: "wavenet",
  available: true, style: "none" as const, voices: { es: ["es-ES-Wavenet-F", "es-ES-Wavenet-E"] }
};

function settings(overrides: Partial<PronunciationSettings> = {}): PronunciationSettings {
  return {
    pregenerate: { headword: false, definitions: false, examples: false },
    expressive: true, voices: {}, chosen: false, languages: ["es"],
    orders: { plain: [WAVENET], expressive: [{ ...WAVENET, model: "gemini-3.1-flash-tts-preview", style: "instruction", voices: { es: ["Kore"] } }] },
    ...overrides
  };
}

async function panel(stored = settings()) {
  replaceStoreForTests(new MemoryMediaStore());
  setPronunciationCacheEnabled(true);
  vi.spyOn(backendSession, "pronunciationSettings").mockResolvedValue(stored);
  const saved = vi.spyOn(backendSession, "savePronunciationSettings")
    .mockImplementation(async (changes) => ({ ...stored, ...changes, pregenerate: { ...stored.pregenerate, ...changes.pregenerate }, chosen: true }));
  render(<PronunciationPanel onNotify={() => undefined} />);
  await screen.findByRole("heading", { name: "Pronunciation" });
  return saved;
}

afterEach(() => { vi.restoreAllMocks(); setPronunciationCacheEnabled(true); });

describe("Settings ▸ Pronunciation", () => {
  it("stores what to record in advance on the server, where the recording happens", async () => {
    const saved = await panel();
    fireEvent.click(await screen.findByRole("checkbox", { name: /The word itself/ }));
    await waitFor(() => expect(saved).toHaveBeenCalledWith({ pregenerate: { headword: true } }));
  });

  it("stores whether examples carry their emotion", async () => {
    const saved = await panel();
    fireEvent.click(screen.getByRole("checkbox", { name: /Speak examples with their emotion/ }));
    await waitFor(() => expect(saved).toHaveBeenCalledWith({ expressive: false }));
  });

  it("offers each model's voices for each vocabulary language, the default first", async () => {
    await panel();
    const select = screen.getAllByRole("combobox")[0];
    expect([...select.querySelectorAll("option")].map((option) => option.textContent))
      .toEqual(["Default · es-ES-Wavenet-F", "es-ES-Wavenet-F", "es-ES-Wavenet-E"]);
  });

  it("stores a chosen voice under its model and language", async () => {
    const saved = await panel();
    fireEvent.change(screen.getAllByRole("combobox")[0], { target: { value: "es-ES-Wavenet-E" } });
    await waitFor(() => expect(saved).toHaveBeenCalledWith({
      voices: { "google-tts": { wavenet: { es: "es-ES-Wavenet-E" } } }
    }));
  });

  it("keeps clips as a device preference, which the server is never told about", async () => {
    const saved = await panel();
    fireEvent.click(screen.getByRole("checkbox", { name: /Keep pronunciations on this device/ }));
    await waitFor(() => expect(pronunciationCacheEnabled()).toBe(false));
    expect(saved).not.toHaveBeenCalled();
  });

  it("still offers to forget what is kept when the server cannot be reached", async () => {
    replaceStoreForTests(new MemoryMediaStore());
    vi.spyOn(backendSession, "pronunciationSettings").mockRejectedValue(new Error("away"));
    render(<PronunciationPanel onNotify={() => undefined} />);
    expect(await screen.findByRole("button", { name: /Forget pronunciations/ })).toBeInTheDocument();
  });
});
