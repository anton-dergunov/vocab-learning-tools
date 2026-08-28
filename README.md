# Acervo

Acervo is a self-hosted, offline-first store for vocabulary chosen by one learner. PocketBase holds
the durable owner-scoped copy; the PWA and native macOS host keep a complete IndexedDB replica so
vocabulary remains readable and editable without a network connection.

The current iteration provides the core data model and persistence foundation. The vocabulary UI,
device synchronization, and capture workflow are separate later stages.

## Core model

The canonical graph separates six records with different lifetimes:

- `lexeme` — the word or phrase being learned;
- `sense` — one ordered meaning with target-language definition and multilingual glosses;
- `attestation` — the verbatim context in which the learner encountered it;
- `example` — a curated or generated sentence with explicit language and provenance;
- `imagePrompt` — a regenerable prompt associated with a lexeme or sense;
- `studyState` — statistics reported by an external learning system.

Every record uses a client-generated PocketBase-compatible ID, belongs to one account, and carries
replication-ready edit metadata. Markdown vocabulary files and extended-article JSON are not
application storage formats.

See [the design document](docs/acervo-design.md) for the product decisions and
[the application guide](docs/acervo-app.md) for deployment details.

## Development

Requirements are Python 3.12, Node.js 20+, Docker for server integration tests, and macOS 14 plus
Xcode/XcodeGen for the native host.

```bash
pip install -r requirements/dev.txt
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

PocketBase creates accounts only through its administration interface. Self-registration is
disabled. The application API exposes password login and token refresh; vocabulary collections are
not exposed through generic public CRUD routes.

## Disposable demonstration data

After creating an Acervo user in PocketBase, insert five owner-scoped demonstration entries with:

```bash
python scripts/seed_acervo_demo.py \
  --server-url https://acervo.example.com \
  --owner-email learner@account.example.com
```

The command prompts for PocketBase superuser credentials, stores none of them, and is idempotent.
The sample graph covers multilingual glosses, phrases, attestations, generated examples, prompts,
study statistics, and a Chinese reading.

## Components

- `web/src/domain.ts` — canonical TypeScript records and runtime validation.
- `web/src/localDatabase.ts` — IndexedDB replica and atomic storage operations.
- `web/src/repository.ts` — offline CRUD, tombstones, and pending markers.
- `deploy/acervo/pocketbase/pb_migrations/` — canonical server schema.
- `deploy/acervo/pocketbase/pb_hooks/` — validation, authentication, health, and releases.
- `src/vocabgen/provider/` — reusable LLM, TTS, and vision provider factory.
- `src/vocabgen/anki_sync/` — headless Anki consumer infrastructure.
- `macos/` — native host for the shared web interface.

Deployment is designed for shared hosts and uses dedicated configurable listeners. It never assumes
ownership of ports 80/443 or unrelated proxy, Tailscale, firewall, or Docker configuration.
