import { useEffect } from "react";
import type { Attestation } from "./domain";
import { usePicture } from "./picture";
import { pointsOf } from "./photoText";

/**
 * The photo a word was met in, kept with its attestation: a thumbnail beside the sentence, and the
 * whole frame with the word and its sentence drawn again when it is opened.
 *
 * Fetched as a blob behind bearer auth and cached on the device like a sense picture
 * (`usePicture`), so a photo seen once opens offline.
 */
export function PhotoThumb({ attestation, onOpen }: { attestation: Attestation; onOpen(): void }) {
  const { url } = usePicture(attestation.photoRef);
  return <button type="button" className="att-photo" aria-label="Open the photo" onClick={onOpen}>
    {url ? <img src={url} alt="" style={{ objectPosition: focusOf(attestation) }} /> : null}
  </button>;
}

/**
 * Where a square thumbnail looks: at the sentence. A photo kept from the camera, or from a scrolled
 * screenshot, is already the square it was chosen in; one that is not is centred on what it kept.
 */
function focusOf(attestation: Attestation): string {
  const polygons = attestation.photoRegion?.sentence.length
    ? attestation.photoRegion.sentence : attestation.photoRegion?.words ?? [];
  const ys = polygons.flat().map(([, y]) => y);
  if (!ys.length) return "50% 50%";
  return `50% ${Math.round(((Math.min(...ys) + Math.max(...ys)) / 2) * 100)}%`;
}

export function PhotoViewer({ attestation, headword, onClose }: {
  attestation: Attestation; headword: string; onClose(): void;
}) {
  const { url, error } = usePicture(attestation.photoRef);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [onClose]);
  const region = attestation.photoRegion;
  return <div className="modal-backdrop" role="presentation"
    onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="settings photo-viewer" role="dialog" aria-modal="true" aria-labelledby="photo-viewer-title">
      <header>
        <h2 id="photo-viewer-title">Where you met “{headword}”</h2>
        <button className="close" onClick={onClose} aria-label="Close">×</button>
      </header>
      <div className="settings-body">
        {error ? <p className="empty">{error}</p> : <div className="photo-window"><div className="photo-square">
          <div className="photo-frame">
            {url && <img src={url} alt="The photo this word was captured from" />}
            {url && region && <svg viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">
              {region.sentence.map((polygon, index) => <polygon key={`s${index}`} className="photo-sentence" points={pointsOf(polygon)} />)}
              {region.words.map((polygon, index) => <polygon key={`w${index}`} className="photo-word" points={pointsOf(polygon)} />)}
            </svg>}
          </div>
        </div></div>}
      </div>
    </section>
  </div>;
}
