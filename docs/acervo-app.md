# Acervo application shell

Acervo now includes one shared web interface, an installable PWA, a native macOS host, and a
dedicated PocketBase instance. This first application release contains no accounts, vocabulary
records, dictionaries, or application collections.

PocketBase serves both the website and the future Acervo API from one listener. Acervo always
coexists with other applications on a shared host; it never assumes ownership of the host's
default HTTP/HTTPS endpoints or unrelated proxy configuration. The default backend port is
`27702`, deliberately separate from the Anki sync listener on `27701` and from other PocketBase
deployments. Override it when either port is already assigned:

```bash
./deploy.sh --local --app-port 27802
./deploy.sh --target user@server.example.com --app-port 27802
```

The installer rejects using the same port for Acervo web/PocketBase and Anki. Before choosing an
override, check the server's existing container port assignments. The app listener binds to
`127.0.0.1` by default so it can sit behind an HTTPS reverse proxy; use `--app-bind-address` only
when the network design requires a different interface.

`web/dist/` and `deploy/acervo/pocketbase/pb_public/` are generated, ignored staging directories.
The supported build and deployment commands repopulate them before packaging; their contents are
disposable and should not be committed.

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
only after **Update Acervo** is selected. Browser Settings also offers **Download Acervo for macOS**
when the server has a native release; a server packaged without one says that no release is
currently published.

## HTTPS with Tailscale Serve on Synology (recommended for a private tailnet)

Use Tailscale Serve when Acervo should be reachable only by devices in the same tailnet. Serve
terminates browser-trusted HTTPS on a dedicated Tailscale listener and proxies it to Acervo's
localhost HTTP backend. The default mapping is HTTPS `27702` to HTTP `127.0.0.1:27702`; using the
same number is safe because the listeners bind different addresses and speak different protocols.
Do not browse directly to the backend before the Serve mapping exists.

1. Keep the default backend bind address `127.0.0.1` and app port `27702`, or save host-specific
   choices in the ignored `.acervo-deploy` profile.
2. In the Tailscale admin console's **DNS** page, enable **MagicDNS** and **HTTPS Certificates** if
   needed. Enabling certificates publishes the generated machine and tailnet DNS names to the
   public certificate-transparency ledger, although access remains private to the tailnet.
3. Install the restricted Acervo launcher once. This is the only routine setup command that asks
   for the NAS account's sudo password:

   ```bash
   ./deploy.sh --install-helper
   ```

4. Add only Acervo's configured listener:

   ```bash
   ./deploy.sh --configure-https
   ```

   The command inspects every existing Serve listener first. It does nothing when the exact mapping
   exists, refuses to replace a port used by another service, and never resets the Serve
   configuration. To choose a different listener explicitly, use `--https-port PORT` and save it
   with `--remember-target`. Port 443 is accepted only when explicitly selected and currently free
   (or already mapped to this exact Acervo backend); it is never Acervo's default.
5. Verify the application and API through the dedicated HTTPS port:

   ```text
   https://server.example.com:27702/
   https://server.example.com:27702/api/acervo/v1/health
   ```

6. Enter the first address, without `/api/...`, in the Acervo macOS Settings window. The native
   updater derives its manifest and download addresses from that base URL.

Serve mappings configured in the background persist across Tailscale restarts. Inspect the complete
shared-host configuration before making changes:

```bash
sudo /var/packages/Tailscale/target/bin/tailscale serve status
```

Never use a global reset or an unqualified disable command on a shared host. If Acervo's listener
must be removed manually, target only its configured port with `tailscale serve --https=PORT off`.

Every phone, tablet, and computer opening this address must be connected to the tailnet and allowed
to reach the NAS by the tailnet access policy. Use **Serve**, not **Funnel**; Funnel would publish the
service to the public internet.

See Tailscale's current [Serve command reference](https://tailscale.com/docs/reference/tailscale-cli/serve),
[HTTPS setup](https://tailscale.com/docs/how-to/set-up-https-certificates), and
[Synology integration guide](https://tailscale.com/docs/integrations/synology).

## Alternative: HTTPS through the DSM 7 reverse proxy

Keep Acervo's container listener as HTTP on `127.0.0.1:27702` and let DSM terminate HTTPS. This
keeps the application port private and gives the browser, PWA, API, and native downloads one secure
origin.

1. Choose a DNS name such as `acervo.example.com` and make it resolve to the NAS through the network
   path you intend to use.
2. In **Control Panel > Security > Certificate**, add or import a certificate whose name matches
   that DNS name. Assign it to the new reverse-proxy service after the rule has been created.
3. In **Control Panel > Login Portal > Advanced > Reverse Proxy**, create a rule with:
   - Source protocol: `HTTPS`
   - Source hostname: `acervo.example.com`
   - Source port: `443` (or a different unused HTTPS port)
   - Destination protocol: `HTTP`
   - Destination hostname: `127.0.0.1`
   - Destination port: `27702`
4. In the rule's **Custom Header** tab, select **Create > WebSocket**. The current shell does not
   require a WebSocket, but this prepares the same origin for PocketBase realtime features later.
5. Open `https://acervo.example.com/` and check both `/api/acervo/v1/health` and
   `/api/acervo/v1/mac-release`. Enable HSTS only after the certificate and proxy rule work.

Do not publish port `27702` directly through the router or NAS firewall. Only the explicitly chosen
HTTPS reverse-proxy listener needs to be reachable. Certificates validate DNS names, so use the
certified hostname rather than an address when opening the application. As with Tailscale Serve,
create an Acervo-specific rule and leave every unrelated virtual host and listener unchanged.

The DSM locations and reverse-proxy fields are documented by Synology in its
[Reverse Proxy help](https://kb.synology.com/en-id/DSM/help/DSM/AdminCenter/system_login_portal_advanced?version=7)
and [Certificate help](https://kb.synology.com/en-us/DSM/help/DSM/AdminCenter/connection_certificate).

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
