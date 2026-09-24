/**
 * Make a story: the owner's own note to the writer travels with the request, trimmed, and only when
 * something was written in it.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { backendSession, type Job, type StoryTypes } from "./api";
import type { Story } from "./domain";
import StoryDialog from "./StoryDialog";
import { testGraph } from "./testGraph";

const TYPES = {
  types: [{ id: "funny", label: "Funny", emoji: "", styles: ["comic-book"] }],
  styles: [{ id: "comic-book", label: "Comic book" }],
  minWords: 1, maxWords: 8, minParts: 2, maxParts: 6, defaultParts: 4
} as unknown as StoryTypes;

function open() {
  render(<StoryDialog
    graph={testGraph()} query={{ language: "es", topic: "all", query: "", sort: "recent" }}
    deviceId="device000000001" onClose={() => undefined} onMade={() => undefined}
    onNotify={() => undefined}
  />);
}

let made: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.spyOn(backendSession, "storyTypes").mockResolvedValue(TYPES);
  made = vi.spyOn(backendSession, "makeStory").mockResolvedValue(
    { story: { id: "storynew0000001" } as Story, job: {} as Job });
});

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("the owner's guidance", () => {
  it("is sent, trimmed, when something is written in it", async () => {
    open();
    const box = await screen.findByRole("textbox", { name: /anything else/i });
    fireEvent.change(box, { target: { value: "  Tell it from the dog’s side.  " } });
    const make = screen.getByRole("button", { name: "Make the story" });
    await waitFor(() => expect(make).toBeEnabled());
    fireEvent.click(make);
    await waitFor(() => expect(made).toHaveBeenCalled());
    expect(made.mock.calls[0][0]).toMatchObject({ guidance: "Tell it from the dog’s side." });
  });

  it("is left out of the request when the box is empty", async () => {
    open();
    const make = await screen.findByRole("button", { name: "Make the story" });
    await waitFor(() => expect(make).toBeEnabled());
    fireEvent.click(make);
    await waitFor(() => expect(made).toHaveBeenCalled());
    expect(made.mock.calls[0][0]).not.toHaveProperty("guidance");
  });

  it("stops where the server would refuse", async () => {
    open();
    const box = await screen.findByRole("textbox", { name: /anything else/i });
    expect(box).toHaveAttribute("maxLength", "1000");
  });
});
