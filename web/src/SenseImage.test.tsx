import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ImagePrompt } from "./domain";
import { SenseImage, yours } from "./SenseImage";
import { testGraph } from "./testGraph";

/** The bytes come from an authenticated route; what the frame says about them is what is tested. */
vi.mock("./media", () => ({
  acquire: vi.fn(async () => "blob:picture"),
  release: vi.fn()
}));

const prompt = (overrides: Partial<ImagePrompt> = {}): ImagePrompt =>
  ({ ...testGraph().imagePrompts[0], ...overrides });

function shown(record: ImagePrompt, busy = false) {
  render(<SenseImage prompt={record} headword="picar" busy={busy} onOpen={() => undefined} />);
}

afterEach(() => { vi.clearAllMocks(); });

describe("what a picture's caption claims", () => {
  it("names the style that drew it", () => {
    shown(prompt({ styleId: "baroque-chiaroscuro", imageModelId: "painter" }));
    expect(screen.getByText("baroque-chiaroscuro")).toBeTruthy();
  });

  it("says a picture is yours instead of naming a style it was never drawn in", () => {
    // The record keeps its `styleId` on purpose — the brief and style are what a later Draw works
    // from — so the caption is the only thing that can stop it reading as a description of *this*
    // picture. "baroque-chiaroscuro yours" was the record leaking through.
    shown(prompt({ styleId: "baroque-chiaroscuro", imageModelId: null }));
    expect(screen.getByText("your own picture")).toBeTruthy();
    expect(screen.queryByText("baroque-chiaroscuro")).toBeNull();
  });

  it("knows a supplied picture from a drawn one by the absence of a rendering model", () => {
    expect(yours(prompt({ imageModelId: null }))).toBe(true);
    expect(yours(prompt({ imageModelId: "painter" }))).toBe(false);
    // Not "yours" merely for having no model: a row with no picture at all has neither.
    expect(yours(prompt({ imageRef: null, imageModelId: null }))).toBe(false);
  });
});

describe("what a picture shows while it is being replaced", () => {
  it("keeps the old picture visible under a mark rather than blanking it", async () => {
    shown(prompt({ imageModelId: "painter" }), true);
    await waitFor(() => expect(screen.getByRole("img")).toBeTruthy());
    // The old picture is what is being reconsidered, and Draw closes the dialog — so this mark is
    // the only thing that says the work was taken.
    expect(screen.getByText("Redrawing…")).toBeTruthy();
  });

  it("says it is drawing when there is nothing there yet", () => {
    shown(prompt({ imageRef: null, imageModelId: null }), true);
    expect(screen.getByText("Drawing…")).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("fetches again when the record changes, because the path never does", async () => {
    const { acquire } = await import("./media");
    const { rerender } = render(
      <SenseImage prompt={prompt({ revision: 4 })} headword="picar" busy={false} onOpen={() => undefined} />
    );
    await waitFor(() => expect(acquire).toHaveBeenCalledTimes(1));

    rerender(
      <SenseImage prompt={prompt({ revision: 5 })} headword="picar" busy={false} onOpen={() => undefined} />
    );
    // A redrawn picture keeps the same `imageRef` — it is derived from the record — so the revision
    // is what tells the frame to look again. Without it the article kept the replaced picture until
    // it happened to remount, which is what "close the word and open it again" was working around.
    await waitFor(() => expect(acquire).toHaveBeenCalledTimes(2));
  });
});
