"""Pronunciation: which words to say, in what language and voice, and saying them.

It stands alone the way `images/` and `clips/` do — it imports the provider package and the article
view and nothing else of Acervo's (`tests/unit/server/test_layering.py`). `services/pronunciations.py`
is the binding layer that reads `Settings`, the owner's chains and settings, the graph and the media
directory, and turns this package's answers into Acervo's wire vocabulary.
"""
