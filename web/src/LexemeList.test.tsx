/**
 * A word's row offers the selection and Delete by right-click or by swipe, and a selected word wears
 * its mark in the list.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LexemeList from "./LexemeList";
import { visibleRows } from "./selectors";
import { testGraph } from "./testGraph";

afterEach(cleanup);

function list(selected: string[] = []) {
  const rows = visibleRows(testGraph(), { language: "es", topic: "all", query: "", sort: "alpha" });
  const handlers = { onOpen: vi.fn(), onToggleSelected: vi.fn(), onDelete: vi.fn() };
  render(<LexemeList
    rows={rows} languageName="Spanish" topic="all" topicLabel="All words" topicIcon="📖" query=""
    sort="alpha" onSort={() => undefined} selected={(id) => selected.includes(id)} {...handlers}
  />);
  return handlers;
}

describe("a word's row", () => {
  it("puts the word in the selection from its right-click menu", () => {
    const { onToggleSelected } = list();
    fireEvent.contextMenu(screen.getByRole("button", { name: /picar/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Add to selection" }));
    expect(onToggleSelected).toHaveBeenCalledWith("lexemepicar0001");
  });

  it("offers Unselect and Delete behind a selected row, and wears the selection's mark", () => {
    const { onToggleSelected, onDelete } = list(["lexemepicar0001"]);
    expect(screen.getAllByRole("img", { name: "Selected" })).toHaveLength(1);
    expect(screen.getByRole("button", { name: /picar/ })).toHaveClass("picked");
    fireEvent.click(screen.getByRole("button", { name: "Unselect" }));
    expect(onToggleSelected).toHaveBeenCalledWith("lexemepicar0001");
    fireEvent.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    expect(onDelete).toHaveBeenCalledWith("lexemebalsa0001");
  });
});
