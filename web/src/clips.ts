/**
 * Every call to the spoken-usage corpus, and nothing else makes one.
 *
 * The rule `sync.ts` lives by for the graph and `dictionaries.ts` for dictionaries. A clip example
 * renders from its stored fields, so the article reads offline like every other read; pressing one
 * needs the network, because YouTube is on the other side of it regardless.
 *
 * The corpus is reached through Acervo's own allow-listed proxy, never directly: that is what keeps
 * the retrieval service on the internal network with no second hostname, no second CORS
 * configuration, and its operator token nowhere near a browser (`docs/plans/spoken-clips.md` §2.9).
 *
 * **The packaged client is used unchanged.** `createSpeechRetrievalClient` is given Acervo's proxy
 * as its base URL and a `fetch` that carries the session token, so the client the retrieval
 * repository ships and tests is the one that runs — no second implementation of its fifteen routes
 * and no second copy of its response types.
 */

import { createSpeechRetrievalClient, SpeechRetrievalApiError, type SpeechRetrievalClient }
  from "@spoken-usage-retrieval/react/client";
import type { SpeechClip, TranslationJob } from "@spoken-usage-retrieval/react/types";
import { backendSession } from "./api";
import type { Example } from "./domain";

export type { SpeechClip, TranslationJob };
export { SpeechRetrievalApiError };

/** Built per call rather than held, because signing out must not leave a client with a stale token. */
function corpus(): SpeechRetrievalClient {
  const headers = backendSession.speechHeaders();
  return createSpeechRetrievalClient({
    baseUrl: backendSession.speechBaseUrl(),
    fetch: (input, init) => {
      const merged = new Headers(init?.headers);
      Object.entries(headers).forEach(([name, value]) => merged.set(name, value));
      return fetch(input, { ...init, headers: merged, cache: "no-store" });
    }
  });
}

/**
 * What the player is opened with: the corpus's current clip, or the stored example alone.
 *
 * Asked for by `clipRef` rather than rebuilt from the stored fields, because the corpus is the
 * authority on where a passage starts and ends and may have re-cut it since. When it cannot be
 * reached the stored reference, start and end are still a playable citation — which is the whole
 * reason those fields are on the record rather than fetched.
 */
export interface ClipView {
  clip: SpeechClip | null;
  /** The stored fallback, always present. `null` clip plus this is the offline case. */
  stored: StoredClip;
  unreachable: boolean;
}

export interface StoredClip {
  videoRef: string;
  videoTitle: string | null;
  videoChannel: string | null;
  videoStart: number;
  videoEnd: number | null;
  clipRef: string | null;
  text: string;
  translation: string | null;
  matchedForm: string | null;
}

export function storedClipOf(example: Example): StoredClip | null {
  if (!example.videoRef) return null;
  return {
    videoRef: example.videoRef,
    videoTitle: example.videoTitle,
    videoChannel: example.videoChannel,
    videoStart: example.videoStart ?? 0,
    videoEnd: example.videoEnd,
    clipRef: example.clipRef,
    text: example.text,
    translation: example.translation,
    matchedForm: example.matchedForm
  };
}

export async function clipFor(stored: StoredClip, signal?: AbortSignal): Promise<ClipView> {
  if (!stored.clipRef) return { clip: null, stored, unreachable: false };
  try {
    return { clip: await corpus().clip(stored.clipRef, { signal }), stored, unreachable: false };
  } catch (error) {
    if (error instanceof SpeechRetrievalApiError && error.status === 404) {
      // The segment is gone from the corpus — an index rebuilt from a video that was deleted at the
      // source. The stored citation still names a real moment, so this is the fallback, not an error.
      return { clip: null, stored, unreachable: false };
    }
    return { clip: null, stored, unreachable: true };
  }
}

/**
 * Ask the corpus to translate this clip, and poll until it settles.
 *
 * **Acervo stores none of this.** The article's own translation line came from the clip-selection
 * call and lives in the graph, so it replicates to the phone and reads offline; what the *player*
 * shows is richer — a validated word-alignment graph it renders as an interactive relation — and it
 * is the service's, fetched when the modal opens and gone when it closes (§2.13).
 *
 * A job rather than a value, because translation is two provider calls and the service caches the
 * result: the second viewer of a clip gets it immediately, and the first waits once.
 *
 * **`retryFailed` is the way out of a cached refusal.** The service remembers a stage that produced
 * unusable output and answers from that memory, `cache_hit` and all, on every later request — which
 * is correct (a bad answer is not worth paying for twice) and means a clip that failed under a
 * broken configuration keeps failing after the configuration is fixed. Only this flag re-asks, so
 * it is what the player's retry button is wired to.
 */
export async function translationFor(segmentId: string, targetLanguage: string,
                                     signal?: AbortSignal,
                                     retryFailed = false): Promise<TranslationJob | null> {
  const client = corpus();
  try {
    let job = await client.requestTranslation(segmentId, { targetLanguage, retryFailed, signal });
    /* Bounded on purpose: the modal is open and somebody is waiting. Giving up leaves the source
       text and the article's own line, which is the state the player is designed to render anyway.

       The bound is two chained provider calls, not one — translate, then align — and only the
       first viewer of a clip ever pays it, because the service caches what it produced. Thirty
       seconds was under a single call's timeout and turned a slow success into a spinner that
       never resolved. */
    const deadline = Date.now() + 120_000;
    while ((job.status === "queued" || job.status === "running") && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 700));
      if (signal?.aborted) return null;
      job = await client.translation(job.job_id, { signal });
    }
    /* Said out loud. The job carries the reason it failed and the player, by design, renders one
       sentence for every way that can happen — so without this the difference between "no provider
       is credentialed", "the model returned prose" and "the segment was translated before the
       chain changed" is one identical line of grey text. */
    if (job.status !== "complete") {
      console.warn(`Acervo: the clip translation ended ${job.status}`,
                   job.error?.code ?? "", job.cache_hit ? "(from the corpus's cache)" : "");
    }
    return job;
  } catch (error) {
    /* Not configured, not credentialed, or not reachable. The player has a defined state for having
       no target text, and it is the same one a deployment with no chain always shows — so this is
       not an error to put in front of the reader.

       It is said out loud, though. Swallowed in silence, "the speech container has no chain" and
       "the corpus is down" and "this segment has no translation yet" are one blank space, and there
       is nothing to look at while working out which. */
    console.warn("Acervo: no target text for this clip", error);
    return null;
  }
}

/** The corpus's own reading, for Settings. */
export function corpusStatus(signal?: AbortSignal) {
  return corpus().status({ signal });
}

export function corpusStatistics(signal?: AbortSignal) {
  return corpus().statistics({ signal });
}

/** The channel catalogue is the retrieval service's; Acervo ships no copy and edits it through here. */
export function channels(language?: string, signal?: AbortSignal) {
  return corpus().channels(language, { signal });
}

export function setChannelEnabled(language: string, channelId: string, enabled: boolean) {
  return corpus().setChannelEnabled(language, channelId, enabled);
}

export function addChannel(channel: Parameters<SpeechRetrievalClient["addChannel"]>[0]) {
  return corpus().addChannel(channel);
}

/** A direct link, for when the service is unreachable and the player cannot be built. */
export function directLink(stored: StoredClip): string {
  const start = Math.max(0, Math.floor(stored.videoStart));
  if (!/youtube\.com|youtu\.be/.test(stored.videoRef)) return stored.videoRef;
  const separator = stored.videoRef.includes("?") ? "&" : "?";
  return `${stored.videoRef}${separator}t=${start}`;
}
