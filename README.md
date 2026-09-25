# Acervo

Acervo is a self-hosted, offline-first store for vocabulary chosen by one learner. One Python
service holds the durable owner-scoped copy; the PWA and native macOS host keep a complete IndexedDB
replica so vocabulary remains readable and editable without a network connection.

Words are added by pasting a word, or the sentence it was met in: the entry is written for you,
shown for review, and kept in an inbox until you approve it. A word already in the store is
recognised as one rather than added twice. The same route walks a file of unstructured notes into
the inbox an entry at a time.

## Core model

The canonical graph separates eight records with different lifetimes:

- `vocabulary` — a language being studied, and the languages to translate it into;
- `topic` — an editable grouping label with an optional symbolic icon;
- `lexeme` — the word or phrase being learned;
- `sense` — one ordered meaning with target-language definition and multilingual glosses;
- `attestation` — the verbatim context in which the learner encountered it;
- `example` — a curated or generated sentence with explicit language and provenance;
- `imagePrompt` — a regenerable prompt associated with a lexeme or sense;
- `studyState` — statistics reported by an external learning system.

Every record uses a client-generated 15-character ID, belongs to one account, and carries
replication-ready edit metadata. Markdown vocabulary files and extended-article JSON are not
application storage formats.

See [the design document](docs/design.md) for the product decisions,
[the server design](docs/server.md) for what runs on the always-on machine, and
[the application guide](docs/app.md) for deployment details.

## Development

Requirements are Python 3.12, Node.js 20+, Docker for server integration tests, and macOS 14 plus
Xcode/XcodeGen for the native host.

```bash
uv pip install -r requirements/dev.txt
uv pip install -e .
npm install --prefix web

pytest
npm --prefix web run test
npm --prefix web run build
npm run test:pwa
npm run test:mac
```

Run the application stack locally with:

```bash
./deploy.sh --local --configure-credentials
```

Self-registration is disabled and there is no superuser. Accounts are made one at a time, with the
password read from the terminal:

```bash
./deploy.sh --create-account
```

The API exposes password login and token refresh; there is no generic CRUD surface over the
vocabulary at all — the graph routes are the only way in or out.

## Disposable demonstration data

Once an account exists, insert owner-scoped demonstration entries with:

```bash
docker exec -i acervo-server-1 \
  python -m acervo.admin seed --owner-email learner@account.example.com
```

It writes through the service layer rather than over HTTP, so it needs no password, and it is
idempotent: a second run skips what the account already holds. The sample graph includes thirteen
editable starter topics plus fifteen lexemes covering multilingual glosses, phrases, attestations,
generated examples, prompts, study statistics, and a Chinese reading.

## Components

- `web/src/domain.ts` — canonical TypeScript records and runtime validation.
- `web/src/localDatabase.ts` — IndexedDB replica and atomic storage operations.
- `web/src/repository.ts` — offline CRUD, tombstones, and pending markers.
- `src/acervo/` — the server: the canonical schema, the graph routes, capture, the dictionary
  routes, auth and the static surfaces. See [the server design](docs/server.md).
- `deploy/acervo/server/` — the image it ships in.
- `src/acervo/client.py` — the one HTTP client against the API; every job and script goes through it.
- `src/acervo/dictionaries/` — the external-dictionary compiler.
- `src/acervo/images/` — the sense-image pipeline: a brief writer and a renderer. Stands alone
  on `src/acervo/models/`, so a route and a batch sweep share it.
- `src/acervo/jobs/images/` — the unattended half: the run directory, the sweep, the import.
- `src/acervo/consumers/anki/` — headless Anki consumer infrastructure.
- `experiments/` — experiments, spikes and benchmark tooling, outside the distribution and never imported by the service.
- `macos/` — native host for the shared web interface.

Deployment is designed for shared hosts and uses dedicated configurable listeners. It never assumes
ownership of ports 80/443 or unrelated proxy, Tailscale, firewall, or Docker configuration. On a
tailnet, Acervo is published as its own Tailscale service, which gives it a hostname and a 443 of
its own without touching the host's — what Android requires to install it alongside another
self-hosted app.
