// Runs only the spike's fidelity check. Deliberately not part of web/vitest.config, so
// `npm run test:web` never depends on downloaded dictionary data.
// Plain object rather than defineConfig: this file sits outside web/, so it cannot resolve
// `vitest/config` itself.
export default {
  test: {
    root: new URL("../../", import.meta.url).pathname,
    include: ["experiments/external-dictionaries/fidelity.test.ts"],
    environment: "node",
  },
};
