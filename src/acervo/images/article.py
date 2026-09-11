"""Which example a picture is drawn from, and which senses already have one.

The assembling lives in `acervo.article`, which every enrichment reads; what is left here is the
part that is only ever about pictures. `anchor_for` is a free function over a shared `SenseView`
rather than a property on it, and that is the right shape: "which example does the picture
illustrate" is a question *about* a sense, not a fact the sense carries — a clip selector and a
pronunciation pipeline would each answer it differently or not at all.
"""

from __future__ import annotations

from acervo.article import ArticleView, SenseView, build_articles, live

__all__ = ["ArticleView", "SenseView", "anchor_for", "build_articles", "drawn_senses", "live"]

# Which example a picture is drawn from, best first. A generated example outranks Tatoeba and
# Wiktionary because it was written for *this* sense, in the vocabulary's own languages, carrying a
# translation and both matched forms; the other two are chosen for neither and read worse.
EXAMPLE_PREFERENCE = {"attestation": 0, "manual": 1, "llm": 2, "tatoeba": 3, "wiktionary": 4}

# A clip never anchors a picture, and it is excluded rather than ranked last. Ranking it last would
# still pick it when it is the only example, and falling back to the sense is the wanted outcome
# rather than a worse one: the clip is real footage of the situation, so illustrating it re-renders
# what the learner is about to watch, and the two are heading for separate full-screen surfaces
# where one sentence drawn twice would show the same thing twice.
UNANCHORABLE_ORIGINS = frozenset({"subtitle"})


def anchor_for(sense: SenseView) -> dict | None:
    """The example this sense's picture illustrates, or nothing — which is a supported state.

    Nothing means "the picture belongs to the sense": the brief writer invents the scene from the
    definition and the glosses instead. That is the right answer for a sense with no examples and
    for one whose only example is a clip.
    """
    candidates = [
        example
        for example in sense.examples
        if example.get("origin", "llm") not in UNANCHORABLE_ORIGINS
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda example: (
            EXAMPLE_PREFERENCE.get(example.get("origin", "llm"), 9),
            example.get("createdAt", ""),
            example.get("id", ""),
        ),
    )


def drawn_senses(changes: dict[str, list[dict]]) -> set[str]:
    """The senses that already hold a picture, so a sweep can leave them alone."""
    return {
        prompt.get("senseId", "")
        for prompt in live(changes.get("imagePrompts", []))
        if prompt.get("imageRef")
    }
