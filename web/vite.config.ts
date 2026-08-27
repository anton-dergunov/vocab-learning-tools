import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

const repositoryPackage = JSON.parse(
  readFileSync(fileURLToPath(new URL("../package.json", import.meta.url)), "utf8")
) as { version?: string };
const appVersion = process.env.ACERVO_APP_VERSION || repositoryPackage.version || "0.0.0";
const appBuild = process.env.ACERVO_APP_BUILD
  || new Date().toISOString().replace(/[-:T]/g, "").slice(0, 12);

export default defineConfig({
  publicDir: fileURLToPath(new URL("../assets/brand/acervo/dist", import.meta.url)),
  plugins: [react(), VitePWA({
    registerType: "prompt",
    injectRegister: false,
    includeAssets: [
      "favicon.ico",
      "favicon-16.png",
      "favicon-32.png",
      "apple-touch-icon.png"
    ],
    manifest: {
      name: "Acervo",
      short_name: "Acervo",
      description: "A personal vocabulary workspace.",
      theme_color: "#071a38",
      background_color: "#f7f3e8",
      display: "standalone",
      start_url: ".",
      scope: ".",
      icons: [
        { src: "pwa-icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
        { src: "pwa-icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
        { src: "pwa-maskable-192.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
        { src: "pwa-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" }
      ]
    },
    workbox: {
      globPatterns: ["**/*.{html,js,css,svg,png,ico,woff,woff2,webmanifest}"],
      navigateFallback: "index.html",
      navigateFallbackDenylist: [/^\/api\//, /^\/_\//],
      runtimeCaching: []
    }
  })],
  define: {
    __APP_VERSION__: JSON.stringify(appVersion),
    __APP_BUILD__: JSON.stringify(appBuild)
  },
  base: "./",
  experimental: {
    renderBuiltUrl(filename, { hostType }) {
      return hostType === "js" ? `./${filename}` : { relative: true };
    }
  },
  build: { outDir: "dist", emptyOutDir: true },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/testSetup.ts"] }
});
