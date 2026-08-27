import { beforeEach, describe, expect, it, vi } from "vitest";

const registerSW = vi.fn();
vi.mock("virtual:pwa-register", () => ({ registerSW }));

describe("PWA registration", () => {
  beforeEach(() => {
    vi.resetModules();
    registerSW.mockReset();
    delete window.webkit;
  });

  it("uses prompt-based update installation", async () => {
    const apply = vi.fn().mockResolvedValue(undefined);
    registerSW.mockReturnValue(apply);
    const pwa = await import("./pwa");
    pwa.registerAcervoServiceWorker();
    expect(registerSW).toHaveBeenCalledOnce();
    const options = registerSW.mock.calls[0][0];
    options.onNeedRefresh();
    expect(pwa.updateStage()).toBe("ready");
    await expect(pwa.installUpdate()).resolves.toBe(true);
    expect(apply).toHaveBeenCalledWith(true);
  });

  it("does not register a service worker inside the native host", async () => {
    window.webkit = { messageHandlers: { acervo: { postMessage: vi.fn() } } };
    const pwa = await import("./pwa");
    pwa.registerAcervoServiceWorker();
    expect(registerSW).not.toHaveBeenCalled();
  });
});
