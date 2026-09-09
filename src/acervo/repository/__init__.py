"""The only code that touches the database.

Routes, services and jobs all go through it — the server-side twin of the rule the interface already
lives by, where every read and write goes through `AcervoRepository` and never through the store.

A repository function is a transaction: it opens its own connection and closes it. There is no
request-scoped session, and that is not tidiness. Capture makes two model calls of up to 120 seconds
each; a request-scoped connection plus `BEGIN IMMEDIATE` would hold an exclusive write transaction
across both and block every other request for up to four minutes. Owning connection lifetime here
makes that impossible to write by accident. Anything that must be atomic across several operations is
*one* repository function.
"""
