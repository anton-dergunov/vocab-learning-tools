"""One ingest endpoint, several thin transports.

Everything intelligent lives here, so a transport is a single authenticated POST: an iOS Shortcut, an
Android share target or the Obsidian ingest script all submit text and get back either an entry or a
reason there is none.

Two model calls, deliberately. The first decides what the text is *about* — which word, which
language, which of the sentences are the learner's — and that answer is what makes the duplicate
check and the file walk possible at all. Only then is an article worth generating.
"""
