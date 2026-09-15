/* The prototype's icon set, unchanged. Stroke and size come from the stylesheet. */

const stroke = { fill: "none", stroke: "currentColor", strokeLinecap: "round" } as const;

export const SearchIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2} aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.6-3.6" /></svg>;
export const BackIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2} strokeLinejoin="round" aria-hidden="true"><path d="M15 5l-7 7 7 7" /></svg>;
export const PlusIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2} aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>;
export const PlayIcon = () => <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5.5v13l11-6.5z" /></svg>;
export const CaretIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2.2} strokeLinejoin="round" aria-hidden="true"><path d="M9 5l7 7-7 7" /></svg>;
export const PencilIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.8} strokeLinejoin="round" aria-hidden="true"><path d="M4 20h4l10-10-4-4L4 16z" /><path d="M13.5 6.5l4 4" /></svg>;
export const TrashIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.8} strokeLinejoin="round" aria-hidden="true"><path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13" /></svg>;
export const CloseIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2} aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>;
export const GearIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.7} strokeLinejoin="round" aria-hidden="true">
  <path d="M10.03 5.34 10.44 2.68h3.12l.41 2.66a6.95 6.95 0 0 1 1.35.55l2.17-1.58 2.2 2.2-1.58 2.17a6.95 6.95 0 0 1 .55 1.35l2.66.41v3.12l-2.66.41a6.95 6.95 0 0 1-.55 1.35l1.58 2.17-2.2 2.2-2.17-1.58a6.95 6.95 0 0 1-1.35.55l-.41 2.66h-3.12l-.41-2.66a6.95 6.95 0 0 1-1.35-.55l-2.17 1.58-2.2-2.2 1.58-2.17a6.95 6.95 0 0 1-.55-1.35l-2.66-.41v-3.12l2.66-.41a6.95 6.95 0 0 1 .55-1.35L4.31 6.51l2.2-2.2 2.17 1.58a6.95 6.95 0 0 1 1.35-.55Z" />
  <circle cx="12" cy="12" r="3.1" />
</svg>;
export const CloudIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.8} strokeLinejoin="round" aria-hidden="true"><path d="M7 18h10a4 4 0 0 0 .6-7.96A6 6 0 0 0 6 10.2 3.9 3.9 0 0 0 7 18z" /></svg>;
export const CloudOffIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.8} strokeLinejoin="round" aria-hidden="true"><path d="M7 18h10a4 4 0 0 0 .6-7.96A6 6 0 0 0 6 10.2 3.9 3.9 0 0 0 7 18z" /><path d="M3 3l18 18" /></svg>;
export const SyncIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.9} strokeLinejoin="round" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v5h-5" /></svg>;
/** A word that came out of a book rather than out of your own reading. */
export const BookIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.7} strokeLinejoin="round" aria-hidden="true"><path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H18v14H5.5A1.5 1.5 0 0 0 4 19.5z" /><path d="M4 19.5A1.5 1.5 0 0 1 5.5 18H20v2.5H5.5" /><path d="M8 8h6" /></svg>;
/** The same, fetched over the network rather than held. */
export const GlobeIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.7} strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="8.5" /><path d="M3.5 12h17" /><path d="M12 3.5c2.2 2.3 3.3 5.2 3.3 8.5S14.2 18.2 12 20.5c-2.2-2.3-3.3-5.2-3.3-8.5S9.8 5.8 12 3.5z" /></svg>;
/* A picture in a frame: what is being made, rather than a clock, which would read as "late". */
export const PictureIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.7} strokeLinejoin="round" aria-hidden="true"><rect x="3.5" y="5" width="17" height="14" rx="2" /><circle cx="9" cy="10" r="1.6" /><path d="M4 16.5l4.5-4 3.5 3 3-2.5 5 4" /></svg>;
export const AlertIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.9} strokeLinejoin="round" aria-hidden="true"><path d="M12 4l9 16H3z" /><path d="M12 10v4M12 17.2v.1" /></svg>;
/* Asking about a word. A speech bubble with a question in it — deliberately not `✳`, which the
   article already uses for "where you met it", and not a pencil, which is the YAML escape hatch. */
export const AskIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.8} strokeLinejoin="round" aria-hidden="true"><path d="M20 14.5A2.5 2.5 0 0 1 17.5 17H12l-4.5 3.5V17H6.5A2.5 2.5 0 0 1 4 14.5v-8A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5z" /><path d="M10.2 8.6a1.9 1.9 0 1 1 2.6 1.8c-.5.2-.8.7-.8 1.2v.3" /><path d="M12 14.2v.1" /></svg>;
/** The sheet's grabber: which way it will move, not a decoration. */
export const ChevronIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2.2} strokeLinejoin="round" aria-hidden="true"><path d="M5 15l7-7 7 7" /></svg>;
/** Sending a turn. */
export const SendIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2} strokeLinejoin="round" aria-hidden="true"><path d="M4 12h14" /><path d="M13 6l6 6-6 6" /></svg>;
/** A clip, drawn as a strip of film: a play triangle alone reads as "audio". */
export const FilmIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.7} strokeLinejoin="round" aria-hidden="true"><rect x="3.5" y="5" width="17" height="14" rx="2" /><path d="M3.5 9h17M3.5 15h17M7.5 5v4M12 5v4M16.5 5v4M7.5 15v4M12 15v4M16.5 15v4" /></svg>;
/** The article's details: what is known about the record rather than about the word. */
export const InfoIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.8} aria-hidden="true"><circle cx="12" cy="12" r="8.5" /><path d="M12 11v5.5" /><path d="M12 7.6v.1" /></svg>;
