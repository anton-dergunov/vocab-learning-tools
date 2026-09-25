# Capture transports · getting a word in from wherever you met it

**Status:** research. Nothing here is built and nothing here is decided. Refreshed 25 Sep 2026 for
the capture routes that exist now: headless capture is `POST /captures`, and resolve can be called
alone as `POST /capture/resolve`. This document enumerates
every realistic way a word or a sentence can reach Acervo on each device, says what each costs and
what it buys, records the options that do not work and why, and ends in a recommendation and a set of
experiments that can be run today without writing any code.

It is scoped to **text**. Photo capture is built ([`photo-capture.md`](../features/photo-capture.md)) and is
not re-litigated here; this document touches it only where a transport happens to *deliver* an image,
which that document lists as not built.

The capture design itself is [`../features/capture.md`](../features/capture.md). One transport that
looks obvious — "iOS Shortcut → POST → open app", one gesture from the share sheet that *ends in the
review screen* — does not exist. See
[Three facts that decide everything](#three-facts-that-decide-everything).

## Where we are today

One production path: open Acervo, go to Add, type or paste the text, press Process, read the article
it proposes, save. Plus `scripts/ingest_vocabulary_file.py`, which walks a notes file into the Inbox
through `POST /captures` — the right tool for a backlog, useless for a word met in the wild.

The shape is settled ([`../features/capture.md`](../features/capture.md)), and nothing here disturbs it:
**one capture pipeline, and every capture path a thin client against it.** `POST /capture` returns a
draft to review and `POST /captures` files a submission straight into the Inbox as a job; between them
they accept everything any transport below would want to send: `text`, an optional `headword` hint,
`language`, `sourceUrl`/`sourceTitle`/`sourceKind`, `note` and `topics`. So this document is not about
the server. **Every option below is a question about the last hundred
metres — how a fragment of text gets from the app you met it in onto that one POST.**

The share-sheet and browser transports are the same single POST and **remain unbuilt**. The code
agrees — there is no `share_target` in the
generated manifest, no URL-parameter handling anywhere in `web/src`, no `CFBundleURLTypes`,
`NSServices` or share extension in `macos/`, and no credential a headless caller could hold that is
not the account password.

## What a share sheet actually is

Worth spelling out, because the whole document turns on it.

A share sheet is the operating system's "send this to another app" menu — the panel that appears when
you tap **Share** on iOS or Android, or **Share** in Safari, or right-click → Share on a Mac. You
already use it constantly: sharing a selection to Telegram, sharing a Chrome page, sharing a
screenshot.

Three things about it matter here.

**It is a registry, not a feature.** An app does not "support sharing"; it *registers* with the
operating system as able to receive certain kinds of content, and the OS then lists it. Nothing
appears in your share sheet that did not ask to be there. So "add Acervo to the share sheet" always
means "make something register on Acervo's behalf", and the whole question is what is allowed to do
that registering on each platform.

**What arrives is one item, not a rich payload.** The sending app decides what it puts in: usually a
string of plain text, or a URL, or a file. A selected sentence arrives as a string. A shared web page
arrives as a URL plus a title, with no text. A screenshot arrives as an image file. There is no
standard way for an app to say "here is the word *and* the sentence *and* the page it came from" —
This is the **selection dilemma**, and its answer stands: share the sentence, pick the word in the app.

**The split that decides this document:** on **Android**, a progressive web app can register itself
through its own manifest — a `share_target` entry — and nothing native is required. On **iOS and
iPadOS**, a web app cannot register at all. Only a real native app, or a shortcut built in Apple's
Shortcuts app, can appear there. This one asymmetry is why the Android and iOS halves of this
document look nothing alike.

## Three facts that decide everything

### 1. iOS cannot open the app from a share

The obvious iOS transport is a Shortcut that POSTs *and then opens a URL*, one gesture from the share
sheet that lands on the review screen. A Shortcut can indeed POST and then open a URL. The problem is where that URL opens.

**There is no deep link into an installed home-screen web app on iOS.** A URL handed to the system
opens in Safari, as a tab, even when it is inside the installed app's scope. Android does the
opposite — a URL in an installed PWA's scope opens the PWA — which is exactly the kind of asymmetry
that makes a plan written from the Android side look fine until it meets a phone.

It is worse than a cosmetic difference, because **an iOS home-screen web app keeps its cookies, Web
Storage and IndexedDB isolated from Safari**. The Safari tab that opens is, for our purposes, a
different installation of Acervo: not signed in, no replica, no sync cursor. The shortcut would land
you on a sign-in screen, and signing in there would build a *second* replica in Safari's storage that
the installed app never sees.

So the obvious iOS transport has to be replaced by something else, and the iOS section below is mostly
about what.

### 2. Capture is a write, so every transport needs the tailnet — and that splits them in two

`deploy/acervo/remote-helper.sh` publishes the server with `tailscale serve`, not Funnel. The server
is reachable from the tailnet and has no public URL. Meanwhile, capture is a *write*: two model calls
on the server, and the standing rule is that a write without the server must fail visibly and must
never be queued.

That splits every option into two families with genuinely different failure behaviour, and it is
worth weighing more heavily than it first appears:

- **Open-the-app-prefilled.** The share puts text into the Add box and stops. If there is no network,
  the text is still sitting there; press Process when there is. Nothing is lost, and the failure is
  in front of you.
- **Post-and-walk-away.** The share fires a request and you move on. If there is no network — a
  plane, a metro, a phone that dropped off the tailnet — the capture is simply gone, unless the app
  you shared from still has the text for you to find again.

The first family is more forgiving in exactly the situations where you most want to capture a word.

**A correction worth recording, because an earlier draft of this reasoning got it wrong:** this does
*not* rule out Telegram. Telegram delivers messages to a bot two ways. A **webhook** means Telegram
POSTs to *your* public HTTPS URL — impossible here, no public URL. **Long-polling** means your own
process calls Telegram's API outbound and waits, which works perfectly from behind a tailnet or a
NAT, needs no inbound anything, and is what info-triage is already doing with four bots on the same
machine. The always-on process a Telegram transport needs is therefore not a new cost; that shape is
already running. This materially upgrades the Telegram options below.

### 3. The measuring stick is the current flow, not zero

The existing Add dialogue is not the problem to be solved — it is the thing to beat. It is
transparent, correctable, and it works everywhere. Its real cost, honestly counted on a phone:

> switch to Acervo (1–2 taps) → Add (1) → tap the box (1) → paste (1–2, the iOS paste callout being
> its own tap) → Process (1). **Roughly five or six actions and one app switch**, before review
> begins.

Two failure modes, not one. The obvious one is the tap count. The less obvious one is **precision**:
typing a foreign word by hand invites a typo that then propagates into an article and a dictionary
lookup, and on a phone keyboard in a language you do not know, that is not a rare event.

**An option that costs more than the floor should not be built.** An option that costs the same but
is more precise still earns its place. Every entry below is scored against that bar, and the table
near the end collects the scores.

---

# The options

Each entry: what the gesture is, what actually arrives, what it costs, how it fails, verdict.

## Android phone and tablet

Android is the good news. A progressive web app can register in the share sheet with nothing but a
manifest entry, and Chrome mints a real Android package (a "WebAPK") from that manifest — which is
already how Acervo is installed there.

### A1 · Web Share Target, `GET` — share a sentence, land in Add with it

**The gesture.** Select a sentence in any app → Share → **Acervo**. Acervo opens on the Add view with
the sentence in the box, the source page's title and URL filled in beside it, and the cursor waiting.
You press Process and review exactly as you do now.

**How it works.** A `share_target` entry in the web app manifest with `method: "GET"`. Android hands
the share to the app as nothing more than a navigation to the app's start URL with a query string —
`?title=…&text=…&url=…`. There is no service worker involved, no new route, no server round trip. The
app reads its own launch URL and seeds the Add view.

**What arrives**, which is the part that decides how it must be written:

| The share | `title` | `text` | `url` |
|---|---|---|---|
| A selection in a reader or a browser | — | the sentence | — |
| Chrome's own "Share page" | the page title | — | the link |
| Most social and news apps | — | **the quote *and* the link, in one string** | — |
| Some apps | the title | the link again | the link |

The third row is the common one and the one that needs care: the URL has to be lifted off the end of
the text, or `/capture` spends two model calls looking for a word inside `https://…`. The second row
has no text at all, and the honest response is to open Add with the source fields filled and an empty
box — a page is not a word, and inventing one from the title would fabricate an attestation.

**Cost.** Small, but not zero, and almost all of it is one prerequisite shared with half this
document — see [The one thing nearly everything needs](#the-one-thing-nearly-everything-needs). The
manifest entry itself is six lines in `web/vite.config.ts`, plus an assertion in
`scripts/verify_pwa.py`. One constraint found in the code: the share target's `action` must be the
start URL with a query (`"."`), **not** a path like `/add`. `/add` is technically in scope, but
`InterfaceServer.resolve` in the macOS host 404s any path not on disk while `src/acervo/api/static.py`
falls through to `index.html` — the two hosts already disagree about non-file paths, and every URL in
this build is deliberately relative because of it.

**How it fails.** Gracefully, which is its quiet advantage: offline, the sentence is sitting in the
box waiting for you. The one operational surprise is that **a manifest change does not reach an
already-installed WebAPK immediately** — Chrome re-checks and re-mints on its own schedule, typically
within a day. Until then the entry is simply absent from the share sheet. Expect one confused hour
unless you uninstall and re-add from the home screen.

**Verdict: the strongest option in this document on cost-to-value, and the one to build first.** It
beats the floor by roughly three actions, keeps review exactly where it is, degrades well offline,
and needs no credential, no native code and no store account.

### A2 · Web Share Target, `POST` — share a screenshot

**The gesture.** Take a screenshot → Share → Acervo → the image opens in the photo-capture surface and
you tap the word.

This is listed as not built in [`photo-capture.md`](../features/photo-capture.md). Noted here so the map is
complete, and for one fact worth knowing in advance: a **file** share must be
`method: "POST"` with `enctype: "multipart/form-data"`, which means the service worker has to
intercept the POST, stash the file, and redirect the app to a URL that picks it up. That is real work,
and it is a different mechanism from A1 rather than a bigger version of it. Both MIME type *and* file
extension must be listed in the manifest, or the app appears in the share sheet and then fails to
receive the file.

**Verdict: correct, and now unblocked.** Photo capture exists, so a shared screenshot has a screen to
land on; what is left is the service-worker handling above, and it is Android only for a PWA.

### A3 · Manifest `shortcuts` — long-press the icon → "Add a word"

**The gesture.** Long-press Acervo on the home screen → **Add a word** → the app opens straight on
Add.

**Cost.** A `shortcuts` array in the manifest. Perhaps ten lines, and it rides on the same launch-URL
work as A1.

**Verdict: worth taking, and worth nothing on its own.** It removes one tap from the floor and does
nothing about precision. Free once A1 is built; not a reason to build anything.

### A4 · A Trusted Web Activity, for `ACTION_PROCESS_TEXT` — the best gesture on any mobile device

This is the one option in the document whose value is genuinely hard to judge from a description, and
the one with the largest cost. Read the trial in [Try it before building
it](#try-it-before-building-it) before forming a view — the gesture can be borrowed for free, today.

**The gesture.** Select a word — in any app, anywhere, in the ordinary text-selection toolbar that
already offers Cut / Copy / Paste / Share — and tap **Acervo**, which is sitting right there beside
them. No share sheet, no scrolling a grid of app icons, no second menu.

**Why it is not available to a PWA.** `ACTION_PROCESS_TEXT` is an Android intent filter declared by
an activity in an installed package. Chrome's WebAPK does not declare one and cannot be made to. The
only way to get one is to ship a real APK — which, for a web app, means a **Trusted Web Activity**: a
thin native wrapper that runs the same web build full-screen in Chrome's engine, structurally the same
idea as the `macos/` host. Built with Bubblewrap, it is mostly generated, and it carries
`share_target` unchanged, so A1 survives inside it.

**What it costs.**
- A Bubblewrap project in the repository, generating and signing an APK.
- A signing key to create, keep and not lose — regenerating it means uninstalling and reinstalling.
- `assetlinks.json` published on the Acervo host, proving the app and the origin belong together.
  Without it the TWA runs with a browser address bar visible.
- Sideloading it onto the phone, and doing that again for each update (no Play listing, and none
  wanted).
- It replaces the WebAPK rather than living beside it, so it becomes the Android install and
  inherits responsibility for everything the WebAPK does today.

**The judgement.** The cost is a day of work and a permanent maintenance obligation. The gesture is
plausibly the single largest capture improvement available anywhere in this document — it removes the
share sheet entirely, and it is the only option that starts from the *word* rather than from a blob
of text, which means it is also the most precise. Whether that trade is worth it is exactly the kind
of question that argument cannot settle and thirty seconds of trying can.

**Verdict: conditional. Run trial T1 first.** If tapping "Translate" in the selection toolbar feels
decisively better than sharing, build it. If it feels about the same, do not.

### A5 · `intent://` links and a custom URL scheme

**Rejected.** Both are ways of getting a URL to open the app, which Android already does for any URL
in the installed app's scope. Neither adds a share-sheet entry. Strictly worse than A1 in every
respect, with more moving parts.

---

## iPhone and iPad

The hard platform. A web app cannot register in the share sheet, and — per fact 1 — nothing outside
the app can open the installed app either. Everything below is a way around one or both of those.

### B1 · A Shortcut in the share sheet that posts, and leaves the word in the Inbox

The option most worth understanding properly, because it is the one that actually clears iOS's
obstacles rather than working around them.

**The gesture.** Select a sentence → Share → **Add to Acervo** (a shortcut you built by hand in
Apple's Shortcuts app, with "Show in Share Sheet" turned on) → a moment later a banner says
*añoranza — longing*. You carry on reading. Two taps, no app switch at all.

**What happens.** The shortcut does one `Get Contents of URL` action: a POST to
`https://acervo.example.com/api/acervo/v1/captures` with a bearer token and a JSON body carrying the
shared text. The server answers `202` with a `capture` job, which resolves what the text is about,
composes each word and saves it through the ordinary save — the same `merge_graph` every other writer
uses — with the record landing in the Inbox and its enrichment queued. The answer is the job, not the
word, so a banner saying *añoranza — longing* needs a second action that asks `GET /jobs/{id}` once the
job has finished and reads the word from its steps.

**Where the word goes.** Acervo's **Inbox** tab, which already exists for precisely this: entries
built by automation that a person has not yet read. Next time you open Acervo, the 📥 tab carries a
count; the word is a complete article, and you correct it, file it, or delete it. This is not a new
queue — it is the one the file-ingestion script has been feeding all along.

**The honest trade.** This is a *post-and-walk-away* transport, so per fact 2: if the phone is off the
tailnet, the capture is lost. And the model's choice of headword is not reviewed at the moment you
make it — if it picks the wrong word out of your sentence, you find out later. The rule that review is
non-negotiable is satisfied in the sense that review still happens before the word is yours; it is
not satisfied in the sense of happening *now*.

**What it needs.** No server changes to capture at all — `POST /captures` is exactly the headless
door, already used by the notes-file ingestion, so this is a sanctioned transport and not a
bypass. What it needs is a **credential**, which is the blocker
discussed in [The second thing several options need](#the-second-thing-several-options-need). Two
smaller frictions belong to this option specifically: the shortcut must hardcode `schemaVersion`, so a
schema bump silently breaks every shortcut in the field until you edit them by hand; and it must carry
a valid fifteen-character `deviceId` as a constant.

**Verdict: the strongest iOS option, conditional on the credential decision.** Two taps against the
floor's six, and it is the only iOS path that does not require an app switch.

### B2 · The same shortcut, but confirm before it writes

**The gesture.** Select → Share → Add to Acervo → a Shortcuts menu appears: *“añoranza — longing.
Add? / Pick another word / Cancel.”* → tap Add.

**Why it is interesting.** It is review at the moment of capture, on iOS, without opening the app —
which is something nothing else in this document achieves. Three taps instead of two, and the wrong
headword is caught immediately rather than in the Inbox a week later.

**What stands in the way.** A shortcut can hold a response in a variable and post it back, so the
Shortcuts side is straightforward. The server side is not: composing an article is two model calls,
and posting twice would generate the entry twice. **The split that avoids this now exists**: photo
capture made resolve callable alone as `POST /capture/resolve` — resolve, the vocabulary checks and
the duplicate check, on the fast `quick` chain — and `/capture` accepts that resolution back and
checks it again rather than trusting it. So B2 is resolve → confirm → capture with the resolution,
with no new server work; the headless half would still want a job-shaped equivalent, since `/capture`
itself does not save.

**Verdict: the right shape for iOS, and unblocked on the server side.** The natural successor to B1.

### B3 · A Paste button in Add

**The gesture.** Copy the text however you normally would → open Acervo → Add already shows a
**Paste** button → tap it → Process.

**Why it is worth listing separately from "the floor".** Because it *is* the floor, with the fiddliest
part removed. On a phone, positioning a caret in a textarea and summoning the paste callout is the
step that goes wrong; a button that reads the clipboard directly is one confident tap. Safari's
`navigator.clipboard.readText()` works inside a user gesture, showing its own native "Paste"
confirmation, which is fine — that confirmation *is* the tap.

**Cost.** Perhaps twenty lines, in `web/src/AddView.tsx` plus the matching rule in `styles.css` and
`design/ui-prototype/` (the prototype and the application change together). Two details decide whether
it works: the clipboard read must be the *first* statement in the handler with nothing awaited before
it, or Safari drops the user-gesture association and rejects; and the button should appear only when
the box is empty, which disposes of the "replace or append?" question entirely. Firefox has no
`readText` for pages at all, so the button simply is not rendered there — a missing button is not a
missing capability, since ⌘V still works.

**Verdict: take it regardless of everything else.** It is the cheapest item in the document, it helps
on every platform, and it is the only one that improves the fallback path that will always exist.

### B4 · A Shortcut that copies and opens

**The gesture.** Share → shortcut → it copies the text and opens Acervo → you tap Paste.

**Verdict: rejected, on the evidence of fact 1.** "Opens Acervo" opens *Safari*, not the installed app
— a different storage bucket, not signed in, no replica. It is worse than B3, which at least lands in
the real app. Recorded here so it is not proposed again.

### B5 · A native iOS app with a Share Extension

**The gesture.** The genuine article: Acervo in the iOS share sheet like any other app, with its own
small review sheet appearing over whatever you are reading, no app switch.

**Cost.** An Xcode project, an app target plus a share-extension target, a WKWebView host mirroring
what `macos/` does, and — the part that decides it — Apple's signing. A personal-device install with a
free Apple ID expires after seven days, so this means a paid developer account (about $99/year) to be
usable at all. *This figure should be confirmed against Apple's current terms before anyone commits to
it.*

**Verdict: the best iOS experience, at the highest cost in the document.** Not first. Worth
reconsidering only if B1 and B2 both disappoint in practice.

### B6 · A Safari Web Extension, on iPhone and iPad

Deferred to [Browsers other than Chrome](#browsers-other-than-chrome), because it is the same piece of
work as the desktop extension and should be costed once.

### B7 · The Action button, Back Tap, Control Centre, a Lock Screen widget

Not transports — **launchers**. Each of them can run a shortcut, so each is a faster trigger for B1 or
B2: squeeze the Action button and the selected text is captured, without the share sheet at all.

**Verdict: free polish, later.** Worth a line in whatever gets built, worth nothing on its own.

### B8 · Web Share Target on iOS

**Rejected, and not for want of trying.** WebKit has never implemented it;
[bug 194593](https://bugs.webkit.org/show_bug.cgi?id=194593) has been open since 2019. A `share_target`
in the manifest is simply ignored on iOS. Nothing about Acervo can change this, and it should not be
re-checked hopefully every six months — put a note on the bug instead.

---

## macOS

The desktop is the easy case and the least urgent one: there is a keyboard, copy-paste is reliable,
and switching to a menu-bar app is cheap. Everything here is a refinement rather than a rescue.

### C1 · The browser extension, retargeted

**The gesture.** Select a sentence on any page → ⌘⇧K → a small dialogue appears *in the page* → press
Enter.

**Why it ranks highest on quality.** An extension is the only
transport with no selection dilemma. It reads the DOM *around* your selection, so one gesture yields
the word, the sentence it sits in, the page URL and the page title — the two fields that make an
attestation memorable years later, and the two that every share-sheet transport throws away.

**What exists already.** The owner's `info-triage-capture-extension` — a separate repository — is this
exact pattern, working, with a Shadow-DOM dialogue, a bearer token, a route picker and an options
page. The
coupling to info-triage is narrow: an endpoint builder that hardcodes a `/capture` path and a
`host:port` shape, and a payload literal. Retargeting is a small change in two files — though it would
want to be Acervo's own copy rather than a fork that drifts.

**Two shapes to choose between**, and they are meaningfully different:
- **Post directly**, like the info-triage extension does — two keystrokes, lands in the Inbox, same
  trade as B1.
- **Hand off to the app**, opening Acervo prefilled — one more app switch, but review stays where it
  is and no credential is needed.

**Verdict: the highest-quality capture available on any platform, on the platform that needs help
least.** Strong, not urgent.

### C2 · A Services menu item and a global hotkey in the existing Mac app

**The gesture.** Select text anywhere on the Mac — any app, not just a browser — press a hotkey, and
Acervo opens with it.

**What it costs, which is less than it looks in one half and more in the other.** The delivery half is
effectively built: `web/src/App.tsx` already installs a `window.acervo` bridge and
`macos/Sources/AcervoApp.swift` already calls into it. A Services capture is one more method on a
bridge that exists — **no URL scheme, no `CFBundleURLTypes`, no share extension.** (Worth noting that
`acervo://` today is a `WKURLSchemeHandler` internal to the WebView, not a system-registered scheme,
and the app in fact loads from a loopback origin.)

The native half is where the work is. `NSServices` is an array of dictionaries and cannot be expressed
as an `INFOPLIST_KEY_*` build setting, so `macos/project.yml` has to give up
`GENERATE_INFOPLIST_FILE: YES` for a real plist — a small change that touches every other generated
key. For the hotkey, the app is already menu-bar resident and therefore always running to receive one;
Carbon's `RegisterEventHotKey` needs no permission, while `NSEvent.addGlobalMonitorForEvents` needs
Accessibility access and a trip through System Settings. Prefer the former. A newly installed Services
entry also does not appear until the Services cache refreshes — the macOS equivalent of the WebAPK
lag.

**Verdict: good value, low urgency.** It is the only macOS option that works outside a browser, which
is its real argument.

### C3 · A Quick Action in Shortcuts.app

Zero code: a Quick Action built in Apple's Shortcuts app appears in the Services menu immediately and
can POST anywhere. Same credential question as B1.

**Verdict: not a thing to build — a thing to *try*.** See trial T4. It is the fastest way to find out
whether C2 is worth building.

---

## Browsers other than Chrome

The extension in C1 is written for Chrome, and "Chrome only" deserves a real answer rather than a
shrug — especially since one of the answers reaches iOS.

- **Firefox** — it is an MV3 WebExtension, so this is close to free if it is ever wanted.
- **Safari, on macOS *and* iOS** — `xcrun safari-web-extension-converter` turns the same extension
  source into an Xcode project targeting both. This is the interesting one, because **a Safari Web
  Extension on iOS is the only way the DOM-reading advantage ever reaches a phone**: select a word in
  mobile Safari, and an extension can read the sentence around it, the URL and the title, which no
  share sheet on iOS can deliver. It also collapses two entries in this document (C1 on Safari, and
  B6) into one piece of work.

  The cost is Apple's rather than the code's. A local unsigned macOS build is fine. The iOS half runs
  into the same seven-day free-provisioning expiry as B5, so in practice it means a paid developer
  account — *again, confirm against Apple's current terms before committing.*

**Verdict: worth knowing, not worth doing yet.** If a paid Apple developer account is ever bought for
B5, this comes nearly free with it and is the better half of the purchase.

---

## Across all platforms

### D1 · Acervo's own Telegram bot

Underrated, and it deserves a second look — particularly for iOS, where every other option is
either blocked or expensive.

**The gesture.** Select anything, anywhere, on any device → Share → **Acervo** (the bot) → the bot
replies within seconds: *“añoranza — longing (noun). Add / Pick another word / Discard”* → tap Add.

**What makes it unusually strong here.**
- **It is the only transport that works identically on iPhone, iPad, Android and the Mac**, with no
  native code, no store account, no signing key and no per-platform work. One implementation reaches
  every share sheet at once, including the one platform that blocks everything else.
- **Inline buttons are review at the moment of capture** — the thing B2 needs a route split to
  achieve, Telegram gives for free, in a UI you already have open.
- It carries **screenshots as well as text**, on iOS, where Web Share Target does not exist. That is
  worth remembering when photo capture reaches step 5.
- The polling process it needs is not a new cost (fact 2): info-triage is already running four of
  them on the same machine.

**What it costs.** A bot token from BotFather. An always-on long-polling process — which must live
somewhere, and `acervo-worker` is deliberately *not* it (that is a one-shot container by design), so
this is a genuinely new always-on thing in the deployment even if the shape is familiar. And the
standing objection: it is a hop through a third party, so a capture can be stranded in Telegram, and
the text of your reading passes through their servers.

**Verdict: the best answer available for iOS if the credential question blocks B1, and a reasonable
answer even if it does not.** Worth a serious look before buying an Apple developer account.

### D2 · Routing through info-triage's `lang` route

The status quo option: share to the existing `lang` bot, and let something downstream move it into
Acervo.

The argument against it stands: info-triage is asynchronous **by necessity**,
because deciding where information belongs needs context you lack at capture time. Vocabulary's
decision is immediate. Routing an immediate thing through infrastructure built for deferral adds a hop
that buys nothing at the end of it — you still open Acervo to review, and now two systems can fail
between you and a word you wanted to keep. The user's own account of the experience confirms it: by
the time the queue is reached, the reason for capturing is forgotten.

Two facts about info-triage as a transport. info-triage has **no outbound push** — no webhook, no forwarding,
no per-route destination adapter; "routing to an external system" there means the item lands in a
directory and a separate downstream tool picks it up. So this option means *building* that push. And
its route names are a closed tuple validated at startup, so a dedicated Acervo route would mean
editing that tuple, the config and a fifth bot token.

**Verdict: rejected as a path, retained as a backstop.** It costs nothing to keep using it for a word
met where Acervo is not installed. It is not the plan, and D1 is strictly better at the same job.

### D3 · A queue of raw captured text, before it is a word

The idea of a holding pen: shares land as raw scraps, and you later open a list, correct the text, and
push each one into Add.

**Mostly already built, and should stay that way.** For *text*, the Inbox is this queue — an applied
capture is a complete article you can correct or delete, which is strictly more useful than a raw
fragment, and it costs a person nothing extra to review. A second queue holding unprocessed text would
be a parallel pipeline for no gain.

The one case that genuinely has no home is a **screenshot shared from iOS**, where there is no review
step possible at capture time and the result is a binary the app cannot turn into anything on its own.
That is a real gap — and it belongs to `photo-capture.md`, whose `photos/{owner}/pending/` staging
area is already the right shape for it, not to a new general-purpose queue.

**Verdict: do not build a scrap queue.** The Inbox is the queue; the screenshot case is photo
capture's to solve.

---

# The comparison

Actions counted on a phone, before review begins. The floor is the current flow: **six actions, one
app switch**.

| # | Transport | Platforms | Actions | Word *and* sentence? | Reviewed when captured? | Survives no network? | Cost | Verdict |
|---|---|---|---|---|---|---|---|---|
| A1 | Share target, GET | Android | **3** | sentence, word picked in app | yes | **yes** | small | **build first** |
| A3 | Manifest shortcuts | Android | 5 | n/a | yes | yes | tiny | take with A1 |
| A4 | TWA + text-selection action | Android | **2** | **both** | yes | **yes** | large | trial T1 first |
| A2 | Share target, POST (image) | Android | 3 | via OCR | yes | no | large | unblocked; photo capture is built |
| B1 | Shortcut → post → Inbox | iOS, iPadOS | **2** | sentence only | no, later | no | credential | strongest on iOS |
| B2 | Shortcut → confirm → post | iOS, iPadOS | 3 | sentence only | **yes** | no | resolve route (built) | successor to B1 |
| B3 | Paste button in Add | **all** | 4 | whatever you copied | yes | **yes** | tiny | **take regardless** |
| B5 | Native iOS share extension | iOS, iPadOS | 2 | sentence only | yes | no | very large | not now |
| C1 | Browser extension | desktop | **2** | **both, plus URL and title** | either | no | medium | best quality |
| C2 | Services + hotkey | macOS | 2 | selection only | yes | yes | medium | good, not urgent |
| B6 | Safari extension (iOS too) | macOS, iOS | 2 | **both** | either | no | large + Apple fee | with B5 or never |
| D1 | Telegram bot | **all** | **3** | sentence only | **yes**, inline buttons | no | medium | iOS fallback |
| D2 | info-triage `lang` | all | 2 + later | sentence only | no, much later | no | medium | rejected |
| B4 | Shortcut → clipboard → open | iOS | — | — | — | — | — | **impossible** |
| B8 | Share target on iOS | iOS | — | — | — | — | — | **impossible** |
| A5 | `intent://`, custom scheme | Android | — | — | — | — | — | worse than A1 |

---

# Try it before building it

Most of this can be *felt* today, with no code in this repository, and one trial decides the largest
cost in the document. Each names in advance what result kills the option — decide that first, then
run it.

### T1 · Borrow the Android text-selection gesture (decides A4)

You cannot fake `ACTION_PROCESS_TEXT` without an APK. You do not need to: **Google Translate and
Wikipedia already register one.** Select a word in any Android app and look at the selection toolbar —
"Translate" sitting beside Copy *is* the gesture a TWA would buy.

Do this for a week, on real words, in the apps you actually read in.

> **Kills A4 if:** it feels about the same as opening the share sheet, or the toolbar is crowded
> enough that the entry hides behind an overflow menu, or you find you were going to switch to the app
> anyway. **Justifies A4 if:** you catch yourself using it for words you would not have bothered to
> capture at all. That last one is the real signal — the value of a two-tap capture is the words you
> would otherwise have let go.

### T2 · Count the Android share sheet against the floor (sanity-checks A1)

Share a selection to Google Translate, or any app, and count the taps to the result. Then do the
current Acervo flow on the same word and count those.

> **Kills A1 if:** the share sheet takes so long to appear, or buries Acervo so deep in its grid, that
> it is not actually shorter. (Android does learn frequently-used targets, so this improves with use —
> which is itself worth knowing before judging.)

### T3 · Build a fake share target (proves the Android mechanism end to end)

A two-file static page — an HTML file and a manifest declaring `share_target` — that does nothing but
print the query string it was launched with. Serve it over HTTPS with `tailscale serve` on a path of
its own, install it from Chrome's "Add to home screen", and share to it from everything you read in:
Chrome, a news app, a reader, a messaging app.

This exercises the entire Android mechanism without touching Acervo, and it answers the question that
actually decides how A1 must be written: **what does each app really put in `text`, `title` and
`url`?** Keep the output — it is the test fixture set for the parser, if A1 gets built.

> **Kills A1 if:** the installed page never appears in the share sheet at all (which would mean
> something about the install or the host is wrong, and is worth finding out now rather than after the
> manifest change).

### T4 · Build the iOS shortcut by hand (decides B1 and B2)

Shortcuts needs no code and no credential to answer the ergonomic question. Make a shortcut with
"Show in Share Sheet" on, whose only action is to show the shared text in an alert. Share to it from
Safari, from a reader, from a screenshot, from a messaging app.

Two things to watch: how many taps it really takes to reach it in the share sheet, and — more
important — **what iOS actually hands over from each app**, which varies more than you would expect.
Then make a second version that POSTs to a public echo service, to feel the round-trip delay before
the banner appears.

> **Kills B1 if:** the shortcut is buried far enough down the share sheet that it is no faster than
> switching apps, or the apps you read in hand over something unusable.

### T5 · Build a macOS Quick Action (decides C2)

A Quick Action in Shortcuts.app appears in the Services menu immediately, with no Xcode and no plist.
Give it a hotkey. Select text in a few apps and trigger it.

> **Kills C2 if:** you do not reach for it — which on a desktop, where copy-paste already works well,
> is a real possibility worth discovering for free.

---

# What to do

Assuming the trials do not overturn anything:

1. **Take B3, the Paste button, now.** Tiny, helps every platform including the one that will always
   be the fallback, and depends on nothing.
2. **Run T1 and T4 this week.** They are free, they take minutes, and between them they decide the
   two largest questions in the document.
3. **Build A1**, the Android share target — with the launch-URL work below, which is most of its cost
   and unlocks nearly everything else. Take A3 with it.
4. **Then iOS, chosen by what T4 said**: B1 if the credential question can be answered cleanly, D1 —
   the Telegram bot — if it cannot, or if B1's silent failure offline proves annoying in practice.
5. **A4, the TWA, only if T1 justified it**, and knowing it is a permanent maintenance obligation.
6. **C1 and C2 whenever the desktop starts to annoy.** They are quality improvements to a flow that
   already works, not rescues.

Not now: B5 and B6 (Apple's fee, and B1/D1 should be tried first), D2 (rejected), D3 (the Inbox already is it).

## The one thing nearly everything needs

Every "open the app prefilled" option here — A1, A3, A4, the hand-off form of C1, C2 — depends on one
capability that does not exist: **the app cannot be launched with content.** There is no router and no
URL-parameter handling anywhere in `web/src`.

This is the real cost of A1, and the reason to build A1 first: it is the piece the others then get for
nothing. It means reading the launch URL once and seeding the Add view from it, reusing the existing
`CaptureSeed` path in `web/src/AddView.tsx` that the external-dictionary "Add to my words" button
already uses. Two things about that seed will need to change, and should be changed in place rather
than doubled: it is shaped for a dictionary entry today (it requires a `reference` and a `headword`, a
shared sentence has neither), and it auto-processes on mount, which is wrong for a share — nobody has
chosen a word yet, a share can arrive with no text at all, and it can land on an app that is not
signed in.

Designing that is a separate task. This document only insists that it is the common dependency and
that it be built once.

## The second thing several options need

B1, B2, C1-as-a-poster, D1 and any future cron-driven transport all need a **credential**, and today
the only one is the account password exchanged at `POST /session` for a 30-day token. Putting an
account password into the Shortcuts app — which syncs through iCloud — is the wrong answer.

The shape of a better one is visible but not decided: the existing tokens are already owner-scoped and
already revocable wholesale by rotating the account's token key, so what is missing is a *lifetime*
and a way to mint one deliberately, not a second auth system. What makes this a real decision rather
than a small feature is that AGENTS.md is explicit that batch work writes through **the owner's own
account, not a service account** — a long-lived token has to stay inside that rule rather than quietly
become the service account it forbids.

**This document raises it; it does not settle it.** Nothing above should be built on an assumption
about how it lands.

---

## Sources

Platform behaviour changes, so every claim above that is not about this repository is anchored:

- [`share_target` — MDN](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Manifest/Reference/share_target)
- [Receiving shared data with the Web Share Target API — Chrome for Developers](https://developer.chrome.com/docs/capabilities/web-apis/web-share-target)
- [Enable Web Share Target in a Trusted Web Activity — Chrome for Developers](https://developer.chrome.com/docs/android/trusted-web-activity/web-share-target)
- [How Chrome handles updates to the web app manifest — web.dev](https://web.dev/articles/manifest-updates)
- [WebKit bug 194593 — Add support for Web Share Target API](https://bugs.webkit.org/show_bug.cgi?id=194593) (open)
- [Complete guide to PWA deep links — Progressier](https://intercom.help/progressier/en/articles/6902113-complete-guide-to-pwa-deep-links) (on iOS not deep-linking into installed web apps)
- [Safari on iOS 14 for PWA developers — firt.dev](https://firt.dev/ios-14/) (on web-app storage isolation from Safari)
- [Async Clipboard API — WebKit](https://webkit.org/blog/10855/async-clipboard-api/) (on the paste callout and the user-gesture requirement)
- [Request your first API in Shortcuts — Apple Support](https://support.apple.com/guide/shortcuts/request-your-first-api-apd58d46713f/ios)
- [Custom text selection actions with ACTION_PROCESS_TEXT — Android Developers](https://medium.com/androiddevelopers/custom-text-selection-actions-with-action-process-text-191f792d2999)
- [Meet Safari Web Extensions on iOS — WWDC21](https://developer.apple.com/videos/play/wwdc2021/10104/)

## Also worth recording

- **A command-line client** would need no server work at all: `POST /capture`, `POST /articles`,
  `POST /captures`, `GET /jobs` and `GET /events` are the whole surface, and the job design deliberately
  made it complete.
- **The credential several options need has a shape to copy.** `src/acervo/tokens.py` already mints
  audienced, time-limited tokens (a loop render's), signed with the per-user key; a deliberate
  long-lived capture token would be the same shape with a different audience and lifetime.
