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
#
# A clip ranks last rather than being excluded. It used to be excluded, on the theory that drawing
# real footage re-renders what the learner is about to watch; in practice a clip's sentence makes a
# good scene, and the picture and the clip share one card rather than two full-screen surfaces. So a
# clip anchors only a sense that has no other sentence.
EXAMPLE_PREFERENCE = {"attestation": 0, "manual": 1, "llm": 2, "tatoeba": 3, "wiktionary": 4, "subtitle": 5}


def anchor_for(sense: SenseView) -> dict | None:
    """The example this sense's picture illustrates, or nothing — which is a supported state.

    Nothing means "the picture belongs to the sense": the brief writer invents the scene from the
    definition and the glosses instead. That is the answer only for a sense with no examples at all.
    """
    if not sense.examples:
        return None
    return min(
        sense.examples,
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
