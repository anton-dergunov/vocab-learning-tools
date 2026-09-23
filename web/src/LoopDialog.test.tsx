/**
 * The make dialog's music: one "Surprise me" rather than two names for it, the styles in words, and
 * a kept bed asked for by the pair that replays it.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { backendSession, type LoopSchema } from "./api";
import LoopDialog from "./LoopDialog";
import { resetLoopSchemaForTests } from "./LoopMusic";
import { testGraph } from "./testGraph";

const SCHEMA: LoopSchema = {
  apiVersion: "1.0.0", engineVersion: "1.4.0", maxItems: 24, patterns: ["retrieval"],
  productionBundle: true,
  families: [
    { id: "sunlit-acoustic", label: "Sunlit acoustic", description: "Guitar, harp or plucked strings." },
    { id: "meditative", label: "Meditative", description: "Slow and spacious." }
  ]
};

function open() {
  const graph = testGraph();
  render(<LoopDialog
    graph={graph} query={{ language: "es", topic: "all", query: "", sort: "recent" }}
    deviceId="device000000001" onClose={() => undefined} onMade={() => undefined}
    onNotify={() => undefined}
  />);
  return graph;
}

beforeEach(() => {
  resetLoopSchemaForTests();
  vi.spyOn(backendSession, "loopSchema").mockResolvedValue(SCHEMA);
});

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("choosing the music", () => {
  it("offers Surprise me once, and every style with its description", async () => {
    open();
    await screen.findByRole("radio", { name: /meditative/i });
    expect(screen.getAllByRole("radio", { name: /surprise me/i })).toHaveLength(1);
    expect(screen.queryByRole("radio", { name: /^auto/i })).toBeNull();
    expect(screen.getByRole("radio", { name: /meditative/i })).toHaveTextContent("Slow and spacious.");
    expect(screen.getByRole("radio", { name: /surprise me/i })).toHaveAttribute("aria-checked", "true");
  });

  it("lists a kept bed first, and asks for it by its family and its seed", async () => {
    const make = vi.spyOn(backendSession, "makeLoop").mockResolvedValue({ loop: { id: "x" } as never, job: {} as never });
    open();
    const kept = await screen.findByRole("radio", { name: /sunlit acoustic.*kept/i });
    fireEvent.click(kept);
    fireEvent.click(screen.getByRole("button", { name: "Make the loop" }));
    await waitFor(() => expect(make).toHaveBeenCalled());
    expect(make.mock.calls[0][0]).toMatchObject({ family: "sunlit-acoustic", seed: 104740 });
  });

  it("asks for a style by its family alone, and for nothing when surprised", async () => {
    const make = vi.spyOn(backendSession, "makeLoop").mockResolvedValue({ loop: { id: "x" } as never, job: {} as never });
    open();
    fireEvent.click(await screen.findByRole("radio", { name: /meditative/i }));
    fireEvent.click(screen.getByRole("button", { name: "Make the loop" }));
    await waitFor(() => expect(make).toHaveBeenCalled());
    const asked = make.mock.calls[0][0];
    expect(asked.family).toBe("meditative");
    expect(asked.seed).toBeUndefined();
  });
});
