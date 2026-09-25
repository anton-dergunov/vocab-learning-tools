# Observability · what Acervo should be able to tell you

**Status:** Open. It holds the question rather than a schedule; nothing here blocks anything. The
most useful single change is §3's request id. Written after a loop render failed on the deployed
server and the server said nothing at all — not in `docker logs`, not in `admin`, nowhere a person
would look.

Acervo is a single-owner system with no operations team, which changes what this is for. There is no
alerting to build and no dashboard anybody will watch. The whole question is narrower and harder:
**when something the owner asked for does not happen, can they find out why without reading the
source?**

---

## §1 · What exists, and the shape to copy

Two logs, both built: the model-call log (`models/journal.py`, read back by
`python -m acervo.admin calls`) and the job log (`work/journal.py`), which exists because a job's
failure was once recorded only in its row's JSON and was invisible from the command line. Both
share a shape any later log should copy: `key=value` pairs so a `grep` is a question with an answer;
the emitting package **never configures**, so the file and the rotation belong to the deployment;
and **a log that cannot be opened warns and is dropped**, because a server that cannot write its
log should still do its work.

## §2 · What is still silent

Each of these is an event the owner could reasonably ask about afterwards. The column that matters is
the third: not everything wants a log line, and a log that records everything is one nobody reads.

| Event | Today | Probably belongs in |
|---|---|---|
| A graph write refused on a stale revision | 4xx, nothing kept | a log line — it is rare and it means two devices disagreed |
| A cursor pull that returned nothing for a device that expected rows | silent | nothing; the replica already shows it |
| A capture that produced no word | the job record | the job log, already |
| An auth failure | one 401, indistinguishable from every other | a log line, and **which** failure — expiry, a rotated key and a deleted account are one message today |
| A deploy | the installer's own output, not kept | a line in the job log's file, so "what changed before this broke" is answerable |
| A dictionary lookup that fell through to an online source | silent | nothing; it is per-keystroke |
| Media written or removed | silent | a log line for removal only: it is the destructive one |

## §3 · The one hard problem

**Nothing joins the containers.** A loop render spends its time in `acervo-lexibeat-1`, calls home
seventy-odd times to `acervo-server-1`, and the two logs share no identifier — so a failure in one
cannot be matched to its cause in the other except by timestamp and hope. The job log now carries
`operationId`, which is half of it; the other half is that `POST /pronunciations/take` receives
nothing saying which render asked. A request id threaded from the job through the render request and
onto every take would close it, and it is the single change that would most improve this.

The same gap exists toward `speech-retrieval`, and would exist for any future companion service, so
it is worth solving once rather than per service.

## §4 · What this is not

Not metrics, not tracing, not a time-series database, not a dashboard. One owner, one machine, a few
hundred jobs a month. Two rotating text files and an `admin` command that reads them back is the
right size, and the discipline to keep is that **every line has a reader in mind** — a question
somebody will actually ask, phrased so a `grep` answers it.
