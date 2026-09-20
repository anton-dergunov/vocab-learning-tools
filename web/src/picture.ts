/**
 * `usePicture`: a blob URL for a stored picture, held for as long as a component shows it.
 *
 * Its own module, above `media.ts` rather than inside it, for two reasons. `media.ts` is byte
 * plumbing — fetching, caching, reference counting — and has no React in it; and keeping the two
 * apart is what lets a test mock the byte layer and still exercise the hand-over logic below,
 * which is the half with the subtle failure modes.
 *
 * Shared by `SenseImage.tsx` and `StoryReader.tsx`: both show a picture the server holds behind
 * bearer auth, so both need the same blob-URL dance, and two copies of it would be two places for
 * a StrictMode double-release to hide.
 */

import { useEffect, useRef, useState } from "react";

import { acquire, release } from "./media";

/**
 * The blob URL for a stored picture, held for as long as this component shows it.
 *
 * A reference carries a digest of its bytes, so a redrawn picture is a *different* reference and a
 * changed picture is a changed effect. The record's revision is deliberately not in here: it is not
 * a cache key, and keying on it re-fetched a picture that had not changed every time the row was
 * edited. Do not add it back.
 *
 * The previous picture stays on screen until the new one is in hand, rather than the frame blanking
 * and filling again — which is what the "Redrawing…" mark over it already promises. That makes this
 * a hand-over: the hold on the old picture is given back only once the new one has been acquired,
 * so `holding` is a ref rather than state — a release inside a state updater would run twice under
 * StrictMode.
 *
 * The hold has to be released exactly once, and only if it was ever taken. Under StrictMode the
 * effect mounts, cleans up and mounts again, and the fetch may still be in flight at cleanup: an
 * arrival that finds itself stale releases immediately, and one that has been promoted to `holding`
 * is released by the next promotion or by the unmount below — never by both.
 */
export function usePicture(reference: string | null): { url: string | null; error: string | null } {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  /** The reference `url` was made from, and the one hold this hook owns. */
  const holding = useRef<string | null>(null);

  useEffect(() => () => {
    if (holding.current) release(holding.current);
    holding.current = null;
  }, []);

  useEffect(() => {
    setError(null);
    if (!reference) {
      // Nothing to show any more — a picture deleted or ruled out blanks at once, on purpose.
      if (holding.current) release(holding.current);
      holding.current = null;
      setUrl(null);
      return;
    }

    let live = true;
    acquire(reference)
      .then((held) => {
        if (!live) {
          release(reference);   // stale: give back the hold this run took
          return;
        }
        // Synchronous from here down, so nothing can interleave between the swap and the release.
        const previous = holding.current;
        holding.current = reference;
        setUrl(held);
        if (previous && previous !== reference) release(previous);
      })
      .catch((problem: Error) => { if (live) setError(problem.message); });

    return () => { live = false; };
  }, [reference]);

  return { url, error };
}
