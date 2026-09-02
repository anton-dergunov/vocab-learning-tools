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
