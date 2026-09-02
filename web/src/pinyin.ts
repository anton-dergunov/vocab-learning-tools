/**
 * Numbered pinyin as it is actually written: `Fang1 shan1 Xian4` → `Fāng shān Xiàn`.
 *
 * CC-CEDICT and CC-Canto store the tone as a trailing digit because their format is one line of
 * ASCII, and every reader is expected to render it. Acervo shows the reading directly under the
 * headword, in the same place a learner reads it, so leaving the digits there hands them the
 * storage format instead of the word.
 *
 * Deliberately not a transliterator and deliberately not a word segmenter: syllables stay separated
 * exactly as the source separated them, because CC-CEDICT does not record where words begin and
 * joining them would be a guess. Anything that is not recognisably a numbered syllable is returned
 * untouched, so a reading that was already accented, or was never pinyin at all, passes through.
 */

/** Vowels in tone order 1–4; a neutral tone (5, or 0) carries no mark. */
const MARKS: Record<string, string[]> = {
  a: ["ā", "á", "ǎ", "à"], e: ["ē", "é", "ě", "è"], i: ["ī", "í", "ǐ", "ì"],
  o: ["ō", "ó", "ǒ", "ò"], u: ["ū", "ú", "ǔ", "ù"], "ü": ["ǖ", "ǘ", "ǚ", "ǜ"]
};

/** Letters a syllable may be built from, once `u:`/`v` have become `ü`. */
const SYLLABLE = /^([a-zü]+)([0-5])$/i;

/**
 * Where the mark goes.
 *
 * The standard rule, and it is short: `a` or `e` takes it whenever present; `ou` puts it on the
 * `o`; otherwise it lands on the last vowel of the syllable.
 */
function markPosition(letters: string): number {
  const lower = letters.toLowerCase();
  for (const vowel of ["a", "e"]) {
    const at = lower.indexOf(vowel);
    if (at >= 0) return at;
  }
  const ou = lower.indexOf("ou");
  if (ou >= 0) return ou;
  for (let index = lower.length - 1; index >= 0; index -= 1) {
    if (MARKS[lower[index]]) return index;
  }
  return -1;
}

function accentSyllable(token: string): string {
  // `u:` and `v` are both how an ASCII format spells `ü`; CC-CEDICT uses the first, learners the
  // second. `ü` only ever follows n, l, j, q, x or y, which is what keeps this off ordinary Latin.
  const normalised = token.replace(/u:/gi, "ü").replace(/([nljqxy])v/gi, "$1ü");
  const parts = SYLLABLE.exec(normalised);
  if (!parts) return token;
  const [, letters, tone] = parts;
  if (tone === "0" || tone === "5") return letters;
  const at = markPosition(letters);
  if (at < 0) return letters;
  const vowel = letters[at];
  const marked = MARKS[vowel.toLowerCase()]?.[Number(tone) - 1];
  if (!marked) return letters;
  return letters.slice(0, at)
    + (vowel === vowel.toUpperCase() && vowel !== vowel.toLowerCase() ? marked.toUpperCase() : marked)
    + letters.slice(at + 1);
}

/** True when this reads as numbered pinyin rather than as something else entirely. */
export function isNumberedPinyin(reading: string): boolean {
  const tokens = reading.trim().split(/\s+/).filter(Boolean);
  if (!tokens.length) return false;
  const syllables = tokens.filter((token) => SYLLABLE.test(token.replace(/u:/gi, "ü")));
  // Most of it, not all: a reading may carry a stray `·` or a Latin abbreviation between syllables.
  return syllables.length > 0 && syllables.length >= tokens.length - 1;
}

export function accentedPinyin(reading: string): string {
  if (!isNumberedPinyin(reading)) return reading;
  return reading.trim().split(/(\s+)/).map((part) => /\s/.test(part) ? part : accentSyllable(part)).join("");
}

/**
 * The same, for the readings CC-CEDICT writes inside a definition.
 *
 * `涼山彝族自治州|凉山彝族自治州[Liang2 shan1 Yi2 zu2 Zi4 zhi4 zhou1]` is a cross-reference to
 * another entry, and the bracket is the only part of it a reader can be expected to sound out.
 */
export function accentedPinyinInText(value: string): string {
  return value.replace(/\[([^\]]{1,120})\]/g, (whole, inner: string) => {
    // Some CC-CEDICT builds space out the `u:` that stands for `ü`, so `[Lu:3 …]` arrives as
    // `[Lu : 3 …]` and stops looking like pinyin at all. Closing that up costs nothing anywhere
    // else: an IPA bracket has no digit after a letter and still fails the test below.
    const candidate = inner.replace(/\s*:\s*/g, ":");
    return isNumberedPinyin(candidate) ? `[${accentedPinyin(candidate)}]` : whole;
  });
}
