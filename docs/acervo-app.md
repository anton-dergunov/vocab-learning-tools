# Acervo application shell

Acervo now includes one shared web interface, an installable PWA, a native macOS host, and a
dedicated PocketBase instance. This first application release contains no accounts, vocabulary
records, dictionaries, or application collections.

PocketBase serves both the website and the future Acervo API from one listener. The default host
port is `27702`, deliberately separate from the Anki sync listener on `27701` and from any other
PocketBase deployment. Override it when either port is already assigned:

```bash
./deploy.sh --local --app-port 27802
./deploy.sh --target user@server.example.com --app-port 27802
```

The installer rejects using the same port for Acervo web/PocketBase and Anki. Before choosing an
override, check the server's existing container port assignments. The app listener binds to
`127.0.0.1` by default so it can sit behind an HTTPS reverse proxy; use `--app-bind-address` only
when the network design requires a different interface.

## Browser and PWA

Point an HTTPS reverse proxy at the configured Acervo app port, then open the public address, for
example `https://acervo.example.com`. PocketBase serves:

- `/` — the responsive Acervo interface and PWA;
- `/api/acervo/v1/health` — the deployed application version;
- `/api/acervo/v1/mac-release` — the current macOS release, when one is published;
- `/_/` — PocketBase administration.

HTTPS is required for service workers and PWA installation outside local development. Install the
site through the browser's normal **Add to Home Screen** or **Install App** command. The cached shell
opens offline. When a new build has downloaded, a dot appears on the gear; the new worker activates
only after **Update Acervo** is selected.

## macOS application

Build an ad-hoc-signed application and release archive with:

```bash
npm run build:mac
npm run package:mac
```

The application embeds the same `web/dist` interface used by the PWA. On first launch, its native
Settings window asks for the same HTTPS Acervo address. That value remains in local macOS
preferences and is never placed in source code, documentation, or release metadata.

The menu-bar icon remains available after the main window closes. Left-click opens Acervo;
right-click shows only **Quit Acervo**. A small dot indicates a native update. Native Settings can
check, download, verify, and install that update; automatic installation is off by default.

Running `deploy.sh` on macOS packages the PWA, PocketBase service, and matching native release with
one version/build identity. Deployments from a non-macOS host update the server and PWA but keep the
previously published native archive.

## Persistent layout

The application additions live beside the existing Anki data:

```text
data/pocketbase
downloads
```

Deployment preserves both directories, along with `data/anki-server`, `data/anki-robot`, inputs,
and backups. `downloads` is deliberately outside PocketBase's public web directory so a phone's
service worker never precaches the macOS archive.
