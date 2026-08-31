import { registerSW } from "virtual:pwa-register";

let installPrompt: BeforeInstallPromptEvent | undefined;

const UPDATE_CHECK_INTERVAL = 60 * 60 * 1000;
export const UPDATE_EVENT = "acervo-update";
export const INSTALL_AVAILABLE_EVENT = "acervo-install-available";
export const INSTALLED_EVENT = "acervo-installed";
export type UpdateStage = "downloading" | "ready";

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

export type InstallPlatform = "ios" | "android" | "macos" | "other";

export function detectedInstallPlatform(): InstallPlatform {
  const userAgent = navigator.userAgent || "";
  // An iPad requesting the desktop site claims to be a Mac. Touch points are what distinguish it
  // from macOS, and this check therefore has to happen before treating the device as a desktop.
  const isIPadDesktopMode = navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;
  if (/iPad|iPhone|iPod/i.test(userAgent) || isIPadDesktopMode) return "ios";
  if (/Android/i.test(userAgent)) return "android";
  if (/Mac/i.test(navigator.platform || userAgent)) return "macos";
  return "other";
}

export function isInstalledApp(): boolean {
  return window.matchMedia?.("(display-mode: standalone)").matches
    || (navigator as Navigator & { standalone?: boolean }).standalone === true
    || isNativeHost();
}

export function shouldOfferMobileInstall(): boolean {
  const platform = detectedInstallPlatform();
  return (platform === "ios" || platform === "android") && !isInstalledApp();
}

export function shouldOfferMacApplication(): boolean {
  return detectedInstallPlatform() === "macos" && !isNativeHost();
}

/**
 * Chrome stops firing its install event after installation, which otherwise makes a missing
 * install button look like a broken page. This query is not supported everywhere, so false means
 * only that the browser cannot tell.
 */
export async function alreadyInstalledOnThisDevice(): Promise<boolean> {
  const query = (navigator as Navigator & { getInstalledRelatedApps?: () => Promise<unknown[]> }).getInstalledRelatedApps;
  if (typeof query !== "function") return false;
  try { return (await query.call(navigator)).length > 0; } catch { return false; }
}

export function canPromptInstall(): boolean {
  return Boolean(installPrompt);
}

export async function promptInstall(): Promise<boolean> {
  if (!installPrompt) return false;
  const prompt = installPrompt;
  await prompt.prompt();
  const choice = await prompt.userChoice;
  installPrompt = undefined;
  return choice.outcome === "accepted";
}

let applyUpdate: ((reload?: boolean) => Promise<void>) | undefined;
let currentStage: UpdateStage | undefined;

export function isNativeHost(): boolean {
  return Boolean(window.webkit?.messageHandlers?.acervo);
}

export function updateStage(): UpdateStage | undefined {
  return currentStage;
}

function announce(stage: UpdateStage | undefined) {
  currentStage = stage;
  window.dispatchEvent(new CustomEvent(UPDATE_EVENT, { detail: stage }));
}

export async function installUpdate(): Promise<boolean> {
  if (!applyUpdate) return false;
  await applyUpdate(true);
  return true;
}

function watchInstallation(registration: ServiceWorkerRegistration) {
  const observe = (worker: ServiceWorker | null) => {
    if (!worker || !navigator.serviceWorker.controller) return;
    announce("downloading");
    worker.addEventListener("statechange", () => {
      if (worker.state === "installed") announce("ready");
      if (worker.state === "redundant") announce(undefined);
    });
  };
  observe(registration.installing);
  registration.addEventListener("updatefound", () => observe(registration.installing));
}

export function registerAcervoServiceWorker() {
  if (isNativeHost()) return;
  if (!(location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) return;
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    installPrompt = event as BeforeInstallPromptEvent;
    window.dispatchEvent(new CustomEvent(INSTALL_AVAILABLE_EVENT));
  });
  window.addEventListener("appinstalled", () => {
    installPrompt = undefined;
    window.dispatchEvent(new CustomEvent(INSTALLED_EVENT));
  });
  applyUpdate = registerSW({
    immediate: true,
    onNeedRefresh: () => announce("ready"),
    onRegisteredSW: (_url, registration) => {
      if (!registration) return;
      watchInstallation(registration);
      if (registration.waiting && navigator.serviceWorker.controller) announce("ready");
      const check = () => { registration.update().catch(() => undefined); };
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") check();
      });
      window.setInterval(check, UPDATE_CHECK_INTERVAL);
    },
    onRegisterError: (error) => console.warn("Acervo service worker registration failed", error)
  });
}
