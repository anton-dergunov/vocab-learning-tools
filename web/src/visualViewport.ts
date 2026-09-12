/* ── the on-screen keyboard ──────────────────────────────────────────────
   The hard constraint for the ask dock is not the laptop. It is a phone in portrait with the
   keyboard up, where the usable height is roughly 300-380 px and the composer has to stay above it.

   Two mechanisms, because no single one covers both platforms. Chrome and Android honour
   `interactive-widget=resizes-content` in the viewport meta (`index.html`), which shrinks the
   layout viewport so `dvh` and a sticky bottom simply follow. iOS Safari does not honour it: the
   layout viewport keeps its full height and the keyboard is drawn over the page, so a sticky
   element pinned to the bottom lands *underneath* the keyboard. There, the only thing that knows
   the keyboard is up is `visualViewport`.

   So this returns the height of whatever is covering the bottom of the window, which is 0 on every
   platform that resizes the content for us, and the keyboard's height on the one that does not. */

import { useEffect, useState } from "react";

/**
 * How much of the window's bottom edge is covered right now — the keyboard, mostly.
 *
 * 0 when `visualViewport` is absent, which is also what jsdom reports, so tests need no shim and
 * the dock renders at its resting position under test.
 */
export function useKeyboardInset(): number {
  const [inset, setInset] = useState(0);

  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const measure = () => {
      // `offsetTop` matters as well as `height`: Safari scrolls the visual viewport up to keep the
      // focused field visible, and without it the inset reads as larger than the keyboard actually
      // is and the dock floats above its own shadow.
      const covered = window.innerHeight - (viewport.height + viewport.offsetTop);
      // Rounded, because Safari reports fractional heights that differ by a hundredth between
      // events and would otherwise re-render on every scroll frame.
      setInset(Math.max(0, Math.round(covered)));
    };
    measure();
    viewport.addEventListener("resize", measure);
    viewport.addEventListener("scroll", measure);
    return () => {
      viewport.removeEventListener("resize", measure);
      viewport.removeEventListener("scroll", measure);
    };
  }, []);

  return inset;
}
