/**
 * Export and import, as the Data page shows them.
 *
 * The panels own the two things a bundle needs that `transfer.ts` deliberately does not: the zip,
 * and the browser's way of handing a file in and out. Everything about what a bundle *is* stays in
 * `transfer.ts`, so a second transport would add a surface here and nothing else.
 */

import { useRef, useState } from "react";
import { strFromU8, strToU8, unzipSync, zipSync } from "fflate";
import { languageOf } from "./languages";
import { repository, type ReplicaSnapshot } from "./repository";
import { languageOptions } from "./selectors";
import {
  bundleName, exportBundle, importBundle, readBundle,
  type BundleFile, type BundlePlan, type ImportReport
} from "./transfer";

/** Whatever the archiver on the other machine felt like adding. None of it is vocabulary. */
const NOISE = /(^|\/)(__MACOSX\/|\.DS_Store$|\._)/;

function save(name: string, bytes: Uint8Array): void {
  const url = URL.createObjectURL(new Blob([bytes as unknown as BlobPart], { type: "application/zip" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Late enough for the click to have been handled, early enough not to hold the bundle in memory.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

async function filesIn(file: File): Promise<BundleFile[]> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (!/\.zip$/i.test(file.name)) return [{ path: file.name, text: strFromU8(bytes) }];
  return Object.entries(unzipSync(bytes))
    .filter(([path, content]) => !path.endsWith("/") && !NOISE.test(path) && content.length > 0)
    .map(([path, content]) => ({ path, text: strFromU8(content) }));
}

export function ExportPanel({ snapshot }: { snapshot: ReplicaSnapshot }) {
  const [language, setLanguage] = useState<string>("all");
  const [markdown, setMarkdown] = useState(true);
  const [problem, setProblem] = useState("");
  const languages = languageOptions(snapshot);

  function run() {
    try {
      const at = new Date().toISOString();
      const files = exportBundle(snapshot, { language, markdown }, at);
      const archive: Record<string, Uint8Array> = {};
      files.forEach((file) => { archive[file.path] = strToU8(file.text); });
      save(bundleName(language, at), zipSync(archive));
      setProblem("");
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "The export could not be written.");
    }
  }

  return <section className="config-section">
    <h3>Export</h3>
    <p className="config-help">
      Saves your vocabulary as a zip of YAML files, one per word, with the language settings and
      topics beside them. Built from this device's copy, so it works whether or not the server is
      reachable.
    </p>
    <label className="config-field">
      <span>Vocabulary</span>
      <select value={language} onChange={(event) => setLanguage(event.target.value)}>
        <option value="all">All languages</option>
        {languages.map((option) => <option key={option.code} value={option.code}>
          {option.name} · {option.count} {option.count === 1 ? "entry" : "entries"}
        </option>)}
      </select>
    </label>
    <label className="config-switch">
      <input type="checkbox" checked={markdown} onChange={(event) => setMarkdown(event.target.checked)} />
      <span>
        <strong>Include Obsidian markdown</strong>
        <span>A readable file per topic, named the way a vault expects: Spanish vocab - Food.md.</span>
      </span>
    </label>
    <button className="tb-btn" onClick={run}>Export…</button>
    {problem && <p className="transfer-problem" role="alert">{problem}</p>}
  </section>;
}

type Stage =
  | { at: "idle" }
  | { at: "chosen"; name: string; plan: BundlePlan }
  | { at: "running"; done: number; total: number }
  | { at: "done"; report: ImportReport };

export function ImportPanel({ onChanged }: { onChanged(): void }) {
  const [stage, setStage] = useState<Stage>({ at: "idle" });
  const [problem, setProblem] = useState("");
  const picker = useRef<HTMLInputElement>(null);
  const cancel = useRef({ cancelled: false });

  async function choose(file: File | undefined) {
    if (!file) return;
    setProblem("");
    try {
      setStage({ at: "chosen", name: file.name, plan: readBundle(await filesIn(file)) });
    } catch (error) {
      setStage({ at: "idle" });
      setProblem(error instanceof Error ? error.message : "That file could not be read.");
    }
  }

  async function run(plan: BundlePlan) {
    cancel.current = { cancelled: false };
    setStage({ at: "running", done: 0, total: 0 });
    const report = await importBundle(
      repository, plan,
      (done, total) => setStage({ at: "running", done, total }),
      cancel.current
    );
    onChanged();
    setStage({ at: "done", report });
  }

  function reset() {
    setStage({ at: "idle" });
    setProblem("");
    if (picker.current) picker.current.value = "";
  }

  return <section className="config-section">
    <h3>Import</h3>
    <p className="config-help">
      Adds the words in a bundle to your vocabulary. A word you already have is left exactly as it
      is, never replaced. Importing writes to the server, so it needs a connection.
    </p>

    <input
      ref={picker} type="file" accept=".zip,.yaml,.yml" className="transfer-file"
      onChange={(event) => void choose(event.target.files?.[0])}
    />

    {stage.at === "chosen" && <>
      <div className="transfer-summary">
        <strong>{stage.name}</strong>
        <span>
          {stage.plan.articles.length} {stage.plan.articles.length === 1 ? "entry" : "entries"}
          {stage.plan.topics.length ? `, ${stage.plan.topics.length} topics` : ""}
          {stage.plan.vocabularies.length ? `, ${stage.plan.vocabularies.length} languages` : ""}
        </span>
      </div>
      {stage.plan.problems.length > 0 && <ProblemList
        title={`${stage.plan.problems.length} ${stage.plan.problems.length === 1 ? "file" : "files"} could not be read and will be left out`}
        problems={stage.plan.problems}
      />}
      <div className="sync-actions">
        <button className="tb-btn" onClick={reset}>Cancel</button>
        <button
          className="tb-btn" disabled={stage.plan.articles.length === 0}
          onClick={() => void run(stage.plan)}
        >Import {stage.plan.articles.length} {stage.plan.articles.length === 1 ? "entry" : "entries"}</button>
      </div>
    </>}

    {stage.at === "running" && <>
      <div className="transfer-summary">
        <strong>Importing {stage.done} of {stage.total}…</strong>
        <span>Each entry is saved to the server before the next one starts.</span>
      </div>
      <button className="tb-btn" onClick={() => { cancel.current.cancelled = true; }}>Stop</button>
    </>}

    {stage.at === "done" && <>
      <div className="transfer-summary">
        <strong>
          {stage.report.aborted ? "Import stopped early" : "Import finished"}
        </strong>
        <span>
          {stage.report.added} added
          {stage.report.skipped.length > 0 && `, ${stage.report.skipped.length} already present`}
          {stage.report.failed.length > 0 && `, ${stage.report.failed.length} refused`}
          {stage.report.topicsAdded > 0 && `, ${stage.report.topicsAdded} new topics`}
          {stage.report.vocabulariesAdded > 0 && `, ${stage.report.vocabulariesAdded} new languages`}
        </span>
      </div>
      {stage.report.skipped.length > 0 && <details className="transfer-report">
        <summary>Already in your vocabulary</summary>
        <ul>{stage.report.skipped.map((entry) => <li key={`${entry.language}/${entry.headword}`}>
          {entry.headword} <span>{languageOf(entry.language).name}</span>
        </li>)}</ul>
      </details>}
      {stage.report.failed.length > 0 && <ProblemList title="Refused" problems={stage.report.failed} open />}
      <button className="tb-btn" onClick={reset}>Import another file</button>
    </>}

    {problem && <p className="transfer-problem" role="alert">{problem}</p>}
  </section>;
}

function ProblemList({ title, problems, open = false }: {
  title: string;
  problems: { path: string; message: string }[];
  open?: boolean;
}) {
  return <details className="transfer-report" open={open}>
    <summary>{title}</summary>
    <ul>{problems.map((entry, index) => <li key={`${entry.path}:${index}`}>
      {entry.path} <span>{entry.message}</span>
    </li>)}</ul>
  </details>;
}
