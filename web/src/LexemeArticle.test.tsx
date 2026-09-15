import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LexemeArticle, { looseAttestations, quietTitle, type PictureSlot } from "./LexemeArticle";
import { articleFor } from "./selectors";
import { testGraph } from "./testGraph";

/* The bytes come from an authenticated route; what the article does with them is what is tested. */
vi.mock("./media", () => ({
  acquire: vi.fn(async () => "blob:picture"),
  release: vi.fn()
}));
vi.mock("./dictionaries", () => ({ lookup: vi.fn(async () => []) }));

const picar = () => articleFor(testGraph(), "lexemepicar0001")!;
const pictures = (): PictureSlot => ({ open: vi.fn(), busy: () => false });
/** Whether some paragraph reads exactly this, however emphasis has split it across elements. */
const reads = (text: string, root: ParentNode = document) =>
  [...root.querySelectorAll("p")].some((paragraph) => paragraph.textContent === text);

afterEach(() => { vi.clearAllMocks(); });

describe("a clip's title", () => {
  it("is made quiet by rule: no hashtags, no emoji, all lower case", () => {
    expect(quietTitle("#NADIEDICENADA | CONOCEMOS A MARTA, LA SEÑORA QUE ESTÁ POR CUMPLIR 101 AÑOS"))
      .toBe("conocemos a marta, la señora que está por cumplir 101 años");
    expect(quietTitle("En este pueblo humanos tienen prohibido vivir 🚫")).toBe("en este pueblo humanos tienen prohibido vivir");
    expect(quietTitle("Comiendo en un mercado 🌮🔥 #mexico #streetfood")).toBe("comiendo en un mercado");
  });
});

describe("the page", () => {
  it("keeps a sentence you supplied out of where you met it, since it is already in its sense", () => {
    expect(looseAttestations(picar())).toEqual([]);
  });

  it("folds each section on its own, and starts Details folded", () => {
    render(<LexemeArticle article={picar()} onUnsupported={() => undefined} />);
    const details = screen.getByText("Details").closest("button")!;
    expect(details.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("demo-model")).toBeNull();

    fireEvent.click(details);
    expect(details.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText(/demo-painter/)).toBeInTheDocument();

    // Folding a sense hides its body and nothing else.
    const sense = screen.getByText("🔪 cooking").closest("button")!;
    fireEvent.click(sense);
    expect(reads("Chop the onion very finely.")).toBe(false);
    expect(reads("My nose itches.")).toBe(true);
  });

  it("plays nothing yet, and says so rather than failing silently", () => {
    const told = vi.fn();
    render(<LexemeArticle article={picar()} onUnsupported={told} />);
    fireEvent.click(screen.getByRole("button", { name: "Listen to picar" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Listen" })[0]);
    expect(told).toHaveBeenCalledTimes(2);
  });
});

describe("cards", () => {
  it("gives each sense a card per sentence, then the sections after them", () => {
    render(<LexemeArticle article={picar()} view="cards" onUnsupported={() => undefined} pictures={pictures()} />);
    const nav = within(screen.getByRole("navigation", { name: "Senses and sections" }));
    // A sense with no label is its number; one with a label shows its emoji and the label.
    expect(nav.getByRole("button", { name: "1" })).toBeInTheDocument();
    expect(nav.getByRole("button", { name: "🔪 cooking" })).toBeInTheDocument();
    expect(nav.getByRole("button", { name: "Details" })).toBeInTheDocument();
    // picar's two senses have one sentence each, then its notes, then the two asides.
    expect(nav.getByRole("button", { name: "✎ Notes" })).toBeInTheDocument();
    expect(document.querySelectorAll(".card")).toHaveLength(5);
    // No ask anchors on a card: a conversation edits the whole entry, which is read on the page.
    expect(document.querySelector(".ask-anchor")).toBeNull();
  });

  it("keeps the definition on the card with its sentence and marks your own", () => {
    render(<LexemeArticle article={picar()} view="cards" onUnsupported={() => undefined} pictures={pictures()} />);
    const first = document.querySelector<HTMLElement>('[data-card="0"]')!;
    expect(reads("My nose itches.", first)).toBe(true);
    expect(first.querySelector(".card-def")!.textContent).toBe("Producir comezón.");
    expect(within(first).getByText("your sentence")).toBeInTheDocument();
  });

  it("puts a picture on the card of the sentence it was drawn from, and an emoji where there is none", async () => {
    render(<LexemeArticle article={picar()} view="cards" onUnsupported={() => undefined} pictures={pictures()} />);
    const itch = document.querySelector<HTMLElement>('[data-card="0"]')!;
    expect(await within(itch).findByRole("img")).toBeInTheDocument();
    // The cooking sense has no picture, so it opens on its own emoji rather than empty paper.
    const cooking = document.querySelector<HTMLElement>('[data-card="1"]')!;
    expect(cooking.querySelector(".card-tile")!.textContent).toContain("🔪");
    // Its clip is a quiet, plainly pressable line.
    expect(within(cooking).getByRole("button", { name: /Play the clip: comiendo en un mercado · easy spanish/ }))
      .toBeInTheDocument();
  });
});
