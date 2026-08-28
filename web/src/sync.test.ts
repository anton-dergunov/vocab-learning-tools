import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AcervoApiError, backendSession } from "./api";
import { repository } from "./repository";
import { pullGraph } from "./sync";
import { TEST_OWNER, testGraph } from "./testGraph";

const response = () => ({ ...testGraph(), syncedAt: "2026-08-28T12:00:00.000Z" });

describe("graph pull", () => {
  beforeEach(async () => {
    await repository.clear();
    await repository.load(TEST_OWNER);
  });
  afterEach(() => vi.restoreAllMocks());

  it("fills the replica from the owner's records on the server", async () => {
    vi.spyOn(backendSession, "fetchGraph").mockResolvedValue(response());
    await expect(pullGraph()).resolves.toBe("2026-08-28T12:00:00.000Z");
    const snapshot = repository.snapshot();
    expect(snapshot.lexemes).toHaveLength(4);
    expect(snapshot.senses).toHaveLength(5);
    // A pull is not a local write, so nothing is queued for sending back.
    expect(snapshot.pendingCount).toBe(0);
  });

  it("replaces records the server no longer sends", async () => {
    vi.spyOn(backendSession, "fetchGraph").mockResolvedValue(response());
    await pullGraph();
    const trimmed = response();
    trimmed.lexemes = trimmed.lexemes.filter((lexeme) => lexeme.id !== "lexemeturmoil01");
    trimmed.senses = trimmed.senses.filter((sense) => sense.lexemeId !== "lexemeturmoil01");
    vi.spyOn(backendSession, "fetchGraph").mockResolvedValue(trimmed);
    await pullGraph();
    expect(repository.snapshot().lexemes.map((lexeme) => lexeme.id)).not.toContain("lexemeturmoil01");
  });

  it("keeps an unsent local tombstone through a pull that still carries the record", async () => {
    vi.spyOn(backendSession, "fetchGraph").mockResolvedValue(response());
    await pullGraph();
    await repository.delete("lexemes", "lexemebalsa0001");
    expect(repository.snapshot().pendingCount).toBeGreaterThan(0);
    await pullGraph();
    const balsa = repository.snapshot().lexemes.find((lexeme) => lexeme.id === "lexemebalsa0001");
    expect(balsa?.deleted).toBe(true);
  });

  it("leaves the replica intact when the server cannot be reached", async () => {
    vi.spyOn(backendSession, "fetchGraph").mockResolvedValue(response());
    await pullGraph();
    vi.spyOn(backendSession, "fetchGraph")
      .mockRejectedValue(new AcervoApiError("The Acervo server could not be reached.", 0, "offline"));
    await expect(pullGraph()).rejects.toThrow("could not be reached");
    expect(repository.snapshot().lexemes).toHaveLength(4);
  });

  it("refuses records belonging to another account", async () => {
    const foreign = response();
    foreign.topics[0].ownerId = "owner0000000002";
    vi.spyOn(backendSession, "fetchGraph").mockResolvedValue(foreign);
    await expect(pullGraph()).rejects.toThrow("one owner only");
    expect(repository.snapshot().lexemes).toHaveLength(0);
  });
});
