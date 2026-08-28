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
