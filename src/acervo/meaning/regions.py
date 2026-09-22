"""Regions, their cheap names, and which senses best describe them.

Clustered on the **layout**, not on the vectors: a name has to sit over its points, and a cluster
found in 384 dimensions can land in pieces across the plane. One Ward tree cut twice, so every
neighbourhood lies inside one region by construction. No noise class — the long tail of minor
interests is exactly what is worth keeping on the map.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Sequence

import numpy as np

MIN_FOR_REGIONS = 150
REGIONS, HOODS = 8, 30
NEIGHBOURS = 5


def cut(coords: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """Region and neighbourhood of every point, or nothing below MIN_FOR_REGIONS, where regions churn
    from one layout to the next and a young language is better shown as plain words."""
    if len(coords) < MIN_FOR_REGIONS:
        return None
    from scipy.cluster.hierarchy import fcluster, linkage

    tree = linkage(coords, method="ward")
    return fcluster(tree, REGIONS, criterion="maxclust") - 1, fcluster(tree, HOODS, criterion="maxclust") - 1


def ranks(vectors: np.ndarray, hoods: np.ndarray | None) -> np.ndarray:
    """0–1, how central each sense is to its neighbourhood: the order labels are allowed in, so the
    middle distance shows the words that best describe each place."""
    if hoods is None:
        similarity = vectors @ vectors.mean(axis=0)
        return (similarity - similarity.min()) / max(float(similarity.max() - similarity.min()), 1e-9)
    out = np.zeros(len(vectors))
    for hood in np.unique(hoods):
        members = np.where(hoods == hood)[0]
        similarity = vectors[members] @ vectors[members].mean(axis=0)
        order = np.argsort(np.argsort(-similarity))
        out[members] = 1 - order / max(len(members) - 1, 1)
    return out


def neighbours(vectors: np.ndarray, lexemes: Sequence[str], k: int = NEIGHBOURS) -> list[list[int]]:
    """Each sense's nearest senses **of other words**: the word's own senses are drawn separately, as
    the arcs between them."""
    similarity = vectors @ vectors.T
    out = []
    for i in range(len(vectors)):
        order = np.argsort(-similarity[i])
        out.append([int(j) for j in order if lexemes[j] != lexemes[i]][:k])
    return out


def central_words(headwords: Sequence[str], vectors: np.ndarray, members: Sequence[int], top: int = 3) -> list[str]:
    centre = vectors[list(members)].mean(axis=0)
    words: list[str] = []
    for i in sorted(members, key=lambda i: -float(vectors[i] @ centre)):
        if headwords[i] not in words:
            words.append(headwords[i])
        if len(words) == top:
            break
    return words


# Function words, plus the boilerplate definitions are written in ("Dicho de una persona:", "showing
# …"), which otherwise wins every cluster it appears in.
STOP = {
    "es": set("""dicho dicha indica indicar sirve ninguna ninguno vez tal poca poco usar suele a al algo
        alguien alguna algunas alguno algunos ante antes aquel aquella así aun aunque bajo bien cada casi
        como con contra cosa cosas cual cuales cuando de del desde donde dos durante e el ella ellas
        ellos en entre era es esa esas ese eso esos esta estas este esto estos etc forma fue ha hace
        hacer hacia hasta la las le les lo los mas más me menos mismo mucho muy ni no nos o otra otras
        otro otros para pero persona personas por porque que qué quien quién se ser si sin sino sobre
        su sus también tan tanto te tener tiene todo todos tu un una uno unos usa usado usada utiliza
        ya y manera modo acción efecto relativo relativa perteneciente situación hecho estar decir dar
        tipo parte cierto cierta propio propia general especialmente generalmente frecuencia expresión""".split()),
    "en": set("""a about above after again against all also an and any are as at be been being below
        between both but by can could did do does doing done down during each especially etc few for
        from further had has have having he her here hers him his how i if in into is it its itself
        just kind like made make makes may me more most much must my no nor not of off often on once
        one ones only or other our out over own person people same she should so some someone
        something such than that the their them then there these they thing things this those through
        to too under until up upon used using usually very was way we were what when where which while
        who whom why will with without would you your act state quality manner particular typically
        showing shows shown extremely rather because able never someone's somebody""".split()),
}


def terms(definitions: Sequence[str], labels: np.ndarray, language: str, top: int = 3) -> dict[int, list[str]]:
    """c-TF-IDF: each cluster's definitions read as one document, terms scored against every other
    cluster, so what comes out is what is distinctive about this one."""
    stop = STOP.get(language.split("-")[0], set())
    counts: dict[int, Counter] = defaultdict(Counter)
    for definition, label in zip(definitions, labels):
        counts[int(label)].update(t for t in re.findall(r"[^\W\d_]{3,}", definition.lower()) if t not in stop)
    total: Counter = Counter()
    for c in counts.values():
        total.update(c)
    average = sum(sum(c.values()) for c in counts.values()) / max(len(counts), 1)
    out: dict[int, list[str]] = {}
    for label, c in counts.items():
        size = sum(c.values()) or 1
        scored = sorted(c, key=lambda t: (-(c[t] / size) * math.log(1 + average / total[t]), t))
        out[label] = [t for t in scored if c[t] > 1][:top] or scored[:top]
    return out
