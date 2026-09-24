import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { backendSession } from "./api";
import { ImageDialog } from "./ImageDialog";
import { testGraph } from "./testGraph";

vi.mock("./media", () => ({ acquire: vi.fn(async () => "blob:picture"), release: vi.fn() }));

afterEach(() => { vi.restoreAllMocks(); });

const row = () => testGraph().imagePrompts[0];
const STYLES = [{ id: "flat-vector", label: "Flat vector", mono: false, photographic: false }, { id: "ukiyo-e", label: "Ukiyo-e", mono: false, photographic: false }];

function dialog(overrides: Partial<Parameters<typeof ImageDialog>[0]> = {}) {
  const props = {
    prompt: row(), headword: "picar", styles: STYLES, briefing: false,
    onClose: vi.fn(), onRebrief: vi.fn(), onDraw: vi.fn(), onAttach: vi.fn(), onRemove: vi.fn(),
    ...overrides
  };
  return { props, view: render(<ImageDialog {...props} />) };
}

describe("the picture dialog", () => {
  it("shows the whole prompt the server composes for the row", async () => {
    vi.spyOn(backendSession, "imagePrompt").mockResolvedValue({
      ...row(), composedPrompt: "A hand hovering near an itchy nose — flat vector, no text."
    } as never);
    dialog();
    expect(await screen.findByText(/flat vector, no text\./)).toBeInTheDocument();
  });

  it("asks for a new brief as a job and says so while it is written", () => {
    vi.spyOn(backendSession, "imagePrompt").mockRejectedValue(new Error("offline"));
    const { props, view } = dialog();
    fireEvent.click(screen.getByRole("button", { name: "Write a new brief" }));
    expect(props.onRebrief).toHaveBeenCalledTimes(1);

    view.rerender(<ImageDialog {...props} briefing />);
    expect(screen.getByRole("button", { name: "Writing…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Draw" })).toBeDisabled();
  });

  it("takes the new brief into the field when it lands", async () => {
    vi.spyOn(backendSession, "imagePrompt").mockRejectedValue(new Error("offline"));
    const { props, view } = dialog();
    view.rerender(<ImageDialog {...props} prompt={{ ...row(), prompt: "A rewritten scene.", styleId: "ukiyo-e", revision: 99 }} />);
    await waitFor(() => expect(screen.getByDisplayValue("A rewritten scene.")).toBeInTheDocument());
  });

  it("hands an edited brief to the caller and closes", () => {
    vi.spyOn(backendSession, "imagePrompt").mockRejectedValue(new Error("offline"));
    const { props } = dialog();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "An onion on a board." } });
    fireEvent.click(screen.getByRole("button", { name: "Draw" }));
    expect(props.onDraw).toHaveBeenCalledWith({ prompt: "An onion on a board.", styleId: "flat-vector" });
    expect(props.onClose).toHaveBeenCalled();
  });
});
