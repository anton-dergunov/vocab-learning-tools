/**
 * The selection is this device's: per language, in the order the words were chosen, under the
 * account it was made in, and a convenience that storage refusing must not break.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearSelected, reloadSelectionForTests, restoreSelected, selectedIds, toggleSelected
} from "./wordSelection";

const OWNER = "ownertest000001";

beforeEach(() => { localStorage.clear(); reloadSelectionForTests(); });
afterEach(() => vi.restoreAllMocks());

describe("the selection", () => {
  it("keeps words in the order they were chosen, one selection per language", () => {
    toggleSelected(OWNER, "es", "lexemebalsa0001");
    toggleSelected(OWNER, "es", "lexemepicar0001");
    toggleSelected(OWNER, "en", "lexemeturmoil01");
    expect(selectedIds(OWNER, "es")).toEqual(["lexemebalsa0001", "lexemepicar0001"]);
    expect(selectedIds(OWNER, "en")).toEqual(["lexemeturmoil01"]);
  });

  it("takes a word out when it is toggled again, and says which way it went", () => {
    expect(toggleSelected(OWNER, "es", "lexemepicar0001")).toBe(true);
    expect(toggleSelected(OWNER, "es", "lexemepicar0001")).toBe(false);
    expect(selectedIds(OWNER, "es")).toEqual([]);
  });

  it("survives a reload, because it is kept in this device's storage", () => {
    toggleSelected(OWNER, "es", "lexemepicar0001");
    reloadSelectionForTests();
    expect(selectedIds(OWNER, "es")).toEqual(["lexemepicar0001"]);
  });

  it("is empty for another account, whose first choice replaces it", () => {
    toggleSelected(OWNER, "es", "lexemepicar0001");
    expect(selectedIds("owneranother001", "es")).toEqual([]);
    toggleSelected("owneranother001", "en", "lexemeturmoil01");
    expect(selectedIds(OWNER, "es")).toEqual([]);
    expect(selectedIds("owneranother001", "en")).toEqual(["lexemeturmoil01"]);
  });

  it("clears one language and puts it back exactly, for Undo", () => {
    toggleSelected(OWNER, "es", "lexemebalsa0001");
    toggleSelected(OWNER, "es", "lexemepicar0001");
    toggleSelected(OWNER, "en", "lexemeturmoil01");
    const before = clearSelected(OWNER, "es");
    expect(selectedIds(OWNER, "es")).toEqual([]);
    expect(selectedIds(OWNER, "en")).toEqual(["lexemeturmoil01"]);
    restoreSelected(OWNER, "es", before);
    expect(selectedIds(OWNER, "es")).toEqual(["lexemebalsa0001", "lexemepicar0001"]);
  });

  it("goes on working for this session when storage refuses to hold it", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota"); });
    toggleSelected(OWNER, "es", "lexemepicar0001");
    expect(selectedIds(OWNER, "es")).toEqual(["lexemepicar0001"]);
  });

  it("reads an unreadable record as an empty selection", () => {
    localStorage.setItem("acervo-word-selection", "{not json");
    reloadSelectionForTests();
    expect(selectedIds(OWNER, "es")).toEqual([]);
  });
});
