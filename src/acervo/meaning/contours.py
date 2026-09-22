"""Where the vocabulary is thick, as iso-lines: the coast and the rings inside it.

Traced here rather than on the device, so the device draws them with no library. The coast sits high
enough (16% of the peak density) that thin sea between clumps stays sea.
"""

from __future__ import annotations

import numpy as np

LEVELS = (0.16, 0.34, 0.56, 0.8)
BANDWIDTH = 0.055
GRID = 150


def contours(coords: np.ndarray) -> list[list]:
    """`[level, [x, y, x, y, …]]` per line, in map coordinates."""
    if len(coords) < 5:
        return []
    import contourpy
    from scipy.stats import gaussian_kde

    kde = gaussian_kde(coords.T, bw_method=BANDWIDTH)
    low, high = coords.min(axis=0), coords.max(axis=0)
    pad = 0.06 * float((high - low).max())
    xs = np.linspace(low[0] - pad, high[0] + pad, GRID)
    ys = np.linspace(low[1] - pad, high[1] + pad, GRID)
    gx, gy = np.meshgrid(xs, ys)
    density = kde(np.vstack([gx.ravel(), gy.ravel()])).reshape(gx.shape)
    generator = contourpy.contour_generator(gx, gy, density)
    peak = float(density.max())
    out = []
    for level, fraction in enumerate(LEVELS):
        for line in generator.lines(peak * fraction):
            if len(line) < 6:
                continue
            out.append([level, [round(float(v), 1) for point in line[::2] for v in point]])
    return out
