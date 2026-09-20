import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FitWords, { fitWords } from "./FitWords";

describe("how many whole words fit", () => {
  // Four words 40, 100, 70 and 60 wide, a separator 30 wide and an ellipsis 10 wide.
  const widths = [40, 100, 70, 60];
  const fit = (available: number) => fitWords(widths, 30, 10, available);

  it("keeps every word when they all fit", () => {
    // 270 of words and three separators of 30.
    expect(fit(400)).toBe(4);
  });

  it("counts the words to the exact pixel", () => {
    expect(fit(360)).toBe(4);
    expect(fit(359)).toBe(3);
  });

  it("gives up whole words from the end, and keeps room for the ellipsis that says so", () => {
    // Three words are 210 wide, and `· …` after them is 40 more.
    expect(fit(310)).toBe(3);
    expect(fit(309)).toBe(2);
    expect(fit(209)).toBe(1);
  });

  it("always keeps the first word, even when it alone is too wide", () => {
    // Showing nothing says less than showing part of the only thing there is; CSS trims it.
    expect(fit(10)).toBe(1);
  });

  it("has nothing to keep when there are no words", () => {
    expect(fitWords([], 30, 10, 200)).toBe(0);
  });
});

describe("the line of words", () => {
  const WORDS = ["numb", "shoestring", "burgeon", "savory"];

  beforeEach(() => {
    // Ten pixels a character, so the widths above follow from the text itself.
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
      return { width: (this.textContent ?? "").length * 10 } as DOMRect;
    });
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    // A stubbed getter is defined on the prototype, so it is removed rather than restored.
    delete (HTMLElement.prototype as { clientWidth?: number }).clientWidth;
  });

  function withLayout(lineWidth: number) {
    vi.stubGlobal("ResizeObserver", class { observe() { /* measured once up front */ } disconnect() { /* nothing */ } });
    Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, value: lineWidth });
  }

  it("shows every word, joined, as one piece of text, where there is no layout to measure", () => {
    const { container } = render(<FitWords words={WORDS} />);
    expect(container.firstElementChild?.firstChild?.textContent).toBe("numb · shoestring · burgeon · savory");
  });

  it("cuts at a word and says there is more", () => {
    // 260 wide: `numb · shoestring` is 170, and `· …` after it is 40 more; a third word does not fit.
    withLayout(260);
    const { container } = render(<FitWords words={WORDS} />);
    expect(container.firstElementChild?.firstChild?.textContent).toBe("numb · shoestring · …");
  });

  it("keeps the whole list where the line is wide enough", () => {
    withLayout(600);
    const { container } = render(<FitWords words={WORDS} />);
    expect(container.firstElementChild?.firstChild?.textContent).toBe("numb · shoestring · burgeon · savory");
  });

  it("puts the whole list in the tooltip however much of it is showing", () => {
    withLayout(260);
    const { container } = render(<FitWords words={WORDS} />);
    expect(container.firstElementChild).toHaveAttribute("title", "numb, shoestring, burgeon, savory");
  });
});
