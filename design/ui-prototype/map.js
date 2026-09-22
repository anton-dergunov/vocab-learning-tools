/* Acervo — the meaning map, as a component.

   This file is the boundary `web/src/meaningMap/` will have (docs/plans/meaning-space.md): it is
   handed its data and its callbacks, and reads nothing of `app.js` — no state, no fixtures, no
   helpers. What it knows about is points, regions and a camera. That is what lets it move to the
   discovery repository later and come back as a package, the way the clip player did.

   One canvas, drawn in two layers per frame: the world layer (contours, clouds, links) under a
   camera transform, and the screen layer (dots, emoji, labels) in pixels, so text never scales
   with the zoom and is never blurred by it. A frame is only drawn when something asked for one.

   Data is `MapData`: `{points, regions, contours, side}` in a 0–side square, as
   `experiments/meaning-space/build.py` writes it. */

(function () {
  "use strict";

  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const smooth = (a, b, v) => clamp((v - a) / (b - a), 0, 1);
  const easeOut = (t) => 1 - Math.pow(1 - t, 3);
  const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  /* Muted hues for the clouds style, one per top-level region. Lightness and alpha are chosen per
     theme when the clouds are painted. */
  const HUES = [168, 24, 212, 88, 330, 44, 262, 128];

  function MeaningMap(canvas, options = {}) {
    const onSelect = options.onSelect || (() => {});
    const onRegion = options.onRegion || (() => {});
    const onCamera = options.onCamera || (() => {});
    const ctx = canvas.getContext("2d");
    const reduced = matchMedia("(prefers-reduced-motion: reduce)");

    let data = null, n = 0;
    let X, Y, FX, FY, PX, PY, PA, delay, fresh;
    let siblings = new Map();
    let regionList = [], hoodList = [];
    let contourPaths = [];
    let cloud = null;
    let anim = null;
    let style = "atlas", labelSource = "model";
    let sel = -1, hover = -1, lit = null;
    let W = 0, H = 0, dpr = 1;
    let cam = { k: 1, tx: 0, ty: 0 }, fitK = 1;
    let insets = { top: 0, right: 0, bottom: 0, left: 0 };
    let colors = {};
    let raf = 0, flight = null, inertia = null;
    let boxes = [];
    const widths = new Map();
    const sprites = new Map();

    /* ── camera ─────────────────────────────────────────────────────────── */

    const view = () => ({
      x: insets.left, y: insets.top,
      w: Math.max(80, W - insets.left - insets.right), h: Math.max(80, H - insets.top - insets.bottom)
    });
    const centre = () => { const v = view(); return { x: v.x + v.w / 2, y: v.y + v.h / 2 }; };
    const toWorld = (sx, sy) => ({ x: (sx - cam.tx) / cam.k, y: (sy - cam.ty) / cam.k });
    const zoom = () => cam.k / fitK;
    const minK = () => fitK * 0.55;
    const maxK = () => fitK * 26;

    function place(cx, cy, k) {
      const c = centre();
      cam = { k, tx: c.x - cx * k, ty: c.y - cy * k };
    }
    function current() {
      const c = centre();
      return { cx: (c.x - cam.tx) / cam.k, cy: (c.y - cam.ty) / cam.k, k: cam.k };
    }
    function boundsOf(indices) {
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const i of indices) {
        x0 = Math.min(x0, X[i]); y0 = Math.min(y0, Y[i]); x1 = Math.max(x1, X[i]); y1 = Math.max(y1, Y[i]);
      }
      if (!isFinite(x0)) return { x0: 0, y0: 0, x1: data ? data.side : 1000, y1: data ? data.side : 1000 };
      return { x0, y0, x1, y1 };
    }
    function kToFit(b, v, pad) {
      const bw = Math.max(b.x1 - b.x0, 40), bh = Math.max(b.y1 - b.y0, 40);
      return Math.min((v.w - pad * 2) / bw, (v.h - pad * 2) / bh);
    }
    /* `fitK` is always the whole map in the whole canvas, whatever covers part of it: the levels of
       detail hang off it, and a peek opening must not change what is labelled. */
    function measureFit() {
      if (!n || !W) return;
      fitK = kToFit(boundsOf(range(n)), { w: W, h: H }, 36);
    }
    function flyTo(cx, cy, k, ms = 520) {
      k = clamp(k, minK(), maxK());
      if (reduced.matches || ms === 0) { place(cx, cy, k); flight = null; request(); onCamera(getCamera()); return; }
      flight = { from: current(), to: { cx, cy, k }, t0: performance.now(), ms };
      inertia = null;
      request();
    }
    function fit(animate = true) {
      if (!n) return;
      const b = boundsOf(range(n));
      const v = view();
      flyTo((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2, kToFit(b, v, 36), animate ? 520 : 0);
    }
    function zoomAt(sx, sy, factor, animate) {
      const k = clamp(cam.k * factor, minK(), maxK());
      const w = toWorld(sx, sy);
      if (!animate) {
        cam = { k, tx: sx - w.x * k, ty: sy - w.y * k };
        request();
        return;
      }
      /* The world point under the finger stays under it: find the centre that makes that true at
         the new scale, and fly there. */
      const c = centre();
      flyTo(w.x + (c.x - sx) / k, w.y + (c.y - sy) / k, k, 380);
    }

    /* ── data ───────────────────────────────────────────────────────────── */

    function range(count) { return Array.from({ length: count }, (_, i) => i); }

    function setData(next, opts = {}) {
      const first = !data;
      data = next;
      n = next.points.length;
      X = new Float32Array(n); Y = new Float32Array(n);
      FX = new Float32Array(n); FY = new Float32Array(n);
      PX = new Float32Array(n); PY = new Float32Array(n); PA = new Float32Array(n);
      delay = new Float32Array(n); fresh = new Uint8Array(n);
      siblings = new Map();
      next.points.forEach((p, i) => {
        X[i] = p.x; Y[i] = p.y;
        if (!siblings.has(p.w)) siblings.set(p.w, []);
        siblings.get(p.w).push(i);
      });
      regionList = next.regions.filter((r) => r.level === "region");
      hoodList = next.regions.filter((r) => r.level === "hood");
      contourPaths = next.contours.map(([level, flat]) => {
        const path = new Path2D();
        path.moveTo(flat[0], flat[1]);
        for (let j = 2; j < flat.length; j += 2) path.lineTo(flat[j], flat[j + 1]);
        path.closePath();
        return { level, path };
      });
      cloud = null;
      sel = -1; hover = -1; lit = null;
      measureFit();
      if (opts.camera) setCamera(opts.camera);
      else if (first || opts.refit !== false) fit(false);
      startAnimation(opts);
      request();
    }

    /* Two motions, both from where a point was to where it is. Growing starts every point at its
       region's centre, a region at a time, so the map assembles into its islands; an update starts
       each shared point where the previous layout had it, and fades the new ones in after. */
    function startAnimation(opts) {
      anim = null;
      if (!opts.animate || reduced.matches) return;
      const now = performance.now();
      if (opts.animate === "grow") {
        const centres = new Map(regionList.map((r) => [r.index, r]));
        const mid = data.side / 2;
        let last = 0;
        data.points.forEach((p, i) => {
          const r = centres.get(p.r);
          FX[i] = r ? r.x : mid; FY[i] = r ? r.y : mid;
          const reach = Math.hypot(X[i] - FX[i], Y[i] - FY[i]) / data.side;
          delay[i] = (p.r >= 0 ? p.r : 0) * 55 + reach * 420;
          last = Math.max(last, delay[i]);
        });
        anim = { kind: "grow", t0: now, dur: 700, total: last + 700 + 450 };
      } else if (opts.animate === "update" && opts.previous) {
        let count = 0;
        data.points.forEach((p, i) => {
          const was = opts.previous.get(p.id);
          if (was) { FX[i] = was[0]; FY[i] = was[1]; delay[i] = 0; }
          else { FX[i] = X[i]; FY[i] = Y[i]; delay[i] = 900; fresh[i] = 1; count++; }
        });
        anim = { kind: "update", t0: now, dur: 1000, total: 900 + 1000 + 2600 };
        return count;
      }
    }

    function positions(now) {
      const t = anim ? now - anim.t0 : Infinity;
      for (let i = 0; i < n; i++) {
        if (!anim) { PX[i] = X[i]; PY[i] = Y[i]; PA[i] = 1; continue; }
        const p = clamp((t - delay[i]) / anim.dur, 0, 1);
        const e = anim.kind === "grow" ? easeOut(p) : easeInOut(p);
        PX[i] = FX[i] + (X[i] - FX[i]) * e;
        PY[i] = FY[i] + (Y[i] - FY[i]) * e;
        PA[i] = anim.kind === "grow" ? smooth(0, 0.35, p) : (fresh[i] ? smooth(0, 0.6, p) : 1);
      }
      return t;
    }

    /* ── colours, fonts, measuring ──────────────────────────────────────── */

    function readColors() {
      const cs = getComputedStyle(canvas);
      const v = (name) => cs.getPropertyValue(name).trim();
      colors = {
        sea: v("--map-sea"), land: v("--map-land"), coast: v("--map-coast"), contour: v("--map-contour"),
        ink: v("--ink"), ink2: v("--ink-2"), ink3: v("--ink-3"), rule: v("--rule"),
        core: v("--core"), coreSoft: v("--core-soft"), halo: v("--map-halo")
      };
      colors.dark = luminance(colors.sea) < 0.4;
      cloud = null;
    }
    function luminance(hex) {
      const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
      if (!m) return 1;
      const v = parseInt(m[1], 16);
      return (0.299 * (v >> 16) + 0.587 * ((v >> 8) & 255) + 0.114 * (v & 255)) / 255;
    }
    function hue(region, alpha, dotted) {
      const h = HUES[((region % HUES.length) + HUES.length) % HUES.length];
      if (colors.dark) return `hsla(${h}, ${dotted ? 38 : 34}%, ${dotted ? 62 : 42}%, ${alpha})`;
      return `hsla(${h}, ${dotted ? 30 : 42}%, ${dotted ? 38 : 62}%, ${alpha})`;
    }
    function width(font, text) {
      const key = font + "\u0000" + text;
      let w = widths.get(key);
      if (w === undefined) { ctx.font = font; w = ctx.measureText(text).width; widths.set(key, w); }
      return w;
    }
    /* An emoji drawn once into its own little canvas and stamped from then on: filling emoji text
       is the slowest thing a canvas does, and a close zoom shows a couple of hundred of them. */
    function sprite(emoji, size) {
      const key = emoji + size + ":" + dpr;
      let s = sprites.get(key);
      if (!s) {
        const px = Math.ceil(size * 1.5 * dpr);
        s = document.createElement("canvas");
        s.width = s.height = px;
        const c = s.getContext("2d");
        c.font = `${size * dpr}px "Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif`;
        c.textAlign = "center"; c.textBaseline = "middle";
        c.fillText(emoji, px / 2, px / 2 + size * dpr * 0.06);
        sprites.set(key, s);
      }
      return s;
    }

    /* ── labels ─────────────────────────────────────────────────────────── */

    function regionText(r) {
      const l = r.labels || {};
      if (labelSource === "model" && l.model) return l.model;
      if (labelSource === "terms" && l.terms && l.terms.length) return l.terms.join(" · ");
      if (labelSource === "words" && l.words && l.words.length) return l.words.join(" · ");
      return l.model || (l.words || []).join(" · ");
    }
    function wrap(text, max) {
      const words = text.split(/\s+/);
      const lines = [];
      let line = "";
      for (const w of words) {
        if (line && (line + " " + w).length > max) { lines.push(line); line = w; }
        else line = line ? line + " " + w : w;
      }
      if (line) lines.push(line);
      return lines.slice(0, 3);
    }

    /* Upright spaced capitals for regions and italic for the neighbourhoods inside them, as a printed
       atlas sets a country and a district. */
    const REGION_FONT = '600 13px "Literata", Georgia, serif';
    const HOOD_FONT = 'italic 400 14px "Literata", Georgia, serif';
    const REGION_LIST_FONT = 'italic 600 15px "Literata", Georgia, serif';
    const WORD_FONT = '500 13px "IBM Plex Sans", system-ui, sans-serif';
    const WORD_FONT_ON = '600 13.5px "IBM Plex Sans", system-ui, sans-serif';
    const GLOSS_FONT = 'italic 400 12px "IBM Plex Sans", system-ui, sans-serif';
    const TRACK = 0.13;

    /* Spaced capitals, as a printed map names its regions. Drawn a letter at a time, because a
       canvas's own letter spacing is not in every WebKit this has to run in. */
    function spacedWidth(text) {
      let w = 0;
      for (const ch of text) w += width(REGION_FONT, ch) + 13 * TRACK;
      return w - 13 * TRACK;
    }
    function drawSpaced(text, x, y) {
      let cx = x - spacedWidth(text) / 2;
      ctx.textAlign = "left";
      for (const ch of text) {
        ctx.strokeText(ch, cx, y);
        ctx.fillText(ch, cx, y);
        cx += width(REGION_FONT, ch) + 13 * TRACK;
      }
    }

    /* A screen-space grid of placed boxes, so testing a label against everything already placed
       costs a handful of comparisons rather than one per label. */
    function makeGrid() {
      const cell = 80, cells = new Map();
      const keys = (b) => {
        const out = [];
        for (let gx = Math.floor(b.x / cell); gx <= Math.floor((b.x + b.w) / cell); gx++)
          for (let gy = Math.floor(b.y / cell); gy <= Math.floor((b.y + b.h) / cell); gy++) out.push(gx + ":" + gy);
        return out;
      };
      return {
        free(b) {
          for (const k of keys(b)) for (const o of cells.get(k) || [])
            if (b.x < o.x + o.w && o.x < b.x + b.w && b.y < o.y + o.h && o.y < b.y + b.h) return false;
          return true;
        },
        add(b) { for (const k of keys(b)) { if (!cells.has(k)) cells.set(k, []); cells.get(k).push(b); } }
      };
    }

    /* ── drawing ────────────────────────────────────────────────────────── */

    function paintClouds() {
      const size = 900, pad = 80;
      const span = data.side + pad * 2;
      const c = document.createElement("canvas");
      c.width = c.height = size;
      const g = c.getContext("2d");
      const s = size / span;
      const radius = 44 * s;
      data.points.forEach((p) => {
        const x = (p.x + pad) * s, y = (p.y + pad) * s;
        const grad = g.createRadialGradient(x, y, 0, x, y, radius);
        grad.addColorStop(0, hue(p.r, colors.dark ? 0.2 : 0.16));
        grad.addColorStop(1, hue(p.r, 0));
        g.fillStyle = grad;
        g.fillRect(x - radius, y - radius, radius * 2, radius * 2);
      });
      cloud = { canvas: c, x: -pad, y: -pad, span };
    }

    function draw(now) {
      const t = positions(now);
      const growing = anim && anim.kind === "grow";
      const labelsIn = growing ? smooth(anim.total - 520, anim.total, t) : 1;
      const worldIn = growing ? smooth(0, 700, t) : 1;
      const z = zoom();
      const focus = sel >= 0 || (lit && lit.size);
      const inFocus = (i) => i === sel || (lit && lit.has(i)) ||
        (sel >= 0 && (data.points[sel].w === data.points[i].w || data.points[sel].nb.includes(i)));

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = style === "atlas" ? colors.sea : colors.land;
      ctx.fillRect(0, 0, W, H);

      /* World layer. */
      ctx.setTransform(dpr * cam.k, 0, 0, dpr * cam.k, dpr * cam.tx, dpr * cam.ty);
      if (style === "atlas" && contourPaths.length) {
        ctx.globalAlpha = worldIn;
        ctx.fillStyle = colors.land;
        for (const c of contourPaths) if (c.level === 0) ctx.fill(c.path);
        ctx.lineJoin = "round";
        for (const c of contourPaths) {
          ctx.strokeStyle = c.level === 0 ? colors.coast : colors.contour;
          ctx.lineWidth = (c.level === 0 ? 1.1 : 0.9) / cam.k;
          ctx.stroke(c.path);
        }
        ctx.globalAlpha = 1;
      }
      if (style === "clouds") {
        if (!cloud) paintClouds();
        ctx.globalAlpha = worldIn;
        ctx.imageSmoothingEnabled = true;
        ctx.drawImage(cloud.canvas, cloud.x, cloud.y, cloud.span, cloud.span);
        ctx.globalAlpha = 1;
      }
      if (style === "constellation") {
        ctx.beginPath();
        for (let i = 0; i < n; i++) {
          const nb = data.points[i].nb;
          for (let j = 0; j < Math.min(3, nb.length); j++) {
            const o = nb[j];
            if (o < i && data.points[o].nb.slice(0, 3).includes(i)) continue;
            ctx.moveTo(PX[i], PY[i]); ctx.lineTo(PX[o], PY[o]);
          }
        }
        ctx.strokeStyle = colors.rule;
        ctx.globalAlpha = (focus ? 0.35 : 0.8) * worldIn;
        ctx.lineWidth = 0.8 / cam.k;
        ctx.stroke();
        ctx.globalAlpha = 1;
      }

      /* Screen layer. */
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const SX = (i) => PX[i] * cam.k + cam.tx;
      const SY = (i) => PY[i] * cam.k + cam.ty;
      const onScreen = (x, y, m = 60) => x > -m && x < W + m && y > -m && y < H + m;

      if (sel >= 0) {
        const p = data.points[sel];
        const sx = SX(sel), sy = SY(sel);
        ctx.lineWidth = 1;
        ctx.strokeStyle = colors.core;
        ctx.globalAlpha = 0.45;
        ctx.beginPath();
        for (const j of p.nb) { ctx.moveTo(sx, sy); ctx.lineTo(SX(j), SY(j)); }
        ctx.stroke();
        /* The same word's other senses, joined by an arc: where else this word lives. */
        ctx.globalAlpha = 0.9;
        ctx.lineWidth = 1.6;
        ctx.setLineDash([5, 5]);
        for (const j of siblings.get(p.w) || []) {
          if (j === sel) continue;
          const tx = SX(j), ty = SY(j);
          const mx = (sx + tx) / 2, my = (sy + ty) / 2;
          const dx = tx - sx, dy = ty - sy;
          ctx.beginPath();
          ctx.moveTo(sx, sy);
          ctx.quadraticCurveTo(mx - dy * 0.22, my + dx * 0.22, tx, ty);
          ctx.stroke();
        }
        ctx.setLineDash([]);
        ctx.globalAlpha = 1;
      }

      /* Points. Dots far out; from the middle distance each sense becomes its own emoji, which is
         what tells the senses of one word apart before any text is read. */
      const emojiIn = smooth(3.0, 4.2, z);
      const r = clamp(1.6 + z * 0.3, 2, 3.6) * (style === "constellation" ? 1.25 : 1);
      const dot = style === "clouds" ? null : (style === "constellation" ? colors.ink2 : colors.ink3);
      for (let i = 0; i < n; i++) {
        if (PA[i] <= 0.01) continue;
        const x = SX(i), y = SY(i);
        if (!onScreen(x, y)) continue;
        const dim = focus && !inFocus(i) ? 0.22 : 1;
        const p = data.points[i];
        if (emojiIn < 1) {
          ctx.globalAlpha = PA[i] * dim * (1 - emojiIn * 0.9);
          ctx.fillStyle = i === sel || (lit && lit.has(i)) ? colors.core : dot || hue(p.r, 1, true);
          ctx.beginPath(); ctx.arc(x, y, i === sel ? r + 1.5 : r, 0, Math.PI * 2); ctx.fill();
        }
        if (emojiIn > 0 && p.emoji) {
          const size = 15;
          const s = sprite(p.emoji, size);
          ctx.globalAlpha = PA[i] * dim * emojiIn;
          const d = size * 1.5;
          ctx.drawImage(s, x - d / 2, y - d / 2, d, d);
        }
      }
      ctx.globalAlpha = 1;
      if (sel >= 0) {
        ctx.strokeStyle = colors.core; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(SX(sel), SY(sel), emojiIn > 0.5 ? 14 : 7, 0, Math.PI * 2); ctx.stroke();
      }
      if (anim && anim.kind === "update") {
        for (let i = 0; i < n; i++) {
          if (!fresh[i]) continue;
          const local = (t - delay[i]) / 1300;
          if (local < 0 || local > 2) continue;
          const phase = local % 1;
          ctx.strokeStyle = colors.core;
          ctx.globalAlpha = (1 - phase) * 0.8;
          ctx.lineWidth = 2;
          ctx.beginPath(); ctx.arc(SX(i), SY(i), 5 + phase * 16, 0, Math.PI * 2); ctx.stroke();
        }
        ctx.globalAlpha = 1;
      }

      drawLabels(z, labelsIn, SX, SY, onScreen, emojiIn, focus, inFocus);
    }

    function drawLabels(z, labelsIn, SX, SY, onScreen, emojiIn, focus, inFocus) {
      const grid = makeGrid();
      boxes = [];
      if (labelsIn <= 0) return;
      ctx.lineJoin = "round";
      ctx.textBaseline = "middle";
      const halo = colors.halo;

      const forced = [];
      if (sel >= 0) {
        forced.push(sel);
        for (const j of siblings.get(data.points[sel].w) || []) if (j !== sel) forced.push(j);
        forced.push(...data.points[sel].nb);
      }
      if (lit) forced.push(...[...lit].slice(0, 40));
      if (hover >= 0) forced.push(hover);

      const regionAlpha = 1 - smooth(1.45, 2.2, z);
      const hoodAlpha = smooth(1.35, 1.85, z) * (1 - smooth(4.5, 6.5, z));
      const glossAlpha = smooth(6.2, 8, z);

      /* Words the reader asked about come first, then the names of places, then the rest in order of
         how central each word is to its neighbourhood. */
      const wordLabel = (i, forcedOne) => {
        const p = data.points[i];
        const x = SX(i), y = SY(i);
        if (!onScreen(x, y, 0) || PA[i] < 0.5) return;
        const on = i === sel;
        const font = on ? WORD_FONT_ON : WORD_FONT;
        const gap = emojiIn > 0.5 ? 13 : 6;
        const tw = width(font, p.headword);
        const showGloss = (glossAlpha > 0 || forcedOne) && p.gloss;
        const gw = showGloss ? width(GLOSS_FONT, p.gloss) : 0;
        const h = showGloss && (glossAlpha > 0.05 || on) ? 32 : 18;
        const w = Math.max(tw, gw);
        let box = { x: x + gap, y: y - 9, w: w + 4, h };
        if (!grid.free(box)) {
          const left = { x: x - gap - w - 4, y: y - 9, w: w + 4, h };
          if (!forcedOne && !grid.free(left)) return;
          if (grid.free(left)) box = left;
        }
        grid.add(box);
        boxes.push({ ...box, point: i });
        const alpha = (focus && !inFocus(i) ? 0.3 : 1) * labelsIn * PA[i] *
          (forcedOne ? 1 : smooth(zmin[i], zmin[i] + 0.22, z));
        ctx.globalAlpha = alpha;
        ctx.font = font;
        ctx.textAlign = "left";
        ctx.strokeStyle = halo; ctx.lineWidth = 3.5;
        ctx.fillStyle = on || (lit && lit.has(i)) ? colors.core : (data.points[sel] && data.points[sel].w === p.w ? colors.core : colors.ink);
        ctx.strokeText(p.headword, box.x + 2, y);
        ctx.fillText(p.headword, box.x + 2, y);
        if (h > 18) {
          ctx.font = GLOSS_FONT;
          ctx.globalAlpha = alpha * (on || forcedOne ? 1 : glossAlpha);
          ctx.fillStyle = colors.ink3;
          ctx.strokeText(p.gloss, box.x + 2, y + 15);
          ctx.fillText(p.gloss, box.x + 2, y + 15);
        }
      };

      /* Once points are drawn as emoji, each one's glyph is a place no label may cover: a word written
         across another word's emoji makes both unreadable. */
      if (emojiIn > 0.5) {
        for (let i = 0; i < n; i++) {
          if (PA[i] < 0.5 || !data.points[i].emoji) continue;
          const x = SX(i), y = SY(i);
          if (onScreen(x, y, 0)) grid.add({ x: x - 9, y: y - 9, w: 18, h: 18 });
        }
      }
      const seen = new Set();
      for (const i of forced) { if (!seen.has(i)) { seen.add(i); wordLabel(i, true); } }

      const placeName = (r, level, alpha) => {
        if (alpha <= 0.02) return;
        const x = r.x * cam.k + cam.tx, y = r.y * cam.k + cam.ty;
        if (!onScreen(x, y, 120)) return;
        const text = regionText(r);
        if (!text) return;
        /* Capitals are for a place's name. A list of words or terms keeps its own case, set as the
           neighbourhoods are: shouted, three headwords read as a warning. */
        const named = level === "region" && labelSource === "model" && r.labels && r.labels.model;
        const lines = named ? wrap(text.toUpperCase(), 16) : wrap(text, level === "region" ? 24 : 20);
        const lh = level === "region" ? 19 : 18;
        const font = named ? REGION_FONT : level === "region" ? REGION_LIST_FONT : HOOD_FONT;
        const lw = Math.max(...lines.map((l) => (named ? spacedWidth(l) : width(font, l))));
        const box = { x: x - lw / 2 - 4, y: y - (lines.length * lh) / 2 - 2, w: lw + 8, h: lines.length * lh + 4 };
        if (!grid.free(box)) return;
        grid.add(box);
        boxes.push({ ...box, region: r });
        ctx.globalAlpha = alpha * labelsIn * (focus ? 0.35 : 1);
        ctx.font = font;
        ctx.fillStyle = colors.ink2;
        ctx.strokeStyle = halo; ctx.lineWidth = 4;
        lines.forEach((line, k) => {
          const ly = box.y + 2 + lh / 2 + k * lh;
          if (named) drawSpaced(line, x, ly);
          else { ctx.textAlign = "center"; ctx.strokeText(line, x, ly); ctx.fillText(line, x, ly); }
        });
      };
      const [firstLevel, secondLevel] = z < 1.8 ? [regionList, hoodList] : [hoodList, regionList];
      for (const r of firstLevel) placeName(r, r.level, r.level === "region" ? regionAlpha : hoodAlpha);
      for (const r of secondLevel) placeName(r, r.level, r.level === "region" ? regionAlpha : hoodAlpha);

      if (z >= 1.6 || !data.regions.length) {
        for (const i of order) {
          if (seen.has(i)) continue;
          if (z < zmin[i]) continue;
          wordLabel(i, false);
        }
      }
      ctx.globalAlpha = 1;
    }

    /* Label priority: most central first. A word's own zoom threshold comes from the same rank, so
       the middle distance shows the words that best describe each neighbourhood. */
    let order = [], zmin = new Float32Array(0);
    function prepareOrder() {
      zmin = new Float32Array(n);
      /* A map with no regions has nothing to show from afar but its words, so it names them all at once. */
      data.points.forEach((p, i) => { zmin[i] = data.regions.length ? 1.7 + Math.pow(1 - p.rank, 1.3) * 3.4 : 0; });
      order = range(n).sort((a, b) => data.points[b].rank - data.points[a].rank);
    }

    /* ── the frame loop ─────────────────────────────────────────────────── */

    function request() { if (!raf) raf = requestAnimationFrame(frame); }
    let lastFrame = 0;
    function frame(now) {
      raf = 0;
      const dt = lastFrame ? Math.min(now - lastFrame, 64) : 16;
      lastFrame = now;
      let again = false;
      if (flight) {
        const p = clamp((now - flight.t0) / flight.ms, 0, 1);
        const e = easeInOut(p);
        const k = Math.exp(Math.log(flight.from.k) + (Math.log(flight.to.k) - Math.log(flight.from.k)) * e);
        place(flight.from.cx + (flight.to.cx - flight.from.cx) * e, flight.from.cy + (flight.to.cy - flight.from.cy) * e, k);
        if (p >= 1) { flight = null; onCamera(getCamera()); } else again = true;
      }
      if (inertia) {
        cam.tx += inertia.vx * dt; cam.ty += inertia.vy * dt;
        const decay = Math.pow(0.93, dt / 16);
        inertia.vx *= decay; inertia.vy *= decay;
        if (Math.hypot(inertia.vx, inertia.vy) < 0.02) { inertia = null; onCamera(getCamera()); } else again = true;
      }
      if (anim) {
        if (now - anim.t0 > anim.total) anim = null; else again = true;
      }
      if (data && W) draw(now);
      if (again) request(); else lastFrame = 0;
    }

    /* ── gestures ───────────────────────────────────────────────────────── */

    const pointers = new Map();
    let gesture = null, lastTap = null;
    const at = (e) => { const r = canvas.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };

    function hitPoint(x, y, reach) {
      let best = -1, bestD = reach * reach;
      for (const b of boxes) if (b.point !== undefined && x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + b.h) return b.point;
      for (let i = 0; i < n; i++) {
        if (PA[i] < 0.3) continue;
        const dx = PX[i] * cam.k + cam.tx - x, dy = PY[i] * cam.k + cam.ty - y;
        const d = dx * dx + dy * dy;
        if (d < bestD) { bestD = d; best = i; }
      }
      return best;
    }
    function hitRegion(x, y) {
      for (const b of boxes) if (b.region && x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + b.h) return b.region;
      return null;
    }
    function tap(x, y, type) {
      const now = performance.now();
      if (lastTap && now - lastTap.t < 300 && Math.hypot(x - lastTap.x, y - lastTap.y) < 30) {
        lastTap = null;
        zoomAt(x, y, 2.2, true);
        return;
      }
      lastTap = { t: now, x, y };
      const region = zoom() < 2.4 ? hitRegion(x, y) : null;
      if (region) { fitRegion(region.id); onRegion(region); return; }
      const i = hitPoint(x, y, type === "mouse" ? 12 : 24);
      if (i >= 0) { select(i); onSelect(data.points[i], i); return; }
      const hood = hitRegion(x, y);
      if (hood) { fitRegion(hood.id); onRegion(hood); return; }
      if (sel >= 0) { select(-1); onSelect(null, -1); }
    }

    function down(e) {
      /* Capture keeps a drag that leaves the canvas ours; it is a convenience, and a pointer the
         browser does not consider active (a synthetic one, in a test) must not end the gesture. */
      try { canvas.setPointerCapture(e.pointerId); } catch (_) { /* carry on uncaptured */ }
      const p = at(e);
      pointers.set(e.pointerId, p);
      flight = null; inertia = null;
      if (pointers.size === 1) {
        gesture = { kind: "pan", moved: 0, start: e.timeStamp, last: p, samples: [{ t: e.timeStamp, ...p }], type: e.pointerType };
      } else if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        const m = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
        gesture = { kind: "pinch", d0: Math.hypot(a.x - b.x, a.y - b.y), k0: cam.k, world: toWorld(m.x, m.y), moved: 99 };
      }
    }
    function move(e) {
      const p = at(e);
      if (!pointers.has(e.pointerId)) {
        if (e.pointerType === "mouse") {
          const i = hitPoint(p.x, p.y, 10);
          const region = zoom() < 2.4 ? hitRegion(p.x, p.y) : null;
          canvas.style.cursor = i >= 0 || region ? "pointer" : "grab";
          if (i !== hover) { hover = i; request(); }
        }
        return;
      }
      pointers.set(e.pointerId, p);
      if (!gesture) return;
      if (gesture.kind === "pan") {
        const dx = p.x - gesture.last.x, dy = p.y - gesture.last.y;
        gesture.moved += Math.abs(dx) + Math.abs(dy);
        gesture.last = p;
        if (gesture.moved > 6) {
          cam.tx += dx; cam.ty += dy;
          canvas.style.cursor = "grabbing";
          request();
        }
        gesture.samples.push({ t: e.timeStamp, ...p });
        if (gesture.samples.length > 6) gesture.samples.shift();
      } else if (gesture.kind === "pinch" && pointers.size >= 2) {
        const [a, b] = [...pointers.values()];
        const m = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
        const k = clamp(gesture.k0 * Math.hypot(a.x - b.x, a.y - b.y) / Math.max(gesture.d0, 1), minK(), maxK());
        cam = { k, tx: m.x - gesture.world.x * k, ty: m.y - gesture.world.y * k };
        request();
      }
    }
    function up(e) {
      const p = at(e);
      pointers.delete(e.pointerId);
      if (!gesture) return;
      if (gesture.kind === "pan" && pointers.size === 0) {
        const quick = e.timeStamp - gesture.start < 450;
        if (gesture.moved <= 6 && quick && e.type === "pointerup") tap(p.x, p.y, gesture.type);
        else {
          const s = gesture.samples;
          const a = s[0], b = s[s.length - 1];
          const dt = b.t - a.t;
          if (dt > 0 && e.timeStamp - b.t < 80 && !reduced.matches) {
            inertia = { vx: (b.x - a.x) / dt, vy: (b.y - a.y) / dt };
            request();
          } else onCamera(getCamera());
        }
        gesture = null;
        canvas.style.cursor = "grab";
      } else if (gesture.kind === "pinch") {
        if (pointers.size === 1) {
          const rest = [...pointers.values()][0];
          gesture = { kind: "pan", moved: 99, start: e.timeStamp, last: rest, samples: [{ t: e.timeStamp, ...rest }], type: e.pointerType };
        } else if (pointers.size === 0) { gesture = null; onCamera(getCamera()); }
      }
    }
    /* A trackpad pinch arrives as a wheel event with ctrlKey, and a two-finger scroll as a plain one;
       a mouse wheel sends whole notches with nothing sideways, and on a map that means zoom. */
    function wheel(e) {
      e.preventDefault();
      flight = null; inertia = null;
      const p = at(e);
      /* ⌘ + scroll (Ctrl + scroll elsewhere) is the desktop convention for zooming a canvas, and it is
         the one a mouse and a trackpad share. */
      const modified = e.ctrlKey || e.metaKey;
      const notch = e.deltaX === 0 && (e.deltaMode === 1 || (Math.abs(e.deltaY) >= 50 && Number.isInteger(e.deltaY)));
      if (modified || notch) {
        const scale = e.deltaMode === 1 ? 0.05 : notch ? 0.0022 : 0.012;
        zoomAt(p.x, p.y, Math.exp(-e.deltaY * scale), false);
      } else {
        cam.tx -= e.deltaX; cam.ty -= e.deltaY;
        request();
      }
      clearTimeout(wheel.timer);
      wheel.timer = setTimeout(() => onCamera(getCamera()), 200);
    }
    /* On the document while the map exists, not on the canvas: zooming should not need a click on
       the map first. ⌘= ⌘− ⌘0 (Ctrl elsewhere) are the browser's own page-zoom keys, taken over
       while a map is open the way any canvas application takes them; the bare keys and the arrows
       work whenever nothing is being typed. */
    function key(e) {
      if (e.defaultPrevented || e.altKey) return;
      const modified = e.metaKey || e.ctrlKey;
      const typing = e.target.closest && e.target.closest("input, textarea, select, [contenteditable]");
      if (typing && !modified) return;
      if (modified && !["=", "+", "-", "_", "0"].includes(e.key)) return;
      const c = centre();
      if (e.key === "+" || e.key === "=") zoomAt(c.x, c.y, 1.6, true);
      else if (e.key === "-" || e.key === "_") zoomAt(c.x, c.y, 1 / 1.6, true);
      else if (e.key === "0") fit(true);
      else if (e.key.startsWith("Arrow")) {
        const step = 90 / cam.k;
        const now = current();
        const dx = e.key === "ArrowLeft" ? -step : e.key === "ArrowRight" ? step : 0;
        const dy = e.key === "ArrowUp" ? -step : e.key === "ArrowDown" ? step : 0;
        flyTo(now.cx + dx, now.cy + dy, now.k, 200);
      } else return;
      e.preventDefault();
    }
    function leave() { if (hover >= 0) { hover = -1; request(); } }

    canvas.addEventListener("pointerdown", down);
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("pointercancel", up);
    canvas.addEventListener("pointerleave", leave);
    canvas.addEventListener("wheel", wheel, { passive: false });
    document.addEventListener("keydown", key);
    /* Safari's own pinch gesture events would zoom the page under the map. */
    const stopGesture = (e) => e.preventDefault();
    canvas.addEventListener("gesturestart", stopGesture);
    canvas.tabIndex = 0;
    canvas.style.cursor = "grab";

    /* ── size and theme ─────────────────────────────────────────────────── */

    function resize() {
      const r = canvas.getBoundingClientRect();
      if (!r.width || !r.height) return;
      const keep = W ? current() : null;
      W = r.width; H = r.height;
      dpr = Math.min(window.devicePixelRatio || 1, 2.5);
      canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
      sprites.clear();
      const before = fitK;
      measureFit();
      if (keep && data) place(keep.cx, keep.cy, keep.k * (fitK / before));
      else if (data) fit(false);
      while (pending.length) pending.shift()();
      request();
    }
    const sizes = new ResizeObserver(resize);
    sizes.observe(canvas);
    const themeWatch = new MutationObserver(() => { readColors(); request(); });
    themeWatch.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const scheme = matchMedia("(prefers-color-scheme: dark)");
    const onScheme = () => { readColors(); request(); };
    scheme.addEventListener("change", onScheme);
    readColors();
    if (document.fonts) document.fonts.ready.then(() => { widths.clear(); request(); });

    /* ── the interface ──────────────────────────────────────────────────── */

    /* Anything that moves the camera before the canvas has a size would be computed against a
       zero-sized view and then thrown away by the first resize; it waits instead. */
    const pending = [];
    const whenSized = (fn) => { if (W) fn(); else pending.push(fn); };

    function select(i, opts = {}) {
      sel = i;
      if (i >= 0 && opts.fly) whenSized(() => flyTo(X[i], Y[i], Math.max(cam.k, fitK * (opts.zoom || 5.5)), 560));
      request();
    }
    function fitRegion(id) {
      const r = data.regions.find((x) => x.id === id);
      if (!r) return;
      const members = range(n).filter((i) => (r.level === "region" ? data.points[i].r : data.points[i].h) === r.index);
      const b = boundsOf(members);
      flyTo((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2, Math.min(kToFit(b, view(), 50), maxK()), 600);
    }
    function getCamera() { const c = current(); return { cx: c.cx, cy: c.cy, z: c.k / fitK }; }
    function setCamera(c) { if (c) whenSized(() => { place(c.cx, c.cy, c.z * fitK); request(); }); }

    return {
      /* Returns how many points are new, when animating an update. */
      setData(next, opts) {
        setData(next, opts);
        prepareOrder();
        return anim && anim.kind === "update" ? fresh.reduce((a, b) => a + b, 0) : 0;
      },
      setStyle(s) { style = s; cloud = null; request(); },
      setLabels(s) { labelSource = s; request(); },
      select(i, opts) { select(i, opts); },
      highlight(set) { lit = set && set.size ? set : null; request(); },
      flyToPoint(i, z) { if (i >= 0) flyTo(X[i], Y[i], Math.max(cam.k, fitK * (z || 5.5)), 560); },
      fitRegion,
      fit,
      zoomBy(f) { const c = centre(); zoomAt(c.x, c.y, f, true); },
      zoomTo(z) { whenSized(() => { const c = current(); flyTo(c.cx, c.cy, fitK * z, 0); }); },
      setInsets(next) { insets = { ...insets, ...next }; },
      /* Where a point is on the canvas now, in CSS pixels. */
      screenOf(i) { return { x: X[i] * cam.k + cam.tx, y: Y[i] * cam.k + cam.ty }; },
      /* Bring a point into the part of the canvas nothing covers, moving as little as possible: a
         sense tapped low on a phone is otherwise hidden by the sheet that tap opened. */
      reveal(i) {
        whenSized(() => {
          const v = view(), m = 40;
          const sx = X[i] * cam.k + cam.tx, sy = Y[i] * cam.k + cam.ty;
          const dx = sx < v.x + m ? v.x + m - sx : sx > v.x + v.w - m ? v.x + v.w - m - sx : 0;
          const dy = sy < v.y + m ? v.y + m - sy : sy > v.y + v.h - m ? v.y + v.h - m - sy : 0;
          if (!dx && !dy) return;
          const c = current();
          flyTo(c.cx - dx / cam.k, c.cy - dy / cam.k, cam.k, 360);
        });
      },
      getCamera, setCamera,
      focus() { canvas.focus({ preventScroll: true }); },
      destroy() {
        cancelAnimationFrame(raf);
        sizes.disconnect(); themeWatch.disconnect();
        scheme.removeEventListener("change", onScheme);
        canvas.removeEventListener("pointerdown", down);
        canvas.removeEventListener("pointermove", move);
        canvas.removeEventListener("pointerup", up);
        canvas.removeEventListener("pointercancel", up);
        canvas.removeEventListener("pointerleave", leave);
        canvas.removeEventListener("wheel", wheel);
        document.removeEventListener("keydown", key);
        canvas.removeEventListener("gesturestart", stopGesture);
      }
    };
  }

  window.MeaningMap = MeaningMap;
})();
