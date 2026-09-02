import type { YamlProblem } from "./yaml";

/** Parse problems, a refusal from the server, or the confirmation that a save landed. */
export function ValidationPanel({ problems, notice }: {
  problems: YamlProblem[]; notice: string | null;
}) {
  if (!problems.length) {
    return notice ? <div className="validation ok" role="status">{notice}</div> : null;
  }
  return <div className="validation bad" role="alert">
    <strong>{problems.length === 1 ? "This document was not saved:" : `${problems.length} problems, so nothing was saved:`}</strong>
    <ul>
      {problems.map((problem, index) => <li key={index}>
        {problem.line !== null && <code>line {problem.line}</code>} {problem.message}
      </li>)}
    </ul>
  </div>;
}
