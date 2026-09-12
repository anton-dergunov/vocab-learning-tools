/* ── what changed inside one string ──────────────────────────────────────
   A proposal that rewords a sentence used to say only that the sentence changed, which left the one
   question worth asking unanswered: *which words*. This computes that, deterministically and on the
   device — no model is asked what it did, because a model's account of its own edit is one more
   thing that can be wrong.

   Pure with no imports at all, like `article.py` is on the server and for the same reason: three
   callers share it and none of them should have to know about the others. `articleEdit.ts` uses
   `wordDiff` for a changed field, `lcs` for the minimal set of records a reorder actually moved, and
   `similarity` to decide whether two notes are the same note reworded or two different notes.

   One LCS serves all three, which is why there is no dependency here. A text-diff package would
   answer the first question and leave the other two to be written anyway. */

/** One run of the diff. `same` + `ins` rebuilds `after`; `same` + `del` rebuilds `before`. */
export interface DiffPart {
  at: "same" | "ins" | "del";
  text: string;
}

/**
 * A word and everything up to the next one.
 *
 * `word` is what `similarity` counts — bare, so "duele" and "duele," are the same word. `text` is
 * what the diff emits, and carries the punctuation and spacing, so joining the tokens rebuilds the
 * original exactly. The diff compares `text` rather than `word` precisely so that a changed comma
 * is a change: comparing `word` would align the two and then have to choose whose punctuation to
 * print, and either choice makes the reassembly a lie.
 */
export interface Token {
  word: string;
  text: string;
}

/**
 * Past this, return no inline diff and let the caller fall back to marking the whole field.
 *
 * A 400-character note is about seventy tokens, so this is far above anything an article holds; it
 * exists so that a pasted wall of text cannot make a render quadratic in something unbounded.
 */
export const TOKEN_CAP = 400;

interface Segment {
  value: string;
  wordLike: boolean;
}

const WORD = /[\p{L}\p{N}\p{M}]/u;
const RUNS = /[\p{L}\p{N}\p{M}]+|\s+|[^\p{L}\p{N}\p{M}\s]/gu;

/**
 * Split into word-like and separator runs.
 *
 * `Intl.Segmenter` rather than the regex below wherever it exists, and that is not gold-plating:
 * Chinese and Japanese write without spaces, so `\p{L}+` makes 他把衣服穿上了 a single token and the
 * word diff — the whole point of this module — would report "everything replaced" for exactly the
 * languages a learner most needs it in. Segmenter splits those by dictionary. The regex stays as the
 * fallback and is tested, because a silent degradation to "one token" is worse than a loud absence.
 */
function segments(text: string): Segment[] {
  if (typeof Intl !== "undefined" && typeof Intl.Segmenter === "function") {
    const reader = new Intl.Segmenter(undefined, { granularity: "word" });
    return [...reader.segment(text)].map((part) => ({
      value: part.segment,
      wordLike: Boolean(part.isWordLike)
    }));
  }
  return [...text.matchAll(RUNS)].map((match) => ({
    value: match[0],
    wordLike: WORD.test(match[0])
  }));
}

/** Tokens whose `text` joins back to exactly what came in. That property is load-bearing. */
export function tokenise(text: string): Token[] {
  const tokens: Token[] = [];
  /* Separators before the first word have nowhere to attach backwards, so they ride on it. */
  let leading = "";
  for (const part of segments(text)) {
    if (part.wordLike) {
      tokens.push({ word: part.value.normalize("NFC"), text: leading + part.value });
      leading = "";
    } else if (tokens.length === 0) {
      leading += part.value;
    } else {
      tokens[tokens.length - 1].text += part.value;
    }
  }
  // A string with no word in it at all — whitespace, or a lone dash — is still one token, so that
  // joining is total rather than nearly total.
  if (leading) tokens.push({ word: "", text: leading });
  return tokens;
}

/** Just the words, for counting and for similarity. */
export function words(text: string): string[] {
  return tokenise(text).map((token) => token.word).filter(Boolean);
}

/**
 * The longest common subsequence, as index pairs into `a` and `b`.
 *
 * Pairs rather than indices into `a` alone because both callers need both sides: the diff has to
 * know which `b` token a kept `a` token matched, and the reorder check reads the `a` side only.
 *
 * Deterministic by construction. At equal cost the walk advances `a`, which means a substitution
 * always emits its deletion before its insertion — so the same two strings always produce the same
 * diff, and a test can pin it.
 */
export function lcs<T>(
  a: readonly T[], b: readonly T[], equal: (left: T, right: T) => boolean
): { a: number; b: number }[] {
  const rows = a.length;
  const columns = b.length;
  if (!rows || !columns) return [];

  /* One flat `Int32Array` rather than nested arrays: at the sizes this sees the allocation dominates
     the arithmetic, and this is one allocation instead of `rows` of them. */
  const width = columns + 1;
  const table = new Int32Array((rows + 1) * width);
  for (let i = rows - 1; i >= 0; i -= 1) {
    for (let j = columns - 1; j >= 0; j -= 1) {
      table[i * width + j] = equal(a[i], b[j])
        ? table[(i + 1) * width + (j + 1)] + 1
        : Math.max(table[(i + 1) * width + j], table[i * width + (j + 1)]);
    }
  }

  const kept: { a: number; b: number }[] = [];
  let i = 0;
  let j = 0;
  while (i < rows && j < columns) {
    if (equal(a[i], b[j])) {
      kept.push({ a: i, b: j });
      i += 1;
      j += 1;
    } else if (table[(i + 1) * width + j] >= table[i * width + (j + 1)]) {
      i += 1;
    } else {
      j += 1;
    }
  }
  return kept;
}

/**
 * How much of one string survives into the other: `2·|common| / (|a| + |b|)`, over words.
 *
 * 1 for the same words, 0 for none shared. Symmetric and length-normalised, so a note that gains a
 * clause is not punished for it — which matters because this decides whether a reworded note is
 * shown as one change or as a deletion beside an addition.
 */
export function similarity(before: string, after: string): number {
  const left = words(before);
  const right = words(after);
  if (!left.length || !right.length) return 0;
  const common = lcs(left, right, (one, other) => one === other).length;
  return (2 * common) / (left.length + right.length);
}

/**
 * What changed between two strings, as runs to render in place.
 *
 * `null` means "do not draw an inline diff" — the strings are identical, or one of them is past
 * `TOKEN_CAP`. The caller marks the whole field instead.
 */
export function wordDiff(before: string, after: string): DiffPart[] | null {
  if (before === after) return null;
  const a = tokenise(before);
  const b = tokenise(after);
  if (a.length > TOKEN_CAP || b.length > TOKEN_CAP) return null;

  /* Trim the shared ends first. This is the entire performance argument and most of the quality
     one: a reworded sentence keeps its opening and closing clauses, so the LCS usually runs over a
     handful of tokens rather than the whole string, and the parts it emits stay contiguous instead
     of being interleaved with incidental matches on common short words. */
  const same = (left: Token, right: Token) => left.text === right.text;
  let head = 0;
  while (head < a.length && head < b.length && same(a[head], b[head])) head += 1;
  let tail = 0;
  while (
    tail < a.length - head && tail < b.length - head
    && same(a[a.length - 1 - tail], b[b.length - 1 - tail])
  ) tail += 1;

  const parts: DiffPart[] = [];
  const push = (at: DiffPart["at"], text: string) => {
    if (!text) return;
    const last = parts[parts.length - 1];
    // Merge runs, so a five-word deletion is one span rather than five.
    if (last && last.at === at) last.text += text;
    else parts.push({ at, text });
  };

  for (let index = 0; index < head; index += 1) push("same", a[index].text);

  const middleA = a.slice(head, a.length - tail);
  const middleB = b.slice(head, b.length - tail);
  const kept = lcs(middleA, middleB, same);
  let i = 0;
  let j = 0;
  for (const pair of kept) {
    while (i < pair.a) push("del", middleA[i++].text);
    while (j < pair.b) push("ins", middleB[j++].text);
    push("same", middleA[pair.a].text);
    i = pair.a + 1;
    j = pair.b + 1;
  }
  while (i < middleA.length) push("del", middleA[i++].text);
  while (j < middleB.length) push("ins", middleB[j++].text);

  for (let index = a.length - tail; index < a.length; index += 1) push("same", a[index].text);

  return parts;
}
