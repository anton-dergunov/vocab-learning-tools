/**
 * Playing a clip: Acervo owns the dialog, the packaged player owns playback.
 *
 * That split is the retrieval package's own contract — it renders a bounded excerpt with its own
 * transport, progressive source text, a direct-source fallback, keyboard control and a
 * reduced-motion mode, and it **deliberately owns no modal**, because a modal belongs to whatever
 * application is showing it.
 *
 * The player is fetched by `clipRef` rather than rebuilt from the stored fields, because the corpus
 * is the authority on where a passage starts and ends and may have re-cut it since the clip was
 * saved. When it cannot be reached, the stored reference, start and end are still a real citation
 * and a real link — which is the whole reason those five fields are on the record rather than
 * fetched. Reading a clip example therefore works offline like every other read; only *pressing*
 * one needs the network, and YouTube is on the other side of it regardless.
 *
 * `lazy()` because the player carries the YouTube iframe API and is the single largest thing in the
 * bundle that most sessions never open.
 */

import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import {
  clipFor, directLink, translationFor, type ClipView, type StoredClip, type TranslationJob
} from "./clips";
import { formatClock } from "./format";
import { PlayIcon } from "./icons";

/* The player's stylesheet is imported **statically**, so it lands in the one CSS file the entry
   already produces, while the component itself stays lazy.

   Importing it inside `lazy()` looked tidier and broke the macOS app outright. Vite splits a
   dynamically imported stylesheet into its own chunk and preloads it through a helper that resolves
   the path *relative to the importing chunk* — and `base: "./"` means that is `assets/`, so
   `assets/styles-….css` became `acervo://app/assets/assets/styles-….css` and the app died on
   "Unable to preload CSS" the first time anyone pressed a clip. It costs 12 KB in the main
   stylesheet to have no dynamically loaded CSS at all, and `verify_pwa.py` now holds the build to
   that. */
import "@spoken-usage-retrieval/react/styles.css";

const SpeechClipPlayer = lazy(async () =>
  ({ default: (await import("@spoken-usage-retrieval/react/player")).SpeechClipPlayer })
);

export function ClipDialog({ stored, headword, glossLang, onClose }: {
  stored: StoredClip;
  headword: string;
  /** What the player's target text is asked for in. The vocabulary's first gloss language. */
  glossLang: string | null;
  onClose(): void;
}) {
  const [view, setView] = useState<ClipView | null>(null);
  const [translation, setTranslation] = useState<TranslationJob | null>(null);
  /**
   * Whether the corpus has been asked yet.
   *
   * `translationFor` answers `null` for every way of having no target text — no chain, no
   * credential, the service down — and the player renders nothing at all for that, so the line
   * under the sentence was simply absent and there was no way to tell "still working" from "this
   * will never arrive". Acervo says which, below.
   */
  const [asking, setAsking] = useState(true);
  /** A retry in flight, so the player says "Translating…" rather than repeating the failure. */
  const [retrying, setRetrying] = useState(false);
  /** Its own controller, because a retry outlives the effect that started it and can poll for two
      minutes — closing the dialog has to stop it as surely as it stops the first ask. */
  const retryCancel = useRef<AbortController | null>(null);
  useEffect(() => () => retryCancel.current?.abort(), []);

  useEffect(() => {
    const cancel = new AbortController();
    let live = true;
    clipFor(stored, cancel.signal).then((found) => { if (live) setView(found); });
    return () => { live = false; cancel.abort(); };
  }, [stored.clipRef, stored.videoRef]);

  /* The player's target text is the *service's*, fetched when the modal opens and stored nowhere
     (§2.13). The article's own line came from the clip-selection call and is already in the graph;
     this is the richer thing — a validated word alignment the player renders as an interactive
     relation — and it is online-only exactly like the clip it belongs to. */
  useEffect(() => {
    if (!view?.clip || !glossLang) return;
    const cancel = new AbortController();
    let live = true;
    setAsking(true);
    translationFor(view.clip.segment_id, glossLang, cancel.signal)
      .then((job) => { if (live) { setTranslation(job); setAsking(false); } });
    return () => { live = false; cancel.abort(); };
  }, [view?.clip?.segment_id, glossLang]);

  /* The player already draws a retry beside a failed translation; this is the callback it needs to
     render one. It matters more than a convenience: the corpus remembers a stage that produced
     unusable output and answers from that memory ever after, so a clip attempted under a broken
     configuration cannot recover on its own. `retryFailed` is the only thing that re-asks. */
  const retry = useCallback(() => {
    const segmentId = view?.clip?.segment_id;
    if (!segmentId || !glossLang) return;
    retryCancel.current?.abort();
    const cancel = new AbortController();
    retryCancel.current = cancel;
    setRetrying(true);
    void translationFor(segmentId, glossLang, cancel.signal, true).then((job) => {
      if (cancel.signal.aborted) return;
      setTranslation(job);
      setRetrying(false);
      setAsking(false);
    });
  }, [view?.clip?.segment_id, glossLang]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const source = stored.videoChannel || stored.videoTitle || "Clip";

  return <div className="modal-backdrop" role="presentation"
    onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="settings clip-dialog" role="dialog" aria-modal="true"
      aria-labelledby="clip-dialog-title">
      <header>
        <h2 id="clip-dialog-title">“{headword}” in {source}</h2>
        <button className="close" onClick={onClose} aria-label="Close">×</button>
      </header>

      <div className="settings-body">
        {view === null && <p className="hint">Fetching the clip…</p>}

        {view?.clip && <Suspense fallback={<p className="hint">Loading the player…</p>}>
          <SpeechClipPlayer
            clip={view.clip}
            sourceLanguage={view.clip.source_language}
            accessibleName={`Clip for ${headword}`}
            targetText={translation?.result?.target_text ?? null}
            targetLanguage={translation?.result?.target_language ?? glossLang}
            translationStatus={retrying ? "running" : translation?.status ?? "not_requested"}
            translationProvenance={translation?.result?.provenance ?? null}
            alignmentStatus={translation?.result?.alignment_status ?? "unavailable"}
            alignmentGroups={translation?.result?.alignment_groups ?? null}
            alignmentGraph={translation?.result?.alignment_graph ?? null}
            onTranslationRetry={retry}
          />
        </Suspense>}

        {/* The player draws its own line once it has a job to draw one from. Until then — and when
            the corpus never answers — this is the only thing that says so. A translation that
            simply appears one day, with nothing in its place meanwhile, reads as broken. */}
        {view?.clip && <TranslationLine
          glossLang={glossLang}
          asking={asking || retrying}
          job={translation}
          onRetry={retry}
        />}

        {view && !view.clip && <Stored stored={stored} unreachable={view.unreachable} />}
      </div>
    </section>
  </div>;
}

/** Where the target text has got to, in one line, for the states the player leaves blank. */
function TranslationLine({ glossLang, asking, job, onRetry }: {
  glossLang: string | null;
  asking: boolean;
  job: TranslationJob | null;
  onRetry(): void;
}) {
  // It has one and the player is drawing it. Nothing to add.
  if (job?.status === "complete" && job.result?.target_text) return null;
  if (!glossLang) {
    return <p className="hint clip-translation">
      This vocabulary has no translation language set, so a clip is not translated.
    </p>;
  }
  if (asking) return <p className="hint clip-translation">Translating…</p>;
  return <p className="hint clip-translation">
    {job === null
      ? "The spoken-usage corpus could not be reached, so this clip has no translation yet."
      : "That translation did not finish."}
    <button className="link-btn" onClick={onRetry}>Try again</button>
  </p>;
}

/**
 * What a clip is when the corpus cannot be asked: the sentence, and a link that opens at the moment.
 *
 * Deliberately not an error screen. The record holds a real citation — a video, a title, a channel
 * and a start — and that was always the point of storing them rather than only the segment id.
 */
function Stored({ stored, unreachable }: { stored: StoredClip; unreachable: boolean }) {
  return <div className="clip-stored">
    <p className="t">{stored.text}</p>
    {stored.translation && <p className="tr">{stored.translation}</p>}
    <p className="hint">
      {unreachable
        ? "The spoken-usage corpus could not be reached, so the player is unavailable."
        : "This segment is no longer in the corpus."}
      {" "}The clip itself is still where it was.
    </p>
    <div className="foot">
      {stored.videoChannel && <span className="prov">{stored.videoChannel}</span>}
      <span className="label">starts at {formatClock(stored.videoStart)}</span>
    </div>
    <a className="clip" href={directLink(stored)} target="_blank" rel="noreferrer noopener">
      <span className="pl"><PlayIcon /></span>
      <span className="ti">{stored.videoTitle ?? "Open the video"}
        <span>opens at {formatClock(stored.videoStart)}</span></span>
    </a>
  </div>;
}
