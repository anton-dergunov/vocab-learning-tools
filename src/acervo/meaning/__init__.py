"""The meaning map: one language's senses laid out by what they mean (docs/features/meaning-map.md).

Senses in, a map out — embedded, laid out, cut into regions, labelled, traced. **The package stands
alone**: it imports nothing of Acervo's (`test_layering.py`), so it knows no owner, no database and no
wire vocabulary. `services/meaning.py` is the binding layer that reads the graph, keeps the cache and
the artifact beside the database, and decides what a missing language is called on the wire.

Every choice here was settled on the owner's real vocabulary in `experiments/meaning-space/`, whose
README has the numbers; the constants carry those values rather than new ones.
"""
