import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StoryReader from "./StoryReader";
import { storyPartsOf, storyWordsOf } from "./selectors";
import { testGraph } from "./testGraph";

vi.mock("./picture", () => ({
  usePicture: () => ({ url: "blob:picture", error: null })
}));

/** The part on screen, as one string. The text is split into spans wherever a word is marked, so
 *  no single element holds the whole sentence. */
function shown(): string {
  return document.querySelector(".story-text")?.textContent ?? "";
}

function reader(storyId = "storypicada0001") {
  const graph = testGraph();
  const story = graph.stories.find((one) => one.id === storyId)!;
  return render(
    <StoryReader
      story={story}
      parts={storyPartsOf(graph, storyId)}
      words={storyWordsOf(graph, storyId)}
    />
  );
}

describe("reading a story", () => {
  it("shows one part at a time, not the whole story", () => {
    reader();
    expect(shown()).toContain("Marcos subió a la balsa");
    expect(shown()).not.toContain("Algo empezó a picar");
    expect(screen.getByText("1 of 2")).toBeInTheDocument();
  });

  it("moves to the next part and back again", () => {
    reader();
    fireEvent.click(screen.getByRole("button", { name: "The next part" }));
    expect(shown()).toContain("Algo empezó a picar");
    expect(screen.getByText("2 of 2")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "The part before" }));
    expect(shown()).toContain("Marcos subió a la balsa");
  });

  it("cannot go back from the first part or on past the last", () => {
    reader();
    expect(screen.getByRole("button", { name: "The part before" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "The next part" }));
    expect(screen.getByRole("button", { name: "The next part" })).toBeDisabled();
  });

  /* The one rule this surface shares with the loop player: an answer must not be on screen before
     it has been asked for. */
  it("never draws the translation until it is asked for", () => {
    reader();
    expect(screen.queryByText(/Marcos climbed onto the raft/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /read it in your own language/i }));
    expect(screen.getByText(/Marcos climbed onto the raft/)).toBeInTheDocument();
  });

  it("does not reveal the next part's translation with this one's", () => {
    reader();
    fireEvent.click(screen.getByRole("button", { name: /read it in your own language/i }));
    fireEvent.click(screen.getByRole("button", { name: "The next part" }));
    expect(screen.queryByText(/Something began to sting/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /read it in your own language/i })).toBeInTheDocument();
  });

  it("keeps a revealed translation revealed when you come back to it", () => {
    reader();
    fireEvent.click(screen.getByRole("button", { name: /read it in your own language/i }));
    fireEvent.click(screen.getByRole("button", { name: "The next part" }));
    fireEvent.click(screen.getByRole("button", { name: "The part before" }));
    expect(screen.getByText(/Marcos climbed onto the raft/)).toBeInTheDocument();
  });

  it("marks the words the story was asked to teach", () => {
    const { container } = reader();
    fireEvent.click(screen.getByRole("button", { name: "The next part" }));
    const marks = Array.from(container.querySelectorAll(".story-mark")).map((one) => one.textContent);
    expect(marks).toEqual(["picar"]);
  });

  it("moves with the arrow keys", () => {
    reader();
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(screen.getByText("2 of 2")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(screen.getByText("1 of 2")).toBeInTheDocument();
  });

  it("says a story with no parts has not been written", () => {
    reader("storyqueued0001");
    expect(screen.getByText(/has not been written yet/i)).toBeInTheDocument();
  });
});
