/**
 * A row with actions: a word in the list, a loop, a story.
 *
 * **Two ways to the same actions**, because a pointer and a finger do not have the same gestures. A
 * pointer right-clicks and gets a menu under it. A finger pushes the row aside and finds the actions
 * behind it — done with scroll-snap rather than touch handlers, the way the cards already swipe, so
 * there is no pointer arithmetic to get wrong and a trackpad gets it for free.
 *
 * It was written out twice, in `LoopView` and `StoryView`, before words needed it too; the three
 * rows now answer the same gestures the same way. `swipeRow` in the prototype's `app.js`.
 *
 * The scroller and the element the menu hangs off are two elements, not one: `overflow-x` makes the
 * vertical axis a scroller too, and a menu positioned inside it would be clipped rather than drawn.
 */

import { Fragment, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

export interface RowAction {
  /** What the swipe shows: short, because it is a button 96 pixels wide. */
  label: string;
  /** What the menu reads, which has room to say it properly. */
  menuLabel: string;
  /** `danger` is red and gets a rule above it in the menu; `pick` is the selection's colour. */
  tone?: "danger" | "pick";
  run(): void;
}

export default function SwipeRow({ actions, shellClassName, children }: {
  actions: RowAction[];
  /** Extra classes for the scroller, which a story row uses to become its own container. */
  shellClassName?: string;
  /** The row itself: the first snap point, the full width of the list. */
  children: ReactNode;
}) {
  /* Where in the row it was right-clicked, so the menu opens under the pointer. */
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  const shell = useRef<HTMLDivElement | null>(null);
  const item = useRef<HTMLDivElement | null>(null);
  const open = menu !== null;

  useEffect(() => {
    if (!open) return;
    /* A press inside this menu is left alone: it is the first half of the click that chooses an
       action, and closing on it unmounts the button before the click can arrive. A press anywhere
       else — another row's right-click included — puts it away, so only one is ever open. */
    const away = (event: PointerEvent) => {
      if (event.target instanceof Node && item.current?.querySelector(".row-menu")?.contains(event.target)) return;
      setMenu(null);
    };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setMenu(null); };
    window.addEventListener("pointerdown", away);
    window.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener("pointerdown", away);
      window.removeEventListener("keydown", escape);
    };
  }, [open]);

  const choose = (action: RowAction) => {
    setMenu(null);
    /* The row slides back over its actions, so what the action changed on the row is seen at once —
       a word's selected mark above all. */
    const scroller = shell.current;
    if (scroller && typeof scroller.scrollTo === "function") scroller.scrollTo({ left: 0, behavior: "smooth" });
    action.run();
  };

  return <div
    ref={item} className="swipe-item"
    onContextMenu={(event) => {
      event.preventDefault();
      const box = event.currentTarget.getBoundingClientRect();
      setMenu({ x: event.clientX - box.left, y: event.clientY - box.top });
    }}
  >
    <div ref={shell} className={`swipe-shell${shellClassName ? ` ${shellClassName}` : ""}`}>
      {children}
      <div className="swipe-actions">
        {actions.map((action) => <button
          key={action.menuLabel} className={`swipe-act${action.tone ? ` ${action.tone}` : ""}`}
          onClick={() => choose(action)}
        >{action.label}</button>)}
      </div>
    </div>
    {menu && <div
      className="menu open row-menu" role="menu"
      style={{ "--menu-x": `${menu.x}px`, "--menu-y": `${menu.y}px` } as CSSProperties}
    >
      {actions.map((action, index) => <Fragment key={action.menuLabel}>
        {action.tone === "danger" && index > 0 && <div className="menu-sep" />}
        <button role="menuitem" className={action.tone === "danger" ? "danger" : undefined} onClick={() => choose(action)}>
          {action.menuLabel}
        </button>
      </Fragment>)}
    </div>}
  </div>;
}
