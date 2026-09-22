"""Senses onto a plane, and a new plane onto the old one.

UMAP with the settings `experiments/meaning-space/` chose by looking: a small `min_dist` lets related
senses clump, which is what turns an even disc into land with sea between it. The cost it measured
is stability, and two things buy it back. A new layout **starts from the previous one** — every sense
the last map held begins where it was, and a new one beside its nearest held senses — and is then
**aligned onto it**, rotated, reflected, scaled and shifted to fit the points both share. Nothing is
pinned: a sense still goes where its meaning now puts it. Measured on the owner's 1,443 Spanish
senses, one edited sense moved the median point 140 of 1,000 units from a cold start and 37 from a
warm one; 2% more words, 179 and 39. A fixed seed alone keeps nothing in place: the same vocabulary
less 2% once came back mirrored.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

NEIGHBOURS = 12
MIN_DIST = 0.1
SEED = 42
SIDE = 1000.0


def start(vectors: np.ndarray, ids: Sequence[str], previous: Mapping[str, Sequence[float]]) -> np.ndarray | None:
    """Where each sense begins: where the last map put it, or — a sense it did not hold — at the
    mean of its three nearest senses that it did. None when too little is shared to start from."""
    held = [i for i, sense in enumerate(ids) if sense in previous]
    if len(held) < 3:
        return None
    placed = np.array([previous[ids[i]] for i in held], dtype=float)
    out = np.zeros((len(ids), 2))
    for i, sense in enumerate(ids):
        if sense in previous:
            out[i] = previous[sense]
        else:
            nearest = np.argsort(-(vectors[held] @ vectors[i]))[:3]
            out[i] = placed[nearest].mean(axis=0)
    # UMAP optimises from a start of modest scale; the frame is restored by `align` afterwards.
    return (out - out.mean(axis=0)) / max(float(out.std()), 1e-9)


def layout(vectors: np.ndarray, init: np.ndarray | None = None) -> np.ndarray:
    """Two coordinates per row, in a SIDE × SIDE square. `init` is where to start, from `start`."""
    n = len(vectors)
    if n == 0:
        return np.zeros((0, 2))
    if n <= 3:
        # Too few for a neighbourhood graph; a word or three simply sit apart, in a row.
        return np.array([[SIDE / 2 + (i - (n - 1) / 2) * SIDE / 4, SIDE / 2] for i in range(n)])
    import umap

    reducer = umap.UMAP(
        n_neighbors=min(NEIGHBOURS, n - 1), min_dist=MIN_DIST, metric="cosine", random_state=SEED,
        # A fixed seed is single-threaded anyway; saying so keeps UMAP from warning about it.
        n_jobs=1,
        # A spectral start needs a connected graph, which a handful of senses may not make.
        init=init if init is not None else ("spectral" if n > 20 else "random"),
    )
    return normalise(reducer.fit_transform(vectors))


def normalise(coords: np.ndarray) -> np.ndarray:
    low, high = coords.min(axis=0), coords.max(axis=0)
    scale = SIDE / max(float((high - low).max()), 1e-9)
    return (coords - (low + high) / 2) * scale + SIDE / 2


def procrustes(moving: np.ndarray, fixed: np.ndarray) -> tuple[np.ndarray, float, np.ndarray, np.ndarray]:
    """The rotation (reflection allowed), scale and shift taking `moving` closest to `fixed`."""
    mu_m, mu_f = moving.mean(axis=0), fixed.mean(axis=0)
    a, b = moving - mu_m, fixed - mu_f
    u, s, vt = np.linalg.svd(a.T @ b)
    rotation = u @ vt
    scale = float(s.sum() / max((a ** 2).sum(), 1e-12))
    return rotation, scale, mu_m, mu_f


def align(coords: np.ndarray, ids: Sequence[str], previous: Mapping[str, Sequence[float]]) -> np.ndarray:
    """`coords` moved onto the frame the previous map was drawn in, fitted on the senses both hold.

    Too few in common, and the new map stands in its own frame: three points fix a plane's rotation,
    and fewer would fit noise.
    """
    shared = [i for i, sense in enumerate(ids) if sense in previous]
    if len(shared) < 3:
        return coords
    moving = coords[shared]
    fixed = np.array([previous[ids[i]] for i in shared], dtype=float)
    rotation, scale, mu_m, mu_f = procrustes(moving, fixed)
    return (coords - mu_m) @ rotation * scale + mu_f
