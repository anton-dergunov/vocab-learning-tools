import { useEffect, useState } from "react";

/**
 * How the YAML surfaces present text, remembered per device.
 *
 * These describe this screen, not the vocabulary — a phone and a desktop want different answers —
 * so they live in local storage rather than the replicated graph, and they are set in Settings
 * rather than above the editor, where they were controls you had to step over on the way to work.
 *
 * Wrapping is the default: these documents are mostly prose, and a definition running off the right
 * edge is the common case. Scrolling stays available because YAML indentation is meaningful.
 */
export interface EditorPreferences {
  wrap: boolean;
  numbers: boolean;
}

const PREFERENCE_KEYS = { wrap: "acervo-editor-wrap", numbers: "acervo-editor-numbers" } as const;
const PREFERENCES_EVENT = "acervo-editor-preferences";

function readPreference(key: string, fallback: boolean): boolean {
  try {
    const stored = localStorage.getItem(key);
    return stored === null ? fallback : stored === "on";
  } catch {
    return fallback;
  }
}

export function editorPreferences(): EditorPreferences {
  return {
    wrap: readPreference(PREFERENCE_KEYS.wrap, true),
    numbers: readPreference(PREFERENCE_KEYS.numbers, false)
  };
}

export function setEditorPreference(name: keyof EditorPreferences, value: boolean): void {
  try { localStorage.setItem(PREFERENCE_KEYS[name], value ? "on" : "off"); } catch { /* a preference, not data */ }
  // Settings and the editor are different trees, so a change in one has to reach the other.
  window.dispatchEvent(new CustomEvent(PREFERENCES_EVENT));
}

export function useEditorPreferences(): EditorPreferences {
  const [preferences, setPreferences] = useState(editorPreferences);
  useEffect(() => {
    const refresh = () => setPreferences(editorPreferences());
    window.addEventListener(PREFERENCES_EVENT, refresh);
    return () => window.removeEventListener(PREFERENCES_EVENT, refresh);
  }, []);
  return preferences;
}

/**
 * Which view an article opens in, remembered per device for the same reason as the editor's.
 *
 * `auto` is Cards where a word is glanced at — a touch screen, which cannot hover — and Page where
 * there is a pointer. The switch above an article changes the view for that sitting, not this.
 */
export type ArticleViewPreference = "auto" | "page" | "cards";
export type ArticleView = "page" | "cards";

const ARTICLE_VIEW_KEY = "acervo-article-view";

export function articleViewPreference(): ArticleViewPreference {
  try {
    const stored = localStorage.getItem(ARTICLE_VIEW_KEY);
    return stored === "page" || stored === "cards" ? stored : "auto";
  } catch {
    return "auto";
  }
}

export function setArticleViewPreference(value: ArticleViewPreference): void {
  try { localStorage.setItem(ARTICLE_VIEW_KEY, value); } catch { /* a preference, not data */ }
  window.dispatchEvent(new CustomEvent(PREFERENCES_EVENT));
}

export function defaultArticleView(preference: ArticleViewPreference = articleViewPreference()): ArticleView {
  if (preference !== "auto") return preference;
  const touch = typeof window.matchMedia === "function" && window.matchMedia("(hover: none)").matches;
  return touch ? "cards" : "page";
}

export function useDefaultArticleView(): ArticleView {
  const [view, setView] = useState(() => defaultArticleView());
  useEffect(() => {
    const refresh = () => setView(defaultArticleView());
    window.addEventListener(PREFERENCES_EVENT, refresh);
    return () => window.removeEventListener(PREFERENCES_EVENT, refresh);
  }, []);
  return view;
}

/**
 * Whether pronunciations are kept on this device once heard, remembered per device.
 *
 * On by default: a spoken headword is a few kilobytes, and a clip kept is a clip that plays on a
 * plane. Off means every press asks the server — the choice for a device short on space — and
 * switching it off forgets what was kept (`pronunciation.ts`). A device fact, like wrapping, so it is
 * never replicated and never on the server.
 */
const PRONUNCIATION_CACHE_KEY = "acervo-pronunciation-cache";

export function pronunciationCacheEnabled(): boolean {
  return readPreference(PRONUNCIATION_CACHE_KEY, true);
}

export function setPronunciationCacheEnabled(value: boolean): void {
  try { localStorage.setItem(PRONUNCIATION_CACHE_KEY, value ? "on" : "off"); } catch { /* a preference, not data */ }
  window.dispatchEvent(new CustomEvent(PREFERENCES_EVENT));
}

export function usePronunciationCache(): boolean {
  const [enabled, setEnabled] = useState(pronunciationCacheEnabled);
  useEffect(() => {
    const refresh = () => setEnabled(pronunciationCacheEnabled());
    window.addEventListener(PREFERENCES_EVENT, refresh);
    return () => window.removeEventListener(PREFERENCES_EVENT, refresh);
  }, []);
  return enabled;
}
