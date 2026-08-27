# Acervo Anki synchronization

This deployment slice runs Anki's official sync server and a separate headless
Acervo robot. Anki Desktop is not required. Server and robot use the same pinned
`anki==26.8.1` image so their sync protocol versions stay aligned.

## Start here: new empty account

This is the shortest route when the mobile app contains nothing you need to
keep. Commands use placeholders; substitute the SSH destination and Acervo root
for the server being deployed.

### 1. Deploy the server

For a Synology installation:

```bash
./deploy.sh --target user@server.example.com --root /volume1/docker/acervo \
  --configure-credentials --remember-target --bind-address 0.0.0.0
```

For ordinary Linux, use `/opt/acervo`. The username and hidden password prompted
for here are the credentials that the mobile app will use.

On the first run, downloading Python and building Anki can take several minutes.
Lines about unknown macOS extended-header keywords are warnings from an older
archive and do not mean the deployment failed. A successful run ends with:

```text
Acervo Anki sync server is healthy at 0.0.0.0:27701
```

Future archives omit those macOS attributes.

### 2. Check that it is running

Because `--remember-target` was used, this needs no hostname:

```bash
./deploy.sh --status
```

Expected output contains `state=running`, `health=healthy`, and a published port
ending in `:27701`. The sync server is an API, not a website, so opening `/` in a
browser may show an empty page or an HTTP error even when it is healthy.

### 3. Choose the mobile URL

Use exactly one access method:

| Access method | Deployment setting | Mobile URL |
| --- | --- | --- |
| Tailscale | `--bind-address 0.0.0.0` | `http://server-name.tailnet-name.ts.net:27701/` |
| Trusted local network | `--bind-address 0.0.0.0` | `http://192.0.2.10:27701/` |
| HTTPS reverse proxy | Keep the default `127.0.0.1` | `https://anki.example.com/` |

For Tailscale, install and connect Tailscale on the server and phone, then use
the server's Tailscale DNS name with `http`, port 27701, and the final slash.
Tailscale encrypts the connection. Do not expose port 27701 directly to the
public internet. `0.0.0.0` also listens on the local network, so use the server
firewall and Tailscale ACLs as appropriate.

### 4. Put one test card on the empty server

“Bootstrap upload” means “create the first server collection.” It is run exactly
once, while the account is empty. This command uploads the included harmless
connection-test card and runs the headless robot on the server:

```bash
scripts/acervo_anki_remote.sh bootstrap-upload \
  examples/anki-sync-smoke/manifest.json
```

It may ask for the server's sudo password. Success includes:

```json
"operation": "bootstrap-upload",
"sync": "full-upload-complete"
```

For later content changes, use `push` instead:

```bash
scripts/acervo_anki_remote.sh push path/to/manifest.json
```

### 5. Connect the mobile app

For AnkiMobile on iPhone or iPad:

1. From the deck list, tap the gear and open **Preferences → Syncing**.
2. Set **Self-hosted sync server** to the URL from step 3.
3. Leave **Sync Sounds & Images** enabled.
4. Tap **Synchronize** and enter the username and password created in step 1.
5. If asked for a direction, choose the server/AnkiWeb/download side.

For AnkiDroid on Android:

1. Open **Settings**, then **Sync** or **Advanced**, depending on the version.
2. Enable **Custom sync server** and enter the URL from step 3.
3. Leave **Fetch media on sync** enabled.
4. Tap the circular sync button and enter the username and password from step 1.
5. If asked for a direction, choose the remote/AnkiWeb/download side.

The mobile deck list should now contain **Acervo → Connection Test**. At that
point the complete server-to-mobile route works. The remaining sections are
reference material for real manifests, upgrades, backups, and existing mobile
collections.

## Reference: storage and network model

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
LAN or tailnet, deploy with `--bind-address` set to the host's private address
or `0.0.0.0`. The default remains loopback.

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

The remote account needs Docker Compose and either root or sudo access. For
Synology:

```bash
./deploy.sh --target user@server.example.com --root /volume1/docker/acervo \
  --configure-credentials --remember-target
```

For another Linux server, omit `--root` to use `/opt/acervo`. The remembered SSH
target is stored in the ignored `.acervo-deploy` file. Release archives contain
code and configuration, never `secrets.env`.

The deployment does not use SCP or SFTP. Synology installations that disable
those subsystems are supported by streaming the archive, installer, and initial
credentials through ordinary SSH. Credentials enter a mode-600 temporary file
through standard input and never appear in a command argument. Temporary uploads
are removed after installation, and ordinary sudo may prompt in the final
terminal session.

For trusted-LAN testing, explicitly publish the port beyond loopback:

```bash
./deploy.sh --target user@server.example.com --root /volume1/docker/acervo \
  --bind-address 0.0.0.0
```

This makes unencrypted HTTP reachable on the host network, so use it only on a
network you trust and restrict port 27701 with the host firewall. For normal
remote use, either reach this private binding through Tailscale or keep the
loopback default and put an HTTPS reverse proxy in front of it.

If a previous deployment failed with `subsystem request failed`, rerun the same
command after updating this checkout; there is no partial release to clean up.

### Remote robot commands

Use `scripts/acervo_anki_remote.sh`; it validates the manifest, packages only
the manifest and referenced media, streams them over SSH, and invokes the robot.
It remembers the same target as `deploy.sh` and detects the standard remote root.
Pass `--target` or `--root` only when overriding those values.

```bash
scripts/acervo_anki_remote.sh bootstrap-upload path/to/manifest.json
scripts/acervo_anki_remote.sh push path/to/manifest.json
scripts/acervo_anki_remote.sh export-state
scripts/acervo_anki_remote.sh adopt-server
```

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

## Reference: adopting an existing mobile collection

Skip this section when the mobile app contains nothing worth keeping; use the
quick start instead. When a mobile collection must be preserved:

1. Export a mobile backup and stop every other client from syncing.
2. Point mobile at an empty Acervo server and choose mobile/upload when prompted.
3. Wait for collection and media upload to finish.
4. Ensure the robot collection does not exist, then run:

   ```bash
   scripts/acervo_anki_remote.sh adopt-server
   ```

5. Wait for the reported full download and schema upload, then sync mobile.

## Reference: scheduling-preservation acceptance

1. On mobile, open an Acervo card, answer it once, optionally flag it, and sync.
2. Run `scripts/acervo_anki_remote.sh export-state`. Verify that card has a
   non-zero `reps` value and the expected flag.
3. Change the same note's sentence or comment in the manifest and run `push`.
   The robot output must say `updated`, not `created`, for that note.
4. Sync mobile again. Confirm the new content and image/audio appear, the card
   remains reviewed rather than new, and its flag is unchanged.
5. Run the identical `push` again and confirm it reports the notes unchanged and
   no new media.

The authoritative networking and client caveats are in the
[Anki self-hosted server manual](https://docs.ankiweb.net/sync-server.html),
[AnkiMobile preferences](https://docs.ankimobile.net/preferences.html), and
[AnkiDroid manual](https://docs.ankidroid.org/).

Upgrade the server and robot together before upgrading to a mobile client that
requires a newer sync protocol.

Before an Anki upgrade, rerun `scripts/test_anki_sync_docker.sh`. The automated
test uses real official server and client code, isolated temporary storage, and
tears down only its uniquely named Compose project.
