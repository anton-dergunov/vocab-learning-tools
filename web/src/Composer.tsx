import type { ReactNode } from "react";

/**
 * The shape of every surface you work in: a bounded column with a pinned header, exactly one
 * scrolling region, and a pinned action bar.
 *
 * The rule it enforces is the one the add sheet broke twice. A surface whose height is decided by
 * its contents has no scroll region at all — it simply grows past the window, taking its title off
 * the top and the button that commits the work off the bottom. Bounding the column and letting one
 * child scroll is what keeps both reachable, at any window size, on any platform.
 *
 * `fill` hands the scrolling to the body's own child instead. The YAML editor is already a scroll
 * container — that is what makes its gutter stick while long lines scroll sideways — so wrapping it
 * in a second scrolling box would give two vertical scrollbars for one document.
 */
export default function Composer({ label, head, actions, fill, children }: {
  label: string;
  head: ReactNode;
  /** Absent where the surface's own controls are the ones that matter — a live camera. */
  actions: ReactNode | null;
  fill?: boolean;
  children: ReactNode;
}) {
  return <section className="composer" aria-label={label}>
    <div className="composer-head">{head}</div>
    <div className={`composer-body${fill ? " fill" : ""}`}>{children}</div>
    {actions ? <div className="composer-actions">{actions}</div> : null}
  </section>;
}
