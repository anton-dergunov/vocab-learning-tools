"""Stories: a few of the owner's words, told back to them as a short illustrated tale.

Standalone the way `acervo.images` is — it imports `acervo.models` and nothing else of Acervo's, and
`tests/unit/server/test_layering.py` enforces it. `services/stories.py` is the binding layer that
knows about settings, the graph and the media directory.

Four calls in a fixed order, and the batching in each is load-bearing:

1. `write` — one hot call, the story itself.
2. `translate` — one cold call, the **whole** story at once, so a pronoun or a recurring name is
   translated consistently rather than each paragraph being translated blind.
3. `illustrate.brief` — one call covering **every part**, so the same character can be kept in the
   same coat across four pictures. This is `images/brief.py`'s argument for batching a word's
   senses, and it matters more here.
4. `illustrate.draw` — one image call per part, every one in the same style.
"""

from acervo.stories.types import StoryType, StoryTypes, load_types, story_types
from acervo.stories.write import Part, StoryRefused, StoryWriter, Written

__all__ = [
    "Part", "StoryRefused", "StoryType", "StoryTypes", "StoryWriter", "Written",
    "load_types", "story_types",
]
