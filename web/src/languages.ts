/**
 * Presentation for the languages a replica happens to contain.
 *
 * This is configuration, not schema — it mirrors the `languages` block described in design §03 and
 * carries only what the interface needs: a label, a flag for the switcher, and the gloss languages
 * to prefer when deriving a one-line short form. Tags with no entry fall back to the platform's
 * own display names, so an unexpected language still renders sensibly.
 */

export interface LanguagePresentation {
  code: string;
  flag: string;
  name: string;
  glossLangs: string[];
}

const TABLE: Record<string, Omit<LanguagePresentation, "code">> = {
  es: { flag: "🇪🇸", name: "Spanish", glossLangs: ["en"] },
  en: { flag: "🇬🇧", name: "English", glossLangs: ["ru"] },
  ru: { flag: "🇷🇺", name: "Russian", glossLangs: ["en"] },
  "zh-Hans": { flag: "🇨🇳", name: "Chinese (Simplified)", glossLangs: ["ru", "en"] },
  "zh-Hant": { flag: "🇹🇼", name: "Chinese (Traditional)", glossLangs: ["ru", "en"] }
};

function displayName(code: string): string {
  try {
    return new Intl.DisplayNames(["en"], { type: "language" }).of(code) ?? code;
  } catch {
    return code;
  }
}

export function languageOf(code: string): LanguagePresentation {
  const known = TABLE[code];
  if (known) return { code, ...known };
  return { code, flag: "🏳️", name: displayName(code), glossLangs: [] };
}

export function glossLanguagesFor(code: string): string[] {
  return languageOf(code).glossLangs;
}
