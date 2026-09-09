"""External dictionaries, from the server's side.

Two jobs only. Say which compiled dictionaries this server holds, so the interface can offer them;
and answer an online lookup on the client's behalf, so the User-Agent obligation is honoured in one
place and the browser never depends on a third party's CORS headers.

Notably absent: a lookup route for compiled dictionaries. The artifact is served as a static file
with byte ranges, so "this device, then the server" is the same reader over a different byte source,
and the format is never implemented twice.
"""
