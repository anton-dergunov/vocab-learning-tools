import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { UPDATE_EVENT } from "./pwa";

vi.mock("virtual:pwa-register", () => ({ registerSW: vi.fn() }));

describe("Acervo shell", () => {
  beforeEach(() => {
    delete window.webkit;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: null }),
    }));
  });
  afterEach(() => vi.unstubAllGlobals());

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

  it("offers the native macOS release from browser settings", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: {
        version: "0.1.0",
        build: "202608270001",
        file: "Acervo.zip",
        size: 42,
        sha256: "abc",
        url: "/api/acervo/downloads/Acervo.zip",
      } }),
    } as Response);
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));
    const link = await screen.findByRole("link", { name: /Download Acervo for macOS/ });
    expect(link).toHaveAttribute("href", "/api/acervo/downloads/Acervo.zip");
    expect(link).toHaveAttribute("download", "Acervo.zip");
  });
});
