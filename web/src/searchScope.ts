import { useEffect, useState } from "react";

/**
 * How far a search reaches, remembered per device.
 *
 * A preference about this screen rather than about the vocabulary — the phone that carries two
 * dictionaries and the laptop that carries ten want different answers — so it lives in local
 * storage beside the editor preferences and the dictionary switches, not in the replicated graph.
 *
 * **Your own words are not a scope.** They are always searched, always first, and there is no
 * setting that turns them off: this is a personal vocabulary store that can also consult a
 * dictionary, never a dictionary browser that happens to remember some words.
 */
export interface SearchScope {
  /** Dictionaries stored on this device. Instant, and works with the server unreachable. */
  device: boolean;
  /** Dictionaries the server has compiled but this device has not stored. Read over byte ranges. */
  server: boolean;
  /** The online sources, which are only ever asked on ⏎. */
  online: boolean;
}

const KEYS: Record<keyof SearchScope, string> = {
  device: "acervo-search-device",
  server: "acervo-search-server",
  online: "acervo-search-online"
};
const SCOPE_EVENT = "acervo-search-scope";

/**
 * Everything on by default.
 *
 * A dictionary someone deliberately switched on in Settings and then had to switch on a second
 * time here would be a puzzle, not a safeguard — and nothing here is expensive enough to need one:
 * the device tier is sub-millisecond, the server tier is debounced, and the online tier already
 * waits for a keypress before it costs anything at all.
 */
function readScope(name: keyof SearchScope): boolean {
  try {
    const stored = localStorage.getItem(KEYS[name]);
    return stored === null ? true : stored === "on";
  } catch {
    return true;
  }
}

export function searchScope(): SearchScope {
  return { device: readScope("device"), server: readScope("server"), online: readScope("online") };
}

export function setSearchScope(name: keyof SearchScope, value: boolean): void {
  try { localStorage.setItem(KEYS[name], value ? "on" : "off"); }
  catch { /* a preference, not data */ }
  window.dispatchEvent(new CustomEvent(SCOPE_EVENT));
}

export function useSearchScope(): SearchScope {
  const [scope, setScope] = useState(searchScope);
  useEffect(() => {
    const refresh = () => setScope(searchScope());
    window.addEventListener(SCOPE_EVENT, refresh);
    return () => window.removeEventListener(SCOPE_EVENT, refresh);
  }, []);
  return scope;
}
