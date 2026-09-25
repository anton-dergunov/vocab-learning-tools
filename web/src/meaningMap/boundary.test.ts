/* The meaning map imports nothing of Acervo's.

   That is what lets it move to the discovery repository and come back as a package, the way the
   clip player did (docs/features/meaning-map.md). React is allowed, and its own files; anything
   else — the replica, the repository, the styles, a helper that happens to be convenient — is not.
   */

import { describe, expect, it } from "vitest";

const sources = import.meta.glob(["./*.ts", "./*.tsx", "!./*.test.ts", "!./*.test.tsx"], {
  query: "?raw", import: "default", eager: true
}) as Record<string, string>;

describe("the meaning map's boundary", () => {
  it("has files to check", () => {
    expect(Object.keys(sources)).toContain("./core.ts");
  });

  it.each(Object.entries(sources))("%s imports only React and its own files", (_name, source) => {
    const imports = [...source.matchAll(/(?:import|export)[^"']*?from\s+["']([^"']+)["']/g)].map((m) => m[1]);
    expect(imports.filter((spec) => !spec.startsWith("./") && spec !== "react")).toEqual([]);
  });
});
