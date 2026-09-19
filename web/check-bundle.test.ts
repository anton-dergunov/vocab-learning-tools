/**
 * The real parser, run over a produced bundle. A throwaway beside `scripts/consolidate_exports.py`.
 *
 * That script carries a copy of `yaml.ts`'s key tables, and a copy is a thing that can be wrong.
 * This is not a copy: it imports `parseArticle` itself, so what passes here is what the Transfer
 * panel will accept. It sits here rather than beside the script so that the project's own vite
 * config resolves it, and it **skips itself** when `BUNDLE` is unset, so `npm run test` is
 * unaffected — it has nothing to say without a bundle on disk.
 *
 *     BUNDLE=~/__acervo_data/__dedup npm --prefix web run test check-bundle
 *
 * Delete it, and the script, once the import has landed.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { expect, test } from "vitest";

import { parseArticle, YamlProblems } from "./src/yaml";

const IGNORED = new Set(["markdown", "media", "audio"]);
// `isWordFile` reserves the three names at the bundle root only, and it is right to: `acervo` is a
// Spanish word, and `es/acervo.yaml` is an entry rather than a manifest.

function wordFiles(root: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(root)) {
    if (entry.startsWith(".") || IGNORED.has(entry)) continue;
    const path = join(root, entry);
    if (!statSync(path).isDirectory()) continue;
    for (const name of readdirSync(path)) {
      if (name.endsWith(".yaml")) found.push(join(path, name));
    }
  }
  return found.sort();
}

test.skipIf(!process.env.BUNDLE)("every word file in the bundle parses", () => {
  const root = process.env.BUNDLE as string;
  const files = wordFiles(root);
  expect(files.length, `no word files under ${root}`).toBeGreaterThan(0);

  const problems: string[] = [];
  for (const file of files) {
    try {
      const draft = parseArticle(readFileSync(file, "utf8"));
      if (!draft.senses.length) problems.push(`${relative(root, file)}: no senses`);
    } catch (error) {
      const said = error instanceof YamlProblems
        ? error.problems.map((one) => `${one.path}: ${one.message}`).join("; ")
        : String(error);
      problems.push(`${relative(root, file)}: ${said}`);
    }
  }
  // Straight to the handle: vitest keeps a passing test's console output to itself, and a gate
  // that says nothing when it passes is one nobody trusts.
  process.stdout.write(`\n${files.length} word files read from ${root}, `
    + `${problems.length} the parser refuses\n`);
  for (const one of problems.slice(0, 40)) process.stdout.write(`  !! ${one}\n`);
  expect(problems, `${problems.length} of ${files.length} files refused`).toEqual([]);
});
