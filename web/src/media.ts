/**
 * Reading a picture the server holds, offline-first like every other read.
 *
 * The media route is behind bearer auth, which is the whole reason this module exists: an
 * `<img src>` cannot carry a token, so the bytes are fetched with one, cached on the device, and
 * handed to the element as a blob URL. `LexemeArticle.tsx` used to put `imageRef` straight in a
 * `src` and had therefore never once displayed a picture.
 *
 * The cache is the offline-first half. A picture seen once is served from `mediaStore.ts` with no
 * request at all, so an article read on a train looks the same as one read at a desk — the rule the
 * replica already lives by, applied to the one part of a word that is not in it.
 *
 * Object URLs are reference-counted rather than revoked on unmount. The same picture is legitimately
 * on screen twice — an article and a list row — and revoking when the first unmounts would blank the
 * second; counting is what makes "this component no longer needs it" different from "nobody does".
 */

import { backendSession } from "./api";
import { createMediaStore, type MediaStore } from "./mediaStore";

const store: MediaStore = createMediaStore();

interface Held {
  url: string;
  holders: number;
}

const held = new Map<string, Held>();
const loading = new Map<string, Promise<Blob>>();

async function download(reference: string): Promise<Blob> {
  const response = await fetch(backendSession.mediaFileUrl(reference), {
    headers: backendSession.mediaHeaders(),
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(
      response.status === 404
        ? "That picture is not on the server."
        : `That picture could not be read from the server (${response.status}).`
    );
  }
  return response.blob();
}

/** The bytes, from this device where it has them and from the server where it does not. */
async function blobFor(reference: string): Promise<Blob> {
  const cached = await store.read(reference);
  if (cached) return cached.blob;
  const blob = await download(reference);
  // Best-effort: a full disk or a private window costs a re-fetch next time, and must not stop the
  // picture that is already in hand from being shown.
  await store.save(reference, blob).catch(() => undefined);
  return blob;
}

/**
 * A blob URL for this picture, taking a hold on it. Every call must be paired with `release`.
 *
 * An entry is never created at zero holders, and that is the whole trick: the object URL and the
 * first hold are set in one synchronous step after the await, so there is no window in which one
 * caller can revoke a URL a concurrent caller is about to be handed. Concurrent callers also share
 * one download — a sense and its list row mount together, and the second should not re-fetch.
 */
export async function acquire(reference: string): Promise<string> {
  const existing = held.get(reference);
  if (existing) {
    existing.holders += 1;
    return existing.url;
  }

  const inFlight = loading.get(reference);
  const promise = inFlight ?? blobFor(reference).finally(() => loading.delete(reference));
  if (!inFlight) loading.set(reference, promise);
  const blob = await promise;

  // Synchronous from here down, so nothing can interleave between the check and the increment.
  const again = held.get(reference);
  if (again) {
    again.holders += 1;
    return again.url;
  }
  const url = URL.createObjectURL(blob);
  held.set(reference, { url, holders: 1 });
  return url;
}

/** Give up one hold. The object URL is revoked once nothing is showing the picture. */
export function release(reference: string): void {
  const entry = held.get(reference);
  if (!entry) return;
  entry.holders -= 1;
  if (entry.holders > 0) return;
  URL.revokeObjectURL(entry.url);
  held.delete(reference);
}

/**
 * Forget a picture, on the device and in memory.
 *
 * Called when the owner deletes one: the reference stays the same across a regeneration, so without
 * this the cache would keep serving the picture that was just thrown away.
 */
export async function forget(reference: string): Promise<void> {
  const entry = held.get(reference);
  if (entry) {
    URL.revokeObjectURL(entry.url);
    held.delete(reference);
  }
  loading.delete(reference);
  await store.remove(reference).catch(() => undefined);
}

/** Every picture this device has cached. Separate from the replica, so neither wipe touches it. */
export async function clearPictures(): Promise<void> {
  held.forEach((entry) => URL.revokeObjectURL(entry.url));
  held.clear();
  loading.clear();
  await store.clear();
}

export function cachedBytes(): Promise<number> {
  return store.bytes();
}

/**
 * The picture's bytes, for the one caller that needs them rather than a URL: the export.
 *
 * Cache-first like everything else here, so exporting a vocabulary you have been reading costs no
 * requests at all. It deliberately takes no hold and creates no object URL — those exist for
 * showing a picture, and this is for writing one into a zip.
 */
export async function bytesFor(reference: string): Promise<Uint8Array> {
  return new Uint8Array(await (await blobFor(reference)).arrayBuffer());
}
