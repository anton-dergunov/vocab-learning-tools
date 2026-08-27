import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { UPDATE_EVENT } from "./pwa";

vi.mock("virtual:pwa-register", () => ({ registerSW: vi.fn() }));

describe("Acervo shell", () => {
  beforeEach(() => { delete window.webkit; });

  it("shows only the product shell and browser settings control", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "Acervo" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open settings" })).toBeInTheDocument();
  });

  it("announces and installs a waiting update explicitly", () => {
    render(<App />);
    act(() => window.dispatchEvent(new CustomEvent(UPDATE_EVENT, { detail: "ready" })));
    const gear = screen.getByRole("button", { name: "Open settings; an update is ready" });
    expect(gear).toHaveClass("has-update");
    fireEvent.click(gear);
    expect(screen.getByRole("button", { name: /Update Acervo/ })).toBeInTheDocument();
  });

  it("keeps PWA controls out of the native host", () => {
    window.webkit = { messageHandlers: { acervo: { postMessage: vi.fn() } } };
    render(<App />);
    expect(screen.queryByRole("button", { name: /Open settings/ })).not.toBeInTheDocument();
  });
});
