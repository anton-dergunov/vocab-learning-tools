"""Headless consumers of the vocabulary: external systems Acervo feeds and reads back.

A consumer uses Acervo record ids but owns neither vocabulary content nor learning state. It reaches
the graph the way a job does, through `acervo.client`.
"""
