/**
 * Make a story: the owner's own note to the writer travels with the request, trimmed, and only when
 * something was written in it.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { backendSession, type Job, type StoryTypes } from "./api";
import type { Story } from "./domain";
import StoryDialog from "./StoryDialog";
import { selectedWords } from "./selectors";
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

describe("the words", () => {
  it("draws from the words a story can use, not only the ones a loop can", async () => {
    // The Inbox holds one word, espolvorear, which has no single term to say: a loop can use none of
    // it, a story can. Drawing from a loop's words sent a story no words at all.
    render(<StoryDialog
      graph={testGraph()} query={{ language: "es", topic: "inbox", query: "", sort: "recent" }}
      deviceId="device000000001" onClose={() => undefined} onMade={() => undefined}
      onNotify={() => undefined}
    />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Make the story" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Make the story" }));
    await waitFor(() => expect(made).toHaveBeenCalled());
    expect(made.mock.calls[0][0].lexemeIds).toEqual(["lexemeespolv001"]);
  });

  it("sends the selection as chosen when opened from it", async () => {
    const graph = testGraph();
    render(<StoryDialog
      graph={graph} query={{ language: "es", topic: "all", query: "", sort: "recent" }}
      selection={selectedWords(graph, "es", ["lexemeespolv001", "lexemepicar0001"])} from="selection"
      deviceId="device000000001" onClose={() => undefined} onMade={() => undefined}
      onNotify={() => undefined}
    />);
    const go = await screen.findByRole("button", { name: "Make the story from 2 words" });
    await waitFor(() => expect(go).toBeEnabled());
    fireEvent.click(go);
    await waitFor(() => expect(made).toHaveBeenCalled());
    expect(made.mock.calls[0][0].lexemeIds).toEqual(["lexemeespolv001", "lexemepicar0001"]);
  });
});
