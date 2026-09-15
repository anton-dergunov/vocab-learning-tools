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
 * The hold has to be released exactly once, and only if it was ever taken. Under StrictMode the
 * effect mounts, cleans up and mounts again, and the fetch may still be in flight at cleanup — so
 * releasing unconditionally would give back a hold that was never taken (and let a still-pending
 * one leak forever). `taken` is what pairs them: cleanup releases now if the hold arrived, and the
 * arrival releases immediately if cleanup got there first.
 */
function usePicture(reference: string | null, version: number): { url: string | null; error: string | null } {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setUrl(null);
    setError(null);
    if (!reference) return;

    let live = true;
    let taken = false;
    acquire(reference)
      .then((held) => {
        taken = true;
        if (live) setUrl(held);
        else release(reference);
      })
      .catch((problem: Error) => { if (live) setError(problem.message); });

    return () => {
      live = false;
      if (taken) release(reference);
    };
    // `version` is the record's revision, and it is in this list for a reason that is easy to miss:
    // a redrawn picture keeps the *same* `imageRef`, because the path is derived from the record.
    // Keyed on the reference alone the effect would never re-run, and the article would go on
    // showing the picture that was just replaced until the component happened to remount — which is
    // what "close the word and open it again" was working around.
  }, [reference, version]);

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
  const { url, error } = usePicture(prompt.imageRef, prompt.revision);

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
 * Only a picture that exists is drawn this way. One that is pending, failed or suppressed opens the
 * card on the sense's emoji instead (`EmojiTile`), because an empty frame with a status in it is a
 * worse first thing to see on a card than a glyph that means the word.
 */
export function CardPicture({ prompt, headword, busy, onOpen }: {
  prompt: ImagePrompt; headword: string; busy: boolean; onOpen(): void;
}) {
  const { url } = usePicture(prompt.imageRef, prompt.revision);
  return <button
    type="button" className="card-pic" onClick={onOpen}
    aria-label={prompt.prompt ? `Picture for ${headword}: ${prompt.prompt}` : `Picture for ${headword}`}
  >
    {url && <img src={url} alt={prompt.prompt || ""} />}
    {busy && url && <span className="sense-image-working" role="status"><SyncIcon /><span>Redrawing…</span></span>}
  </button>;
}

/** A sense with no picture to show: its emoji, in the frame a picture would fill. */
export function EmojiTile({ emoji, busy, onOpen }: { emoji: string; busy: boolean; onOpen?(): void }) {
  return <button
    type="button" className="card-pic card-tile" onClick={onOpen} disabled={!onOpen}
    aria-label={busy ? "Drawing a picture" : "No picture yet"}
  >
    <span aria-hidden="true">{emoji}</span>
    {busy && <span className="card-tile-status" role="status">Drawing…</span>}
  </button>;
}

function placeholderFor(state: ImageState, prompt: ImagePrompt): string {
  if (state === "suppressed") return "No picture";
  if (state === "failed") return prompt.failureReason ?? "Could not be drawn";
  return prompt.prompt ? "Not drawn yet" : "No picture yet";
}

/**
 * A sense with no image prompt at all — nothing has been briefed for it.
 *
 * It gets the same frame and the same click target as a picture, so the article has one shape
 * whether or not a word has been through the pipeline yet.
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
