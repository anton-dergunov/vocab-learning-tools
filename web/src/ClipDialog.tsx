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
  clipFor, directLink, matchIn, translationFor,
  type ClipView, type StoredClip, type TranslationJob
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

export function ClipDialog({ stored, headword, glossLang, onClose, onRemove }: {
  stored: StoredClip;
  headword: string;
  /** What the player's target text is asked for in. The vocabulary's first gloss language. */
  glossLang: string | null;
  onClose(): void;
  /**
   * Taking the clip off the word. Here rather than under the clip in the article: you decide a clip
   * is wrong having watched it, and a remove link under every clip was noise on every read.
   */
  onRemove?(): void;
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

  /* The sentence is Acervo's; the *alignment* of it is the service's.

     The article already carries a translation of this clip — the clip-selection call wrote it into
     the graph — so it is shown at once, offline, with no round trip, and it is the same wording the
     article shows. What the corpus is asked for is the word graph **for that sentence**: one
     provider call instead of two, and nothing that can disagree with the page behind it. Asking it
     to translate afresh gave a second wording for the same passage and no way to say which was
     right (§2.13, amended). */
  const stored_text = stored.translation;
  const target_lang = stored.translationLang ?? glossLang;

  useEffect(() => {
    /* "Not fetched yet" is not "nothing to align", and the two used to share this branch. On the
       first pass `view` is null, so the guard below turned asking off before anything had been
       asked — and the commit that mounted the player mounted the line under it too, saying the
       corpus could not be reached, until the effect ran again a moment later and took it away.
       That is the flicker the comment in `TranslationLine` says was designed out: a line appearing
       and going, moving the sentence the reader had started. */
    if (!view) return;
    // Nothing to align, so nothing is outstanding — otherwise the line below would say it was
    // still working forever, on a clip it was never going to ask about.
    if (!view.clip || !target_lang || !stored_text) { setAsking(false); return; }
    const cancel = new AbortController();
    let live = true;
    setAsking(true);
    translationFor(view.clip.segment_id, target_lang, cancel.signal, false, stored_text)
      .then((job) => { if (live) { setTranslation(job); setAsking(false); } });
    return () => { live = false; cancel.abort(); };
    // `view` itself, not its segment id: a clip the corpus no longer holds has no id, so keying on
    // one meant the arrival of that answer did not re-run this.
  }, [view, target_lang, stored_text]);

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
    void translationFor(segmentId, glossLang, cancel.signal, true, stored_text ?? undefined)
      .then((job) => {
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
            /* The article's own sentence, on screen before anything is asked. The corpus only
               ever returns this same text back (it is what was sent), so the fallback here is not
               a placeholder that gets replaced — it is the final wording from the first frame. */
            targetText={translation?.result?.target_text ?? stored_text}
            targetLanguage={target_lang}
            /* Complete the moment there is a sentence, which there is immediately. What is still
               outstanding is the word graph, and `alignmentStatus` is the field that says so. */
            translationStatus={
              retrying ? "running" : translation?.status ?? (stored_text ? "complete" : "not_requested")
            }
            translationProvenance={translation?.result?.provenance ?? null}
            alignmentStatus={translation?.result?.alignment_status ?? "unavailable"}
            alignmentGroups={translation?.result?.alignment_groups ?? null}
            alignmentGraph={translation?.result?.alignment_graph ?? null}
            /* Where the headword sits in the Spanish. The corpus cannot say — a clip fetched by id
               carries no match span, because a segment id does not know what was searched for — but
               the stored example names the form, so Acervo can. Without it the translation was
               marked and the sentence it translates was not, which read as a bug because it was. */
            match={matchIn(stored)}
            onTranslationRetry={retry}
          />
        </Suspense>}

        {/* The player draws its own line once it has a job to draw one from. Until then — and when
            the corpus never answers — this is the only thing that says so. A translation that
            simply appears one day, with nothing in its place meanwhile, reads as broken. */}
        {view?.clip && <TranslationLine
          text={stored_text}
          asking={asking || retrying}
          job={translation}
          onRetry={retry}
        />}

        {view && !view.clip && <Stored stored={stored} unreachable={view.unreachable} />}

        {onRemove && <p className="clip-dialog-actions">
          {/* An ordinary tombstone, deliberately not a picture's `suppressed` field — and safe only
              because the clip search is one-shot at save. The id is derived from the sense and the
              segment, so a later re-search that chose the same segment would bring it back. */}
          <button type="button" className="link-btn clip-remove" onClick={onRemove}>Remove this clip</button>
        </p>}
      </div>
    </section>
  </div>;
}

/**
 * What is still outstanding under the sentence, in one line.
 *
 * **Its subject changed when the sentence stopped being the thing in doubt.** The translation is
 * the article's own and is on screen from the first frame, so the only question left is whether the
 * corpus managed to align it word by word — a nicety, not the content. So a failure here says so
 * mildly and offers a retry, rather than reporting a missing translation that is plainly visible
 * above it. A word with no stored translation at all is the one case where the sentence really is
 * absent, and it says that instead.
 */
function TranslationLine({ text, asking, job, onRetry }: {
  text: string | null;
  asking: boolean;
  job: TranslationJob | null;
  onRetry(): void;
}) {
  if (!text) {
    return <p className="hint clip-translation">
      This clip was saved without a translation, so there is nothing to show under it.
    </p>;
  }
  // Aligned. The player is drawing the interactive version and there is nothing to add.
  if (job?.status === "complete" && job.result?.alignment_graph) return null;
  // **While it is still asking, this says nothing and occupies nothing.** It used to announce
  // "Linking the words…" here, which was a paragraph with a rule above it and twenty pixels of its
  // own — so the moment the graph arrived and this returned null, the dialog collapsed by the
  // height of a line and everything in it moved. What the reader saw was the sentence they had
  // started reading shifting under them, and the natural conclusion was that the *text* had
  // changed. The linking is a nicety that finishes in a second or two and needs no narration; the
  // states worth a line are the ones below, where something is actually wrong and there is
  // something to do about it.
  if (asking) return null;
  return <p className="hint clip-translation">
    {job === null
      ? "The spoken-usage corpus could not be reached, so the words are not linked."
      : "The words could not be linked."}
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
