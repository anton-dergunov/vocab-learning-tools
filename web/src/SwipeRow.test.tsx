/**
 * One row for words, loops and stories: a right-click opens the same actions a swipe reveals, a
 * press elsewhere puts the menu away, and a danger action gets a rule above it.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SwipeRow from "./SwipeRow";

afterEach(cleanup);

function row() {
  const pick = vi.fn();
  const drop = vi.fn();
  render(<SwipeRow actions={[
    { label: "Select", menuLabel: "Add to selection", tone: "pick", run: pick },
    { label: "Delete", menuLabel: "Delete this word", tone: "danger", run: drop }
  ]}><button>picar</button></SwipeRow>);
  return { pick, drop };
}

describe("a row with actions", () => {
  it("offers its actions behind the row, for a swipe", () => {
    const { pick, drop } = row();
    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(pick).toHaveBeenCalledOnce();
    expect(drop).toHaveBeenCalledOnce();
  });

  it("opens the same actions under the pointer on a right-click, with a rule above Delete", () => {
    const { pick } = row();
    fireEvent.contextMenu(screen.getByRole("button", { name: "picar" }), { clientX: 40, clientY: 12 });
    const menu = screen.getByRole("menu");
    expect(menu.querySelector(".menu-sep")).not.toBeNull();
    fireEvent.pointerDown(screen.getByRole("menuitem", { name: "Add to selection" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Add to selection" }));
    expect(pick).toHaveBeenCalledOnce();
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("puts the menu away on a press elsewhere, or on Escape", () => {
    const { drop } = row();
    fireEvent.contextMenu(screen.getByRole("button", { name: "picar" }));
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("menu")).toBeNull();
    fireEvent.contextMenu(screen.getByRole("button", { name: "picar" }));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(drop).not.toHaveBeenCalled();
  });
});
