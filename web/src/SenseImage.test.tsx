import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
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

// Before rather than after: the library's own cleanup unmounts the previous test's component, and
// an unmount gives back a hold — so clearing afterwards left that release in the next test's history.
beforeEach(() => { vi.clearAllMocks(); });

describe("what a picture says about itself", () => {
  it("shows the picture with no caption, leaving the style to the dialog", () => {
    shown(prompt({ styleId: "baroque-chiaroscuro", imageModelId: "painter" }));
    expect(screen.queryByText("baroque-chiaroscuro")).toBeNull();
    expect(document.querySelector("figcaption")).toBeNull();
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

  it("does not fetch again when only the record's revision moves", async () => {
    const { acquire } = await import("./media");
    const { rerender } = render(
      <SenseImage prompt={prompt({ revision: 4 })} headword="picar" busy={false} onOpen={() => undefined} />
    );
    await waitFor(() => expect(acquire).toHaveBeenCalledTimes(1));

    rerender(
      <SenseImage prompt={prompt({ revision: 5 })} headword="picar" busy={false} onOpen={() => undefined} />
    );
    // The reference names the bytes, so a row edited without its picture changing is not a reason to
    // fetch one. The revision was a cache key once, and must not become one again.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(acquire).toHaveBeenCalledTimes(1);
  });

  it("keeps the picture it has until the redrawn one has arrived", async () => {
    const { acquire, release } = await import("./media");
    let arrive: (url: string) => void = () => undefined;
    vi.mocked(acquire)
      .mockResolvedValueOnce("blob:first")
      .mockImplementationOnce(() => new Promise((resolve) => { arrive = resolve; }));

    const { rerender } = render(
      <SenseImage prompt={prompt({ imageRef: "images/a/one-1111.webp" })} headword="picar" busy={false} onOpen={() => undefined} />
    );
    await waitFor(() => expect(screen.getByRole("img").getAttribute("src")).toBe("blob:first"));

    rerender(
      <SenseImage prompt={prompt({ imageRef: "images/a/one-2222.webp" })} headword="picar" busy onOpen={() => undefined} />
    );
    // Still the old picture, under the mark: the frame never blanks between two pictures.
    expect(screen.getByRole("img").getAttribute("src")).toBe("blob:first");
    expect(release).not.toHaveBeenCalled();

    arrive("blob:second");
    await waitFor(() => expect(screen.getByRole("img").getAttribute("src")).toBe("blob:second"));
    // The hand-over: the old hold is given back, and only once the new picture is on screen.
    expect(release).toHaveBeenCalledTimes(1);
    expect(release).toHaveBeenCalledWith("images/a/one-1111.webp");
  });

  it("gives every hold back exactly once when it is unmounted mid-fetch", async () => {
    const { acquire, release } = await import("./media");
    let arrive: (url: string) => void = () => undefined;
    vi.mocked(acquire).mockImplementationOnce(() => new Promise((resolve) => { arrive = resolve; }));

    const { unmount } = render(
      <SenseImage prompt={prompt({ imageRef: "images/a/one-1111.webp" })} headword="picar" busy={false} onOpen={() => undefined} />
    );
    unmount();
    arrive("blob:late");
    await waitFor(() => expect(release).toHaveBeenCalledTimes(1));
    // The hold the run took, given back by the arrival that found itself stale — not twice, which
    // would revoke a URL another component is showing, and not never, which would leak it.
    expect(release).toHaveBeenCalledWith("images/a/one-1111.webp");
  });

  it("blanks at once when the picture is taken away", async () => {
    const { release } = await import("./media");
    const { rerender } = render(
      <SenseImage prompt={prompt({ imageRef: "images/a/one-1111.webp" })} headword="picar" busy={false} onOpen={() => undefined} />
    );
    await waitFor(() => expect(screen.getByRole("img")).toBeTruthy());

    rerender(
      <SenseImage prompt={prompt({ imageRef: null, imageModelId: null })} headword="picar" busy={false} onOpen={() => undefined} />
    );
    expect(screen.queryByRole("img")).toBeNull();
    expect(release).toHaveBeenCalledWith("images/a/one-1111.webp");
  });
});
