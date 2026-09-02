/**
 * Runs mapped dictionary entries through Acervo's own `parseArticle`.
 *
 * The fidelity column in the results table is only meaningful if the same code that reads a typed
 * document reads a mapped one, so this imports the real parser rather than re-implementing it in
 * Python. `parseArticle` is the correct gate: external entries are render-only and never enter the
 * graph, so `validateGraph`'s stricter rule (at least one gloss group per sense) does not apply.
 *
 *   npx vitest run --config experiments/external-dictionaries/fidelity.config.ts
 */
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "vitest";

import { parseArticle } from "../../web/src/yaml";

const OUT = join(__dirname, "..", "..", "data", "dictionaries", "out");
const RESULTS = join(__dirname, "results");

test("mapped dictionary entries parse as Acervo articles", () => {
  const files = readdirSync(OUT).filter((name) => name.endsWith(".yaml.jsonl"));
  expect(files.length).toBeGreaterThan(0);

  // Group by the record's own `source`, not by file: online.yaml.jsonl holds two APIs.
  const bySource = new Map<string, string[]>();
  for (const file of files) {
    for (const line of readFileSync(join(OUT, file), "utf8").split("\n").filter(Boolean)) {
      const source = JSON.parse(line).source;
      if (!bySource.has(source)) bySource.set(source, []);
      bySource.get(source)!.push(line);
    }
  }

  const rows = [...bySource.entries()].map(([source, lines]) => {
    const causes = new Map<string, number>();
    let valid = 0;
    let senseTotal = 0;
    for (const line of lines) {
      const record = JSON.parse(line);
      try {
        const draft = parseArticle(record.yaml);
        valid += 1;
        senseTotal += draft.senses.length;
      } catch (error: any) {
        const problems: string[] = error?.problems?.map((p: any) => p.message) ?? [String(error?.message)];
        for (const message of new Set(problems)) {
          causes.set(message, (causes.get(message) ?? 0) + 1);
        }
      }
    }
    return {
      source,
      checked: lines.length,
      valid,
      sensesPerEntry: valid ? Number((senseTotal / valid).toFixed(2)) : 0,
      causes: [...causes.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5),
    };
  });

  const lines = ["", "| Source | Checked | Valid | Acceptance | Senses/entry | Top failure |",
    "|---|---:|---:|---:|---:|---|"];
  for (const row of rows) {
    const rate = row.checked ? ((row.valid / row.checked) * 100).toFixed(1) : "0.0";
    const top = row.causes.length ? `${row.causes[0][0]} (×${row.causes[0][1]})` : "—";
    lines.push(`| \`${row.source}\` | ${row.checked} | ${row.valid} | ${rate} % | ${row.sensesPerEntry} | ${top} |`);
  }
  const table = lines.join("\n");
  console.log(table);
  writeFileSync(join(RESULTS, "fidelity.json"), JSON.stringify(rows, null, 2));
  writeFileSync(join(RESULTS, "fidelity.md"), table);
});
