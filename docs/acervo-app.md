# Acervo application shell

Acervo includes one shared web interface, an installable PWA, a native macOS host, and a dedicated
PocketBase instance. PocketBase stores the owner-scoped vocabulary graph; each client keeps a
complete IndexedDB replica. The current interface remains a shell while the vocabulary UI is built.

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
- `/api/acervo/v1/health` — the deployed application and schema version;
- `/api/acervo/v1/session` — password authentication for administrator-created Acervo accounts;
- `/api/acervo/v1/session/refresh` — authenticated token renewal;
- `/api/acervo/v1/mac-release` — the current macOS release, when one is published;
- `/_/` — PocketBase administration.

HTTPS is required for service workers and PWA installation outside local development. Install the
site through the browser's normal **Add to Home Screen** or **Install App** command. The cached shell
and IndexedDB replica open offline. When a new build has downloaded, a dot appears on the gear; the new worker activates
only after **Update Acervo** is selected. Browser Settings also offers **Download Acervo for macOS**
when the server has a native release; a server packaged without one says that no release is
currently published.

## HTTPS with a Tailscale service (recommended for a private tailnet)

Use Tailscale when Acervo should be reachable only by devices in the same tailnet. Serve terminates
browser-trusted HTTPS and proxies it to Acervo's localhost HTTP backend. Do not browse directly to
the backend before the mapping exists.

Give Acervo its **own service**, which means its own hostname and its own port 443, rather than a
port on the machine's shared hostname. This is not cosmetic. Android mints a WebAPK — a real
installed app — only for a site on the default port; on a non-standard port Chrome silently falls
back to a home-screen shortcut, and that fallback does not distinguish two apps that share a
hostname. Hosting Acervo and another self-hosted PWA as ports on one hostname therefore makes them
collide: installing one makes the other's page offer "Open <the first app>" instead of "Install
app", and only one of the two can be installed at a time. Separate hostnames fix it; separate paths
on one origin do not, and would additionally put both apps' browser storage in one bucket, where
uninstalling either offers to erase the other's data.

A service's 443 is bound on the service's own virtual IP, so it is not the host's 443 and cannot
collide with another application, another service, or an unrelated Serve mapping.

### Two server prerequisites

**Tailscale 1.86.0 or later.** Earlier clients have no `--service` flag at all and answer it with
their usage screen; `--configure-https` refuses with this requirement rather than letting that
happen. Check with `tailscale version`. Synology's Package Center channel lags far behind — it may
still offer 1.58 — so install the current package by hand from
[pkgs.tailscale.com](https://pkgs.tailscale.com/stable/#spks), choosing the `-dsm7` file matching
the architecture that `uname -m` reports (`x86_64`, `aarch64` → `armv8`, `armv7l` → `armv7`). Use
**Package Center > Manual Install** *over* the running package. Do not uninstall first: that drops
the node key, so the NAS leaves the tailnet and every existing Serve mapping goes with it. An
in-place upgrade keeps them. `tailscale set --auto-update` is not supported on Synology, so this
stays a manual step to repeat.

**A tag-based identity for the server.** Tailscale refuses a service host that is authenticated as
a person — `tailscale serve --service=…` answers `service hosts must be tagged nodes`. Tagging
*replaces* the device's user authentication: the Tailscale IP stays the same and a new node key is
issued, but the machine stops belonging to the account that logged it in. On a shared host this
affects everything else that machine serves, so grant the tag access before applying it:

1. Declare who may own the tag. A tag cannot be created from any form: the visual policy editor
   writes access rules only, so this has to go in the policy file itself. In the admin console
   sidebar expand **Access controls** and open the **JSON editor**, then merge a `tagOwners`
   section into the existing document rather than replacing it:

   ```json
   "tagOwners": {
     "tag:service-host": ["autogroup:admin"]
   }
   ```

2. Make sure a rule still admits the machine under its new identity. A tailnet left with the
   default "all users and devices, all ports" rule already covers tagged devices and needs nothing
   here. Where that rule has been narrowed, add this *before* tagging, or every application on the
   host becomes unreachable at once:

   ```json
   {
     "src": ["autogroup:member"],
     "dst": ["tag:service-host"],
     "ip": ["*"]
   }
   ```

3. On the **Machines** page, open the server's `⋯` menu, choose **Edit ACL tags**, add
   `tag:service-host`, and save. The tag must already exist in the policy file, and this needs
   Owner, Admin, or Network admin. Confirm the machine's other addresses still answer afterwards.

Then:

1. Keep the default backend bind address `127.0.0.1` and app port `27702`, or save host-specific
   choices in the ignored `.acervo-deploy` profile.
2. In the Tailscale admin console's **DNS** page, enable **MagicDNS** and **HTTPS Certificates** if
   needed. Enabling certificates publishes the generated machine and tailnet DNS names to the
   public certificate-transparency ledger, although access remains private to the tailnet.
3. On the admin console's **Services** page, **Advertised** tab, choose **Define a Service**:

   - **Service name**: `acervo` — the bare name, with no `svc:` prefix. The field accepts only
     letters, digits and dashes, and its contents become the hostname, so naming it `svc-acervo`
     would publish `svc-acervo.<tailnet-name>.ts.net` and have to be referenced as
     `svc:svc-acervo`. The `svc:` prefix belongs only in the policy file and the CLI.
   - **Ports**: `443`, in the field already prefixed with `tcp:`. Not `433`.
   - **Description** and **Service tags** are optional

4. Grant access to the service. Without a grant the name resolves but nothing connects. On the
   **Access Controls** page choose **Add rule** and set:

   - **Source**: `autogroup:member`
   - **Destination**: `svc:acervo` — here the `svc:` prefix is correct, and the console adds it to
     the bare name from the previous step
   - **Port and protocol**: `443` only. Remove **All ports and protocols** if the form offers it;
     leaving it in grants every port on the service, which the app does not need.

   The form's JSON preview is the rule it will save, and the policy file can be edited directly
   instead if you prefer:

   ```json
   {
     "src": ["autogroup:member"],
     "dst": ["svc:acervo"],
     "ip": ["443"]
   }
   ```

5. Install the restricted Acervo launcher once. This is the only routine setup command that asks
   for the NAS account's sudo password, and it is also how the launcher is refreshed after its
   protocol changes:

   ```bash
   ./deploy.sh --install-helper
   ```

6. Add only Acervo's own service listener, and remember the choice:

   ```bash
   ./deploy.sh --service acervo --configure-https --remember-target
   ```

   The command touches nothing but `svc:acervo` and never resets the Serve configuration. It
   reports that nothing changed when the mapping already exists. Unless an auto-approval policy
   covers the host, approve it once from the **Services** page; the service then reads
   **Connected**.

7. Verify the application and API on the service's own hostname, with no port:

   ```text
   https://acervo.<tailnet-name>.ts.net/
   https://acervo.<tailnet-name>.ts.net/api/acervo/v1/health
   ```

8. Enter the first address, without `/api/...`, in the Acervo macOS Settings window. The native
   updater derives its manifest and download addresses from that base URL.

Inspect what the host is serving, including every other service, with:

```bash
sudo /var/packages/Tailscale/target/bin/tailscale serve status
```

### Alternative: a port on the machine's own hostname

Where Tailscale Services is unavailable, Acervo can still take a dedicated port on the machine's
hostname. Use `--https-port PORT` instead of `--service NAME`; the default mapping is HTTPS `27702`
to HTTP `127.0.0.1:27702`, and using the same number is safe because the listeners bind different
addresses and speak different protocols. The command inspects every existing Serve listener first,
does nothing when the exact mapping exists, and refuses to replace a port used by another service.
Port 443 is accepted only when explicitly selected and currently free (or already mapped to this
exact Acervo backend); it is never Acervo's default. A configured `--service` takes precedence, and
the remembered HTTPS port is then left unused rather than mapped as well.

Expect the Android installation limitation described above when two PWAs on this machine are
separated only by port.

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

### Rebuilding the vocabulary database

PocketBase records applied migrations by filename, and a schema change here is a rewrite of the one
bootstrap migration — so an existing `data/pocketbase` never picks the rewrite up, and every graph
route fails against a database that predates it. `./deploy.sh --reset-pocketbase` replaces that
directory as part of the deployment, keeping a copy under `backups/`. It requires typing
`RESET ACERVO VOCABULARY`, discards every account and word on the server, and leaves Anki data
alone — `--reset-data` is the separate flag for that, and review history is not something a schema
rebuild should take with it. Accounts must be recreated and the seeder re-run afterwards; device
replicas are untouched, and each will notice the new dataset identity and stop rather than
overwrite itself.
