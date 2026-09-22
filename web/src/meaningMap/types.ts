/* The meaning map's own data, independent of where it came from.

   This directory imports nothing of Acervo's (`boundary.test.ts`), so these types say only what a
   map needs to be drawn: points, regions and contours in a 0–side square, with the text each point
   is labelled with already joined in. Acervo's adapter builds them from the server's map and the
   replica; the discovery repository could build them from anything. */

export interface MapPoint {
  /* A stable id for the point — a sense id in Acervo. */
  id: string;
  /* Which word the point is a sense of. Points sharing it are joined by arcs when one is selected. */
  word: string;
  headword: string;
  emoji: string;
  /* The first gloss term, drawn under the headword at close zoom. */
  gloss: string;
  x: number;
  y: number;
  /* Region and neighbourhood index, or -1 on a map with no regions. */
  region: number;
  hood: number;
  /* 0–1, how central the point is to its neighbourhood: the order labels are allowed in. */
  rank: number;
  /* The nearest points of other words, as indices into `points`. */
  near: number[];
}

export interface MapRegion {
  id: string;
  level: "region" | "hood";
  index: number;
  x: number;
  y: number;
  count: number;
  /* The region a neighbourhood lies inside. */
  region?: number;
  labels: { words: string[]; terms: string[]; name?: string };
}

export interface MapData {
  side: number;
  points: MapPoint[];
  regions: MapRegion[];
  /* `[level, [x, y, x, y, …]]`, level 0 being the coast. */
  contours: [number, number[]][];
}

export type MapStyle = "atlas" | "constellation" | "clouds";
/* How a region is named: its written name when it has one, its most central words, or its most
   distinctive terms. */
export type MapLabels = "name" | "words" | "terms";

export interface MapCamera {
  cx: number;
  cy: number;
  /* Zoom relative to the whole map fitting the canvas. */
  z: number;
}

export interface MapInsets {
  top: number;
  right: number;
  bottom: number;
  left: number;
}
