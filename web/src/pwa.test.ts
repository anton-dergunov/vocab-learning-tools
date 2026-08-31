import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const registerSW = vi.fn();
vi.mock("virtual:pwa-register", () => ({ registerSW }));

afterEach(() => {
  for (const name of ["userAgent", "platform", "maxTouchPoints"]) {
    delete (navigator as unknown as Record<string, unknown>)[name];
  }
  vi.unstubAllGlobals();
});

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

  it("captures and resolves the browser installation prompt", async () => {
    registerSW.mockReturnValue(vi.fn());
    const pwa = await import("./pwa");
    const prompt = vi.fn().mockResolvedValue(undefined);
    const event = Object.assign(new Event("beforeinstallprompt", { cancelable: true }), {
      prompt,
      userChoice: Promise.resolve({ outcome: "accepted" as const })
    });
    const available = vi.fn();
    window.addEventListener(pwa.INSTALL_AVAILABLE_EVENT, available, { once: true });

    pwa.registerAcervoServiceWorker();
    window.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
    expect(available).toHaveBeenCalledOnce();
    expect(pwa.canPromptInstall()).toBe(true);
    await expect(pwa.promptInstall()).resolves.toBe(true);
    expect(prompt).toHaveBeenCalledOnce();
    expect(pwa.canPromptInstall()).toBe(false);
  });

  it("does not register a service worker inside the native host", async () => {
    window.webkit = { messageHandlers: { acervo: { postMessage: vi.fn() } } };
    const pwa = await import("./pwa");
    pwa.registerAcervoServiceWorker();
    expect(registerSW).not.toHaveBeenCalled();
  });
});

describe("mobile installation detection", () => {
  beforeEach(() => {
    vi.resetModules();
    delete window.webkit;
  });

  function pretend(userAgent: string, platform: string, maxTouchPoints = 0) {
    Object.defineProperties(navigator, {
      userAgent: { value: userAgent, configurable: true },
      platform: { value: platform, configurable: true },
      maxTouchPoints: { value: maxTouchPoints, configurable: true }
    });
  }

  it("recognises iOS, iPad desktop mode, Android, and macOS", async () => {
    const pwa = await import("./pwa");
    pretend("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)", "iPhone");
    expect(pwa.detectedInstallPlatform()).toBe("ios");

    pretend("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "MacIntel", 5);
    expect(pwa.detectedInstallPlatform()).toBe("ios");

    pretend("Mozilla/5.0 (Linux; Android 15)", "Linux armv8l", 5);
    expect(pwa.detectedInstallPlatform()).toBe("android");

    pretend("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "MacIntel", 0);
    expect(pwa.detectedInstallPlatform()).toBe("macos");
  });

  it("offers the macOS application only in a macOS browser outside the native host", async () => {
    pretend("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "MacIntel", 0);
    const pwa = await import("./pwa");
    expect(pwa.shouldOfferMacApplication()).toBe(true);

    window.webkit = { messageHandlers: { acervo: { postMessage: vi.fn() } } };
    expect(pwa.shouldOfferMacApplication()).toBe(false);
    delete window.webkit;

    pretend("Mozilla/5.0 (Linux; Android 15)", "Linux armv8l", 5);
    expect(pwa.shouldOfferMacApplication()).toBe(false);
  });

  it("offers the gate only in a mobile browser that is not already installed", async () => {
    pretend("Mozilla/5.0 (Linux; Android 15)", "Linux armv8l", 5);
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false })));
    const pwa = await import("./pwa");
    expect(pwa.shouldOfferMobileInstall()).toBe(true);

    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true })));
    expect(pwa.shouldOfferMobileInstall()).toBe(false);
  });
});
