/**
 * A sense's picture in the article, and the controls that change it.
 *
 * Deliberately plain: how pictures are *presented* is its own piece of work, and this is the
 * infrastructure that work will sit on. What matters here is that the states are all visible and
 * none of them moves the page — a picture that is still being drawn holds the space the drawn one
 * will take, so nothing reflows under the reader's eye when it arrives.
 *
 * The picture is fetched with the session token and shown as a blob URL, because the media route is
 * behind auth and an `<img src>` cannot carry one. `media.ts` owns that and the cache behind it.
 */

import { useEffect, useRef, useState } from "react";
import type { ImagePrompt } from "./domain";
import { SyncIcon } from "./icons";
import { acquire, release } from "./media";

export type ImageState = "ready" | "pending" | "failed" | "suppressed";

/** A picture with no rendering model is one the owner supplied — provenance modelled, not flagged. */
export function yours(prompt: ImagePrompt): boolean {
  return Boolean(prompt.imageRef) && prompt.imageModelId === null;
}

export function imageStateOf(prompt: ImagePrompt): ImageState {
  if (prompt.imageRef) return "ready";
  if (prompt.suppressed) return "suppressed";
  return prompt.attempts > 0 ? "failed" : "pending";
}

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
function usePicture(reference: string | null): { url: string | null; error: string | null } {
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

export function SenseImage({ prompt, headword, busy, onOpen }: {
  prompt: ImagePrompt;
  headword: string;
  /** True while this sense is being drawn right now, which only the engine knows. */
  busy: boolean;
  onOpen(): void;
}) {
  const state = imageStateOf(prompt);
  const { url, error } = usePicture(prompt.imageRef);

  return <figure className="sense-image">
    <button
      type="button"
      className={`sense-image-frame is-${state}${busy ? " is-busy" : ""}`}
      onClick={onOpen}
      // The alt text is the brief, which is a description of the picture written for a person —
      // exactly what alt text is for, and better than anything that could be generated here.
      aria-label={prompt.prompt ? `Picture for ${headword}: ${prompt.prompt}` : `Picture for ${headword}`}
    >
      {url
        ? <img src={url} alt={prompt.prompt || ""} />
        : <span className="sense-image-empty">
            {busy ? "Drawing…" : error ?? placeholderFor(state, prompt)}
          </span>}
      {/* Over the picture it is replacing, rather than instead of it. Pressing Draw closes the
          dialog, so this mark is the only thing that says the work was taken — and the old picture
          stays visible underneath because that is what is being reconsidered. */}
      {busy && url && <span className="sense-image-working" role="status">
        <SyncIcon />
        <span>Redrawing…</span>
      </span>}
    </button>
    {/* No caption. The style is how a picture was drawn, which nobody reads while learning a word;
        the picture's dialog says it, and says "your own picture" for one the owner attached. */}
  </figure>;
}

/**
 * The same picture as a card shows it: as large as the card allows, with nothing around it.
 *
 * Not a button. A card is for reading; the picture is asked for and changed on the page. One that is
 * being drawn right now is shown in `SenseImage`'s own frame instead, so a card and the page say the
 * same thing about it.
 */
export function CardPicture({ prompt, headword, busy }: { prompt: ImagePrompt; headword: string; busy: boolean }) {
  const { url, error } = usePicture(prompt.imageRef);
  return <div
    className="card-pic" role="img"
    aria-label={prompt.prompt ? `Picture for ${headword}: ${prompt.prompt}` : `Picture for ${headword}`}
  >
    {/* Still fetching, the spot says so quietly instead of being an unexplained gap. */}
    {url ? <img src={url} alt="" /> : <span className="sense-image-empty">{error ?? "Loading…"}</span>}
    {busy && url && <span className="sense-image-working" role="status"><SyncIcon /><span>Redrawing…</span></span>}
  </div>;
}

function placeholderFor(state: ImageState, prompt: ImagePrompt): string {
  if (state === "suppressed") return "No picture";
  if (state === "failed") return prompt.failureReason ?? "Could not be drawn";
  return prompt.prompt ? "Not drawn yet" : "No picture yet";
}

/**
 * A sense with no image prompt at all, while its brief is being written.
 *
 * Shown only while that work is happening: a sense with no picture and nothing drawing shows no frame
 * at all, and asks for one from the icon in its heading.
 */
export function EmptySenseImage({ busy, onOpen }: { busy: boolean; onOpen(): void }) {
  return <figure className="sense-image">
    <button type="button" className="sense-image-frame is-pending" onClick={onOpen}>
      <span className="sense-image-empty">{busy ? "Writing a brief…" : "Add a picture"}</span>
    </button>
  </figure>;
}

/** Reads a file the owner chose, for the attach control. Kept here so the dialog stays declarative. */
export function useFilePicker(onChosen: (file: File) => void) {
  const input = useRef<HTMLInputElement | null>(null);
  const element = <input
    ref={input}
    type="file"
    accept="image/*"
    hidden
    onChange={(event) => {
      const [file] = event.target.files ?? [];
      // Cleared so choosing the same file twice in a row still fires a change.
      event.target.value = "";
      if (file) onChosen(file);
    }}
  />;
  return { element, choose: () => input.current?.click() };
}
