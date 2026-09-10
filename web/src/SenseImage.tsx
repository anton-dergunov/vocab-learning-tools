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
import { acquire, release } from "./media";

export type ImageState = "ready" | "pending" | "failed" | "suppressed";

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
function usePicture(reference: string | null): { url: string | null; error: string | null } {
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
    </button>
    <figcaption className="cap">
      {prompt.styleId && <span className="label">{prompt.styleId}</span>}
      {prompt.imageModelId === null && prompt.imageRef && <span className="label">yours</span>}
    </figcaption>
  </figure>;
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
