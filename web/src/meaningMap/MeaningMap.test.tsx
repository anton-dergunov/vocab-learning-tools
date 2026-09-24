import { render } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import type { MeaningMapHandle } from "./core";
import { MeaningMap } from "./MeaningMap";
import type { MapData } from "./types";

/* jsdom has no canvas, so the core is replaced by a handle that records what it is asked. */
const core = {
  setData: vi.fn(() => 0), setStyle: vi.fn(), setLabels: vi.fn(), select: vi.fn(), highlight: vi.fn(), choose: vi.fn(),
  fit: vi.fn(), fitRegion: vi.fn(), zoomBy: vi.fn(), zoomTo: vi.fn(), setInsets: vi.fn(),
  screenOf: vi.fn(() => ({ x: 1, y: 2 })), reveal: vi.fn(), getCamera: vi.fn(() => ({ cx: 5, cy: 6, z: 2 })),
  setCamera: vi.fn(), destroy: vi.fn()
};
vi.mock("./core", () => ({ createMeaningMap: () => core }));

const data: MapData = { side: 1000, regions: [], contours: [], points: [
  { id: "a", word: "w", headword: "picar", emoji: "", gloss: "", x: 1, y: 2, region: -1, hood: -1, rank: 1, near: [] }
] };

describe("the meaning map component", () => {
  /* The core is made in an effect, after the ref is handed out. A ref holding the core itself held
     `null` for good, and every fly, fit and zoom the page asked for went nowhere. */
  it("hands its host a handle that reaches the core made after it", () => {
    const ref = createRef<MeaningMapHandle>();
    render(<MeaningMap ref={ref} data={data} dataKey="es" />);
    ref.current?.fit(true);
    ref.current?.select(0, { fly: true });
    ref.current?.zoomBy(1.8);
    expect(core.fit).toHaveBeenCalledWith(true);
    expect(core.select).toHaveBeenCalledWith(0, { fly: true });
    expect(core.zoomBy).toHaveBeenCalledWith(1.8);
    expect(ref.current?.getCamera()).toEqual({ cx: 5, cy: 6, z: 2 });
  });

  it("grows a new key in, and draws new data for the same key as an update", () => {
    const { rerender } = render(<MeaningMap data={data} dataKey="es" />);
    expect(core.setData).toHaveBeenLastCalledWith(data, { animate: "grow" });
    const moved: MapData = { ...data, points: [{ ...data.points[0], x: 50 }] };
    rerender(<MeaningMap data={moved} dataKey="es" />);
    expect(core.setData).toHaveBeenLastCalledWith(moved, expect.objectContaining({ animate: "update" }));
    const renamed: MapData = { ...moved, points: [{ ...moved.points[0], headword: "picado" }] };
    rerender(<MeaningMap data={renamed} dataKey="es" />);
    // Nothing moved: a redraw in place, not a glide.
    expect(core.setData).toHaveBeenLastCalledWith(renamed, { camera: { cx: 5, cy: 6, z: 2 } });
  });
});
