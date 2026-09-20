import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { VocabularyGraph } from "./domain";
import StoryReader from "./StoryReader";
import { storyPartsOf, storyWordEntries, storyWordsOf } from "./selectors";
import { testGraph } from "./testGraph";

const picture = vi.fn((reference: string | null) => ({
  url: reference ? "blob:picture" : null, error: null
}));
vi.mock("./picture", () => ({ usePicture: (reference: string | null) => picture(reference) }));

/* jsdom does no layout, so a deck that snaps under the finger has to be faked: every page is one
   hundred wide, and scrolling to an offset is a scroll event at that offset. The reader reads only
   `scrollLeft / clientWidth`, which is all a real snap track would tell it too. */
beforeEach(() => {
  picture.mockClear();
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, value: 100 });
  Element.prototype.scrollTo = function scrollTo(this: Element, options?: ScrollToOptions | number) {
    this.scrollLeft = typeof options === "object" ? options.left ?? 0 : 0;
    this.dispatchEvent(new Event("scroll"));
  } as typeof Element.prototype.scrollTo;
});

function reader(storyId = "storypicada0001", change: (graph: VocabularyGraph) => void = () => undefined) {
  const graph = testGraph();
  change(graph);
  const story = graph.stories.find((one) => one.id === storyId)!;
  const onBack = vi.fn();
  const view = render(
    <StoryReader
      story={story}
      title={story.title ?? "untitled"}
      parts={storyPartsOf(graph, storyId)}
      words={storyWordsOf(graph, storyId)}
      entries={storyWordEntries(graph, storyId)}
      onBack={onBack}
    />
  );
  return { ...view, onBack };
}

const next = () => fireEvent.click(screen.getByRole("button", { name: "The next part" }));
const previous = () => fireEvent.click(screen.getByRole("button", { name: "The part before" }));
const position = () => document.querySelector(".story-bar-count")?.textContent;
/** The translation on screen as one string: a marked word splits it across elements. */
const translation = () => document.querySelector(".story-tr")?.textContent ?? "";

describe("reading a story", () => {
  it("says which story it is and where you are in it, in the header", () => {
    reader();
    expect(document.querySelector(".story-bar-title")).toHaveTextContent("La balsa que picaba");
    // Two parts and the page of words after them.
    expect(position()).toBe("1 / 3");
  });

  it("numbers each part in front of its heading", () => {
    reader();
    expect(screen.getByRole("heading", { name: "1 · La balsa" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "2 · El picor" })).toBeInTheDocument();
  });

  it("moves to the next page and back again", () => {
    reader();
    next();
    expect(position()).toBe("2 / 3");
    previous();
    expect(position()).toBe("1 / 3");
  });

  it("cannot go back from the first page or on past the last", () => {
    reader();
    expect(screen.getByRole("button", { name: "The part before" })).toBeDisabled();
    next();
    next();
    expect(position()).toBe("3 / 3");
    expect(screen.getByRole("button", { name: "The next part" })).toBeDisabled();
  });

  it("moves with the arrow keys, but not while you are typing", () => {
    reader();
    fireEvent.keyDown(document.body, { key: "ArrowRight" });
    expect(position()).toBe("2 / 3");
    fireEvent.keyDown(document.body, { key: "ArrowLeft" });
    expect(position()).toBe("1 / 3");

    const field = document.body.appendChild(document.createElement("input"));
    fireEvent.keyDown(field, { key: "ArrowRight" });
    expect(position()).toBe("1 / 3");
    field.remove();
  });

  it("goes back with the arrow in the header", () => {
    const { onBack } = reader();
    fireEvent.click(screen.getByRole("button", { name: "Back to the stories" }));
    expect(onBack).toHaveBeenCalled();
  });

  /* The one rule this surface shares with the loop player: an answer must not be on screen before
     it has been asked for. */
  it("never draws a translation until it is asked for", () => {
    reader();
    expect(translation()).toBe("");
    fireEvent.click(screen.getAllByRole("button", { name: /read it in your own language/i })[0]);
    expect(translation()).toContain("Marcos climbed onto the raft");
  });

  it("does not reveal the next part's translation with this one's", () => {
    reader();
    fireEvent.click(screen.getAllByRole("button", { name: /read it in your own language/i })[0]);
    expect(screen.queryByText(/Something began to sting/)).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /read it in your own language/i })).toHaveLength(1);
  });

  it("keeps a revealed translation revealed when you come back to it", () => {
    reader();
    fireEvent.click(screen.getAllByRole("button", { name: /read it in your own language/i })[0]);
    next();
    previous();
    expect(translation()).toContain("Marcos climbed onto the raft");
  });

  it("marks the words the story was asked to teach", () => {
    const { container } = reader();
    const marks = Array.from(container.querySelectorAll(".story-mark")).map((one) => one.textContent);
    expect(marks).toEqual(["balsa", "picar"]);
  });

  it("marks the word in the translation too, once it has been asked for", () => {
    const { container } = reader();
    fireEvent.click(screen.getAllByRole("button", { name: /read it in your own language/i })[0]);
    const marks = Array.from(container.querySelectorAll(".story-tr .story-mark")).map((one) => one.textContent);
    expect(marks).toEqual(["raft"]);
  });

  it("shows a translation plainly when nothing was reported for it", () => {
    const { container } = reader("storypicada0001", (graph) => {
      graph.storyWords.forEach((word) => { word.translationForms = []; });
    });
    fireEvent.click(screen.getAllByRole("button", { name: /read it in your own language/i })[0]);
    expect(translation()).toContain("Marcos climbed onto the raft");
    expect(container.querySelectorAll(".story-tr .story-mark")).toHaveLength(0);
  });

  it("says a story with no parts has not been written", () => {
    reader("storyqueued0001");
    expect(screen.getByText(/has not been written yet/i)).toBeInTheDocument();
    // Nothing to move through, so nothing that pretends to.
    expect(screen.queryByRole("button", { name: "The next part" })).not.toBeInTheDocument();
  });
});

describe("the last page", () => {
  it("lists the words the story was made from as the word list draws them", () => {
    reader();
    const page = document.querySelector<HTMLElement>(".story-words-page")!;
    const rows = Array.from(page.querySelectorAll(".row"));
    expect(rows.map((row) => row.querySelector(".word")?.textContent)).toEqual(["la balsa", "picar"]);
    expect(within(rows[1] as HTMLElement).getByText("to itch; to chop")).toBeInTheDocument();
    expect(rows[1].querySelector(".plate")).toHaveTextContent("🌶️");
  });

  it("dims a word the story was asked for and could not use", () => {
    reader("storypicada0001", (graph) => {
      graph.storyWords.find((word) => word.id === "storyword000002")!.forms = [];
    });
    const rows = document.querySelectorAll(".story-words-page .row");
    expect(rows[0]).not.toHaveClass("unused");
    expect(rows[1]).toHaveClass("unused");
  });

  it("keeps a word that has been deleted since, on the words the story kept", () => {
    reader("storypicada0001", (graph) => {
      graph.lexemes = graph.lexemes.filter((lexeme) => lexeme.id !== "lexemebalsa0001");
    });
    const first = document.querySelector(".story-words-page .row")!;
    expect(first.querySelector(".word")).toHaveTextContent("la balsa");
    expect(first.querySelector(".plate")).toHaveTextContent("📄");
  });
});

describe("pictures", () => {
  it("fetches only the page in view and its neighbours", () => {
    const graph = testGraph();
    const story = graph.stories[0];
    const parts = [0, 1, 2, 3].map((index) => ({
      ...graph.storyParts[0], id: `storypart00000${index}`, position: index, imageRef: `stories/x/ref${index}.webp`
    }));
    render(<StoryReader
      story={story} title="x" parts={parts} words={[]} entries={[]} onBack={() => undefined}
    />);
    const asked = new Set(picture.mock.calls.map(([reference]) => reference).filter(Boolean));
    expect(asked).toEqual(new Set(["stories/x/ref0.webp", "stories/x/ref1.webp"]));
  });
});
