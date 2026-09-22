/* The meaning map as a React component: a canvas the core draws on, fed through props.

   Data for another key (a language) grows in from nothing, or appears where `initialCamera` says it
   was left; new data for the same key is an update, and the points already on screen glide to their
   new places while the new ones ring. Everything else — flying to a point, fitting, zooming, what the
   floating furniture covers — is the handle, through the ref. */

import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from "react";
import { createMeaningMap, type MeaningMapHandle } from "./core";
import type { MapCamera, MapData, MapLabels, MapPoint, MapRegion, MapStyle } from "./types";

export interface MeaningMapProps {
  data: MapData;
  /* What the data is a map of. A different key is a different map, not an update of this one. */
  dataKey: string;
  style?: MapStyle;
  labels?: MapLabels;
  /* Where to put the camera the first time this key is shown, instead of growing the map in. */
  initialCamera?: MapCamera | null;
  selected?: number;
  highlighted?: Set<number> | null;
  label?: string;
  onSelect?: (point: MapPoint | null, index: number) => void;
  onRegion?: (region: MapRegion) => void;
  onCamera?: (camera: MapCamera) => void;
  /* How many points an update brought, once it has been applied. */
  onUpdate?: (arrived: number) => void;
}

export const MeaningMap = forwardRef<MeaningMapHandle | null, MeaningMapProps>(function MeaningMap(props, ref) {
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const handle = useRef<MeaningMapHandle | null>(null);
  const shown = useRef<{ key: string; data: MapData } | null>(null);
  /* The callbacks change on every render of the host; the core is made once and reads them here. */
  const latest = useRef(props);
  latest.current = props;

  /* The core is made in an effect, after the ref is handed out, so what the host holds is a stand-in
     that forwards to it: handing out `handle.current` itself gave the host `null` for good, and every
     fly, fit and zoom from the page went nowhere. */
  const forward = useMemo<MeaningMapHandle>(() => ({
    setData: (next, options) => handle.current?.setData(next, options) ?? 0,
    setStyle: (style) => handle.current?.setStyle(style),
    setLabels: (labels) => handle.current?.setLabels(labels),
    select: (index, options) => handle.current?.select(index, options),
    highlight: (indices) => handle.current?.highlight(indices),
    fit: (animate) => handle.current?.fit(animate),
    fitRegion: (id) => handle.current?.fitRegion(id),
    zoomBy: (factor) => handle.current?.zoomBy(factor),
    zoomTo: (z) => handle.current?.zoomTo(z),
    setInsets: (insets) => handle.current?.setInsets(insets),
    screenOf: (index) => handle.current?.screenOf(index) ?? { x: 0, y: 0 },
    reveal: (index) => handle.current?.reveal(index),
    getCamera: () => handle.current?.getCamera() ?? { cx: 0, cy: 0, z: 1 },
    setCamera: (camera) => handle.current?.setCamera(camera),
    destroy: () => undefined
  }), []);
  useImperativeHandle(ref, () => forward, [forward]);

  useEffect(() => {
    if (!canvas.current) return;
    handle.current = createMeaningMap(canvas.current, {
      onSelect: (point, index) => latest.current.onSelect?.(point, index),
      onRegion: (region) => latest.current.onRegion?.(region),
      onCamera: (camera) => latest.current.onCamera?.(camera)
    });
    return () => {
      handle.current?.destroy();
      handle.current = null;
      shown.current = null;
    };
  }, []);

  useEffect(() => {
    const map = handle.current;
    if (!map) return;
    const before = shown.current;
    if (before && before.key === props.dataKey) {
      if (before.data === props.data) return;
      const previous = new Map(before.data.points.map((p) => [p.id, [p.x, p.y] as [number, number]]));
      /* Text can change with nothing moving — a headword edited, a sync that touched nothing here —
         and that is a redraw, not an update: no glide and no rings for a map that stayed put. */
      const moved = props.data.points.some((p) => {
        const was = previous.get(p.id);
        return !was || was[0] !== p.x || was[1] !== p.y;
      });
      if (moved) {
        // Not `onUpdate?.(map.setData(…))`: an optional call skips its arguments, and a host that
        // passed no `onUpdate` never had its map updated at all.
        const arrived = map.setData(props.data, { animate: "update", previous, camera: map.getCamera() });
        latest.current.onUpdate?.(arrived);
      } else map.setData(props.data, { camera: map.getCamera() });
    } else {
      const camera = props.initialCamera ?? null;
      map.setData(props.data, camera ? { camera } : { animate: "grow" });
    }
    shown.current = { key: props.dataKey, data: props.data };
    // New data clears the core's selection and highlight; what the host holds is put back.
    if (props.selected !== undefined && props.selected >= 0) map.select(props.selected);
    if (props.highlighted) map.highlight(props.highlighted);
    // `selected` is applied on its own below; `initialCamera` matters only when the key changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.data, props.dataKey]);

  useEffect(() => { handle.current?.setStyle(props.style ?? "atlas"); }, [props.style]);
  useEffect(() => { handle.current?.setLabels(props.labels ?? "name"); }, [props.labels]);
  useEffect(() => { handle.current?.select(props.selected ?? -1); }, [props.selected]);
  useEffect(() => { handle.current?.highlight(props.highlighted ?? null); }, [props.highlighted]);

  return <canvas ref={canvas} className="map-canvas" role="img" aria-label={props.label ?? "A map of words by meaning"} />;
});
