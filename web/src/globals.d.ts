/// <reference types="vite/client" />

declare const __APP_VERSION__: string;
declare const __APP_BUILD__: string;

declare module "virtual:pwa-register" {
  export interface RegisterSWOptions {
    immediate?: boolean;
    onNeedRefresh?: () => void;
    onRegisteredSW?: (url: string, registration: ServiceWorkerRegistration | undefined) => void;
    onRegisterError?: (error: unknown) => void;
  }
  export function registerSW(options?: RegisterSWOptions): (reloadPage?: boolean) => Promise<void>;
}

/** What the macOS menu bar can ask the interface to open. */
type AcervoCommand = "export" | "import" | "delete";

interface Window {
  acervo?: { command(name: AcervoCommand): void };
  webkit?: {
    messageHandlers?: {
      acervo?: { postMessage(message: unknown): Promise<unknown> };
    };
  };
}
