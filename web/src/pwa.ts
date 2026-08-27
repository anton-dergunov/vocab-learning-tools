import { registerSW } from "virtual:pwa-register";

const UPDATE_CHECK_INTERVAL = 60 * 60 * 1000;
export const UPDATE_EVENT = "acervo-update";
export type UpdateStage = "downloading" | "ready";

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
