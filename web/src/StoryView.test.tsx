import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StoryView from "./StoryView";
import { testGraph } from "./testGraph";

vi.mock("./picture", () => ({
  usePicture: () => ({ url: "blob:picture", error: null })
}));

function view(overrides: Partial<Parameters<typeof StoryView>[0]> = {}) {
  const props = {
    graph: testGraph(), language: "es",
    onMake: vi.fn(), onClose: vi.fn(), onDelete: vi.fn(),
    ...overrides
  };
  return { ...render(<StoryView {...props} />), props };
}

describe("the stories surface", () => {
  it("lists a written story by its own title", () => {
    view();
    expect(screen.getByRole("button", { name: /La balsa que picaba/ })).toBeInTheDocument();
  });

  /* A story's state is derived: no parts is the whole of what "never written" means, and there is
     no status column that could disagree with it. */
  it("says a story that was asked for and never written has not been", () => {
    view();
    expect(screen.getByText(/Never written/)).toBeInTheDocument();
  });

  it("names a story that has no title by the words it was asked to teach", () => {
    view();
    // The queued story has no title, so its words stand in for one.
    expect(screen.getByRole("button", { name: /^picar/ })).toBeInTheDocument();
  });

  it("lists the words a written story was made from, in the order they were asked for", () => {
    view();
    expect(screen.getByText("la balsa · picar")).toBeInTheDocument();
  });

  it("counts a story's parts and words, and says how many pictures have been drawn", () => {
    view();
    expect(screen.getByText("2 parts · 2 words")).toBeInTheDocument();
    expect(screen.getByText("1 of 2 drawn")).toBeInTheDocument();
  });

  it("opens a written story and comes back out of it", () => {
    view();
    fireEvent.click(screen.getByRole("button", { name: /La balsa que picaba/ }));
    // Two parts, and the page of words after them.
    expect(screen.getByText("1 / 3")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Back to the stories" }));
    expect(screen.getByRole("heading", { name: "Stories" })).toBeInTheDocument();
  });

  it("does not open a story that was never written", () => {
    view();
    fireEvent.click(screen.getByRole("button", { name: /^picar/ }));
    expect(screen.getByRole("heading", { name: "Stories" })).toBeInTheDocument();
  });

  /* A surface that replaces the list has to carry the way back out of itself, at every width. */
  it("goes back to the words with the back arrow", () => {
    const { props } = view();
    fireEvent.click(screen.getByRole("button", { name: "Back to the list" }));
    expect(props.onClose).toHaveBeenCalled();
  });

  it("asks for a new story from its own header", () => {
    const { props } = view();
    fireEvent.click(screen.getByRole("button", { name: /Make a story/ }));
    expect(props.onMake).toHaveBeenCalled();
  });

  it("deletes from the right-click menu", () => {
    const { props } = view();
    fireEvent.contextMenu(screen.getByRole("button", { name: /La balsa que picaba/ }).closest(".loop-item")!);
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete this story" }));
    expect(props.onDelete).toHaveBeenCalledWith("storypicada0001");
  });

  it("says so when there are no stories at all", () => {
    view({ language: "de" });
    expect(screen.getByText(/No stories yet/)).toBeInTheDocument();
  });
});
