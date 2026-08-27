# Acervo Anki synchronization

This deployment slice runs Anki's official sync server and a separate headless
Acervo robot. Anki Desktop is not required. Server and robot use the same pinned
`anki==26.8.1` image so their sync protocol versions stay aligned.

## Storage and network model

The deployment is named `acervo`; Anki names are limited to its two internal
services. Persistent paths below the Acervo root are:

```
data/anki-server
data/anki-robot
input
backups
releases
secrets.env
```

The default roots are `~/.acervo` locally, `/volume1/docker/acervo` on Synology,
and `/opt/acervo` on other Linux hosts. A root-owned `/etc/acervo-root` file may
contain a different absolute path.

Port 27701 is bound to `127.0.0.1` by default. Keep it private: use an SSH
tunnel, Tailscale, or a TLS reverse proxy for remote clients. Do not expose the
unencrypted sync endpoint directly to the public internet. To bind on a trusted
LAN, change `ACERVO_BIND_ADDRESS` in `deployment.env` to the host's LAN address.

## Local Docker Desktop deployment

Docker Desktop must be running. The first command prompts for a username and a
hidden password, stores them only in `~/.acervo/secrets.env` with mode 600, and
starts the official server:

```bash
./deploy.sh --local --configure-credentials
docker compose -p acervo \
  --env-file "$HOME/.acervo/deployment.env" \
  --env-file "$HOME/.acervo/secrets.env" \
  -f deploy/acervo/compose.yaml ps
```

Place a manifest and its relative media under `~/.acervo/input`, then run one of
the robot commands:

```bash
docker compose -p acervo \
  --env-file "$HOME/.acervo/deployment.env" \
  --env-file "$HOME/.acervo/secrets.env" \
  -f deploy/acervo/compose.yaml --profile tools run --rm anki-robot \
  bootstrap-upload /input/manifest.json
```

Use `push /input/manifest.json` for routine updates and `export-state` to emit
review state as JSON. A routine push syncs down first, refuses a required full
sync in either direction, updates by immutable `AcervoNoteId`, and syncs media
to completion. It preserves card IDs, scheduling, and non-`acervo::` tags.

## Remote deployment

The remote account needs Docker Compose and either root access or non-interactive
sudo rights (so credential standard input remains reserved for Acervo). For
Synology:

```bash
./deploy.sh --target anton@nas --root /volume1/docker/acervo \
  --configure-credentials --remember-target
```

For another Linux server, omit `--root` to use `/opt/acervo`. The remembered SSH
target is stored in the ignored `.acervo-deploy` file. Release archives contain
code and configuration, never `secrets.env`. Credentials are sent on standard
input rather than in a command argument.

Each replacement first copies collection databases and media indexes into a
timestamped backup and keeps the newest ten. Full multi-gigabyte media snapshots
are a separate operational backup tier and should be handled by NAS snapshots or
another backup system. Server data, robot data, backups, and inputs live outside
release directories and survive upgrades.

`--reset-data` is destructive and requires typing `RESET ACERVO DATA`. It is not
needed for upgrades.

## Manifest contract

The accepted version-one shape is:

```json
{
  "schema_version": 1,
  "notes": [{
    "note_id": "8fb56fd8-49f1-4498-91f6-ab78c98f95ed",
    "lexeme_id": "ff3a0df4-1612-411c-bda6-ae2aa35d4c66",
    "deck": "Spanish::Vocabulary",
    "sentence": "La balsa",
    "translation": "The raft",
    "comment_html": "<p>A vessel.</p>",
    "tags": ["acervo::topic::travel"],
    "image_path": "media/balsa.webp",
    "audio_path": "media/balsa.mp3"
  }]
}
```

Media paths must be relative to the manifest and cannot escape its directory.
Media are imported under content-addressed names. Duplicate manifest identities
or duplicate collection `AcervoNoteId` values fail before any mutation. Notes
absent from a manifest remain untouched.

## Bootstrap and adoption

Use `bootstrap-upload` only for a genuinely empty sync account. It authorizes
only Anki's `FULL_UPLOAD` result.

For a collection created on mobile first, stop all other syncing, ensure the
robot has no local collection, then run:

```bash
docker compose -p acervo \
  --env-file "$HOME/.acervo/deployment.env" \
  --env-file "$HOME/.acervo/secrets.env" \
  -f deploy/acervo/compose.yaml --profile tools run --rm anki-robot \
  adopt-server --confirm-no-other-clients
```

This downloads the existing collection, installs the Acervo note type, and
performs the one manually confirmed full upload. Routine commands never change
the note type. A template or schema mismatch stops and requires a future explicit
migration workflow.

## Mobile acceptance checklist

Test fresh-account bootstrap and mobile-first adoption separately.

- In current AnkiMobile or AnkiDroid, set the custom sync-server base URL with a
  trailing slash, for example `https://anki.example.net/`.
- Enable both image and audio synchronization.
- Sync the fresh account and confirm its Acervo cards and media download.
- Review a card, sync, push changed manifest content, sync again, and verify the
  card's scheduling and review count remain intact.
- For mobile-first adoption, close or disable every other client during the
  confirmed adoption window.
- Upgrade the server and robot together before adopting clients that require a
  newer sync protocol.

Before an Anki upgrade, rerun `scripts/test_anki_sync_docker.sh`. The automated
test uses real official server and client code, isolated temporary storage, and
tears down only its uniquely named Compose project.
