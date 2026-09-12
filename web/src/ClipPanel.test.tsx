/**
 * Settings ▸ Clips: what the channel list says, and what it does not say twice.
 *
 * The catalogue is the corpus service's, so what is tested here is Acervo's presentation of it —
 * the grouping, the link, and the fact that switching a channel on is a request to that service
 * rather than anything Acervo stores.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const channels = vi.fn();
const setChannelEnabled = vi.fn(async (_language: string, _id: string, _on: boolean) => undefined);
const clipSettings = vi.fn();
const saveClipSettings = vi.fn();

vi.mock("./clips", async () => {
  const actual = await vi.importActual<typeof import("./clips")>("./clips");
  return { ...actual, channels: () => channels(), setChannelEnabled: (...a: [string, string, boolean]) => setChannelEnabled(...a) };
});
vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return {
    ...actual,
    backendSession: { ...actual.backendSession, clipSettings: () => clipSettings(), saveClipSettings: () => saveClipSettings() }
  };
});

const { default: ClipPanel } = await import("./ClipPanel");

const channel = (over: Partial<Record<string, unknown>> = {}) => ({
  source_language: "es", section_id: "learning", section_name: "Language learning",
  id: "easy-spanish", name: "Easy Spanish", url: "https://www.youtube.com/@EasySpanish/videos",
  enabled: true, varieties: ["Spain", "Mexico"], speech_style: ["conversation"], description: null,
  ...over
});

function panel() {
  clipSettings.mockResolvedValue({
    searchEnabled: true, selfContainedOnly: false, chosen: false,
    corpus: { configured: true, reachable: true, ready: true, indexedLanguages: ["es"], videos: 251, segments: 60704 }
  });
  render(<ClipPanel onNotify={() => undefined} />);
}

afterEach(() => { vi.clearAllMocks(); });

describe("the channel catalogue", () => {
  it("groups by language, and does not repeat the language on every row", async () => {
    // The language used to sit against each channel's name, where it was both redundant and — with
    // the old flex row — run together with it: "Easy Spanishes · Spain · Mexico".
    channels.mockResolvedValue([
      channel(),
      channel({ id: "linguriosa", name: "Linguriosa", enabled: false }),
      channel({ source_language: "en", id: "bbc", name: "BBC", section_name: "News", enabled: false })
    ]);
    panel();

    await screen.findByText("1 of 2 on");
    const groups = [...document.querySelectorAll("details.channel-group")];
    expect(groups).toHaveLength(2);       // two languages, two groups
    const group = groups.find((one) => one.textContent?.includes("Easy Spanish"))!;
    expect(within(group as HTMLElement).getByText("1 of 2 on")).toBeTruthy();
    // The row says the variety and the style, and nothing about the language.
    expect(within(group as HTMLElement).getAllByText("Spain · Mexico · conversation")).toHaveLength(2);
    // And nothing on the row says the language, which the group heading already carries.
    expect(within(group as HTMLElement).queryByText(/\bes\b/)).toBeNull();
  });

  it("is shut until it is opened", async () => {
    channels.mockResolvedValue([channel()]);
    panel();
    await screen.findByText("1 of 1 on");
    const group = document.querySelector("details.channel-group") as HTMLDetailsElement;
    expect(group.open).toBe(false);
  });

  it("counts what is on without being opened", async () => {
    channels.mockResolvedValue([
      channel(), channel({ id: "b", name: "B", enabled: false }), channel({ id: "c", name: "C", enabled: false })
    ]);
    panel();
    expect(await screen.findByText("1 of 3 on")).toBeTruthy();
  });

  it("names each of the corpus's own sections", async () => {
    channels.mockResolvedValue([
      channel(),
      channel({ id: "ruina", name: "La Ruina", section_name: "Live comedy", enabled: false })
    ]);
    panel();
    expect(await screen.findByText("Language learning")).toBeTruthy();
    expect(screen.getByText("Live comedy")).toBeTruthy();
  });

  it("opens the channel itself from its name", async () => {
    // The useful thing to do with a channel you are deciding about is watch some of it.
    channels.mockResolvedValue([channel()]);
    panel();
    const link = await screen.findByRole("link", { name: "Easy Spanish" }) as HTMLAnchorElement;
    expect(link.href).toBe("https://www.youtube.com/@EasySpanish/videos");
    expect(link.target).toBe("_blank");
    expect(link.rel).toContain("noreferrer");
  });

  it("switches a channel through the corpus service rather than storing anything", async () => {
    channels.mockResolvedValue([channel()]);
    panel();
    await screen.findByText("1 of 1 on");
    const box = document.querySelector("#channel-es-easy-spanish") as HTMLInputElement;
    fireEvent.click(box);
    await waitFor(() => expect(setChannelEnabled).toHaveBeenCalledWith("es", "easy-spanish", false));
  });

  it("says that switching one on does nothing until a harvest is run", async () => {
    // Nothing in Acervo schedules one, so promising "the next harvest" without saying who runs it
    // would be a promise the deployment does not keep.
    channels.mockResolvedValue([channel()]);
    panel();
    expect(await screen.findByText(/index-clips/)).toBeTruthy();
  });
});
