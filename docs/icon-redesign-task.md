# Task: Finalize the Acervo Small and Menu-Bar Icons

## Status

Deferred. Complete this as a separate visual-design task after the initial Acervo application shell.

## Existing artwork boundary

- Preserve the approved detailed Acervo artwork used at 48 px and larger.
- Do not reinterpret, regenerate, crop, or replace the large PWA, Apple touch, or macOS application icons.
- Redesign only the colour favicon family at 16, 24, and 32 px and the separate macOS menu-bar symbol.

## Preferred direction

The second image-generated concept from the August 2026 exploration is the most relevant starting point. Its useful features are:

- a perfectly upright, front-facing closed book;
- a continuous rounded binding joined convincingly to the covers;
- a recessed, visibly bound page block;
- a bookmark that helps the object read as a complete book;
- a centred gold capital `A` on a burgundy leather cover; and
- enough material depth to avoid the appearance of flat SVG shapes stacked together.

The concept is not approved as final artwork. It currently feels too formal and resembles a legal or reference volume. The next iteration should retain its believable construction while feeling more approachable, distinctive, and appropriate for a personal vocabulary application.

## Colour icon requirements

- Keep the book exactly upright. Do not rotate, tilt, skew, or use an isometric view.
- Make the spine and binding continuous from top to bottom and physically integrated with both covers.
- Pages must look bound into the volume, not like loose sheets placed between two disconnected covers.
- Centre the `A` optically and leave comfortable clearance from every edge and decorative line.
- Use the established deep-burgundy, warm-ivory, antique-gold, and restrained dark-navy palette.
- Prefer polished material depth over a flat vector or children's-illustration appearance.
- Avoid a generic legal-book, religious-book, or institutional-reference-book character.
- Keep details bold enough to survive reduction to 32 px and 16 px.
- Use a genuinely transparent background rather than a painted transparency grid.

## Menu-bar requirements

- Create a separate monochrome interpretation of the chosen book silhouette.
- Supply it as a macOS template image so the system renders it black or white for the current menu-bar appearance.
- Do not reuse the burgundy-and-gold colour bitmap in the menu bar.
- Preserve the existing interactions: left-click opens Acervo, and right-click shows **Quit Acervo**
  plus one update item when an update is waiting.
- Preserve the reserved trailing margin for the update dot. The dot is drawn beside the book, never
  on it, so that it is large enough to read at menu-bar size; the book must not be clipped, crowded,
  or shifted by it, and the icon must not change width when the dot appears.

## Suggested workflow

1. Generate several high-resolution raster candidates using the preferred concept as a structural reference.
2. Review the high-resolution candidates before modifying repository assets.
3. Produce 32 px and 16 px reductions of the finalists and review them at native size.
4. Select and approve one colour design.
5. Derive a simplified monochrome menu-bar symbol from its silhouette.
6. Replace only the small-icon assets and regenerate `favicon.ico` and the macOS optical-size slots.
7. Confirm that all artwork at 48 px and larger remains byte-for-byte unchanged.

## Acceptance criteria

- The object is immediately recognizable as one properly bound closed book at 16 px and 32 px.
- The icon feels suitable for a polished vocabulary application rather than a generic legal volume.
- The letter `A` is centred, legible, and never touches the cover border.
- The colour and menu-bar versions are recognizably related but are optimized independently.
- The menu-bar icon is monochrome and remains clear in both light and dark appearances.
- No approved large-format Acervo artwork changes.
