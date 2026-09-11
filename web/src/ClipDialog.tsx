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

import { Suspense, lazy, useEffect, useState } from "react";
import {
  clipFor, directLink, translationFor, type ClipView, type StoredClip, type TranslationJob
} from "./clips";
import { formatClock } from "./format";
import { PlayIcon } from "./icons";

const SpeechClipPlayer = lazy(async () => {
  const [player] = await Promise.all([
    import("@spoken-usage-retrieval/react/player"),
    import("@spoken-usage-retrieval/react/styles.css")
  ]);
  return { default: player.SpeechClipPlayer };
});

export function ClipDialog({ stored, headword, glossLang, onClose }: {
  stored: StoredClip;
  headword: string;
  /** What the player's target text is asked for in. The vocabulary's first gloss language. */
  glossLang: string | null;
  onClose(): void;
}) {
  const [view, setView] = useState<ClipView | null>(null);
  const [translation, setTranslation] = useState<TranslationJob | null>(null);

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
    translationFor(view.clip.segment_id, glossLang, cancel.signal)
      .then((job) => { if (live) setTranslation(job); });
    return () => { live = false; cancel.abort(); };
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
            translationStatus={translation?.status ?? "not_requested"}
            translationProvenance={translation?.result?.provenance ?? null}
            alignmentStatus={translation?.result?.alignment_status ?? "unavailable"}
            alignmentGroups={translation?.result?.alignment_groups ?? null}
            alignmentGraph={translation?.result?.alignment_graph ?? null}
          />
        </Suspense>}

        {view && !view.clip && <Stored stored={stored} unreachable={view.unreachable} />}
      </div>
    </section>
  </div>;
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
