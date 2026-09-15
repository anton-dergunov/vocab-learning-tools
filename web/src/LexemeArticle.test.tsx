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
    expect(quietTitle("REDDIT DRAMA IN SPANISH 🇪🇸 FOR SPANISH LEARNERS")).toBe("reddit drama in spanish for spanish learners");
    expect(quietTitle("Top 10 1️⃣ palabras")).toBe("top 10 palabras");
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

  it("asks for a missing picture from an icon in the sense heading, with no empty frame", () => {
    const slot = pictures();
    render(<LexemeArticle article={picar()} onUnsupported={() => undefined} pictures={slot} />);
    // The cooking sense has no picture record at all.
    const cooking = document.querySelector<HTMLElement>('[data-record="sensepicarchop0"]')!;
    expect(cooking.querySelector(".sense-image")).toBeNull();
    fireEvent.click(within(cooking).getByRole("button", { name: "Add a picture" }));
    expect(slot.open).toHaveBeenCalledWith("sensepicarchop0", null);
    // A sense whose picture exists shows it, and no icon.
    const itch = document.querySelector<HTMLElement>('[data-record="sensepicaritch0"]')!;
    expect(itch.querySelector(".sense-image")).not.toBeNull();
    expect(within(itch).queryByRole("button", { name: "Add a picture" })).toBeNull();
  });

  it("shows no frame for a picture that was removed", () => {
    const graph = testGraph();
    graph.imagePrompts[0] = { ...graph.imagePrompts[0], imageRef: null, suppressed: true };
    render(<LexemeArticle article={articleFor(graph, "lexemepicar0001")!} onUnsupported={() => undefined} pictures={pictures()} />);
    const itch = document.querySelector<HTMLElement>('[data-record="sensepicaritch0"]')!;
    expect(itch.querySelector(".sense-image")).toBeNull();
    expect(within(itch).getByRole("button", { name: "Add a picture" })).toBeInTheDocument();
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

  it("shows a picture still being drawn in the page's own frame, not in place of the emoji", () => {
    const graph = testGraph();
    graph.imagePrompts[0] = { ...graph.imagePrompts[0], imageRef: null, attempts: 0 };
    const busy: PictureSlot = { open: vi.fn(), busy: () => true };
    render(<LexemeArticle article={articleFor(graph, "lexemepicar0001")!} view="cards" onUnsupported={() => undefined} pictures={busy} />);
    const itch = document.querySelector<HTMLElement>('[data-card="0"]')!;
    expect(itch.querySelector(".card-frame .sense-image-frame")).not.toBeNull();
    expect(within(itch).getByText("Drawing…")).toBeInTheDocument();
    expect(itch.querySelector(".card-tile")).toBeNull();
  });

  it("sets a card that is only words as a quotation", () => {
    const graph = testGraph();
    graph.examples.push({
      ...graph.examples.find((example) => example.id === "examplepicar010")!,
      id: "examplepicar011", origin: "tatoeba", sourceAttestationId: null,
      text: "La lana pica.", translation: "Wool itches.", matchedForm: "pica", matchedTranslationForm: "itches"
    });
    render(<LexemeArticle article={articleFor(graph, "lexemepicar0001")!} view="cards" onUnsupported={() => undefined} pictures={pictures()} />);
    const second = document.querySelector<HTMLElement>('[data-card="1"]')!;
    // Between two ivy leaves, and closed as well as opened — the marks are not part of the text.
    expect(second.querySelector(".card-main.quoted .card-ornament.above")).not.toBeNull();
    expect(second.querySelector(".card-main.quoted .card-ornament.below")).not.toBeNull();
    expect(second.querySelector(".card-ex .t")!.textContent).toBe("“La lana pica.”");
    expect([...second.querySelectorAll(".quote-mark")].every((mark) => mark.getAttribute("aria-hidden") === "true")).toBe(true);
    // The picture stays on the card of the sentence it was drawn from.
    expect(second.querySelector(".card-pic")).toBeNull();
    // The arrows are outside the track, so they can move to the margins or to the foot of the card.
    expect(document.querySelector(".cards-edges .cards-edge.next")).not.toBeNull();
  });

  it("puts a picture on the card it was drawn from, and nothing where there is none", async () => {
    render(<LexemeArticle article={picar()} view="cards" onUnsupported={() => undefined} pictures={pictures()} />);
    const itch = document.querySelector<HTMLElement>('[data-card="0"]')!;
    expect(await within(itch).findByRole("img")).toBeInTheDocument();
    // A card is for reading: the picture does not open the picture dialog.
    expect(itch.querySelector("button.card-pic")).toBeNull();
    // The cooking sense has no picture: no placeholder and no control, just its sentence as a quote.
    const cooking = document.querySelector<HTMLElement>('[data-card="1"]')!;
    expect(cooking.querySelector(".card-pic, .card-frame, .sense-image")).toBeNull();
    expect(cooking.querySelector(".card-main.quoted")).not.toBeNull();
    // Its clip is a quiet, plainly pressable line.
    expect(within(cooking).getByRole("button", { name: /Play the clip: comiendo en un mercado · easy spanish/ }))
      .toBeInTheDocument();
  });
});
