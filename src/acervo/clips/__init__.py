"""Choosing a clip, and nothing about the corpus itself.

The spoken-usage corpus is a separate repository and a separate service; this package is about
which of its segments illustrates which sense. It stands alone the way `acervo.images` does — it
may import `acervo.models` and the narrow retrieval client, and nothing else of Acervo's.
"""
