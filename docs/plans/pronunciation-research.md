# Pronunciation: what is actually possible

**Status:** Research. No code, no decisions locked. This replaces the assumptions in
[`pronunciation-and-audio.md`](pronunciation-and-audio.md) rather than building on them — that
document was written from the provider roadmap and assumed Gemini's ten-requests-a-day free tier was
the free path and that audio, being media, would not be replicated. Both assumptions turn out to be
wrong, and each of them was load-bearing.

## The question

Given a word, a phrase, a sentence or a short passage that is **already in the graph**, play it
aloud. Clearly, in the right language, at an absolute minimum for headwords and phrases. It must
work on a plane and in the Underground, it must work well online, the NAS has CPU and no GPU and
unlimited patience, and the expected volume is **30–100 pronunciations a day**.

Nothing here is dynamic text the owner typed into a box. Every utterance is a field of a record that
was written while online, which turns out to be the single most useful fact in the whole problem.

---

## Seven findings, in the order they change the design

### 1 · Cost is not a constraint, and designing around it would be designing around nothing

The whole corpus at its ten-thousand-lexeme ceiling is **1.9 M characters / 31 hours of audio**
(10,000 headwords at ~9 characters and 0.8 s, plus ~30,000 example and attestation sentences at ~60
characters and 3.5 s). Rendering *all of it, once*:

| Provider | Metered by | Headwords | Sentences | Free allowance |
|---|---|---|---|---|
| Google Cloud TTS Standard | characters, $4/1M | $0.36 | $7.20 | **4 M chars/month** |
| Google Cloud TTS WaveNet | characters, $4/1M | $0.36 | $7.20 | **1 M chars/month** |
| Cloudflare Aura‑1 | neurons ≈ $15/1M chars | $1.35 | $27.00 | 10 k neurons/day ≈ **7.3 k chars/day** |
| Azure Neural | characters, $16/1M | $1.44 | $28.80 | 500 k chars/month |
| Google Chirp 3: HD | characters, $30/1M | $2.70 | $54.00 | 1 M chars/month |
| Gemini 3.5 Flash TTS | audio tokens, $6/1M | $1.20 | $15.75 | — (Vertex, paid) |
| Gemini 3.1 Flash TTS | audio tokens, $20/1M | $4.00 | $52.50 | free tier: **10 requests/day** |
| OpenAI gpt‑4o‑mini‑tts | audio tokens ≈ $0.015/min | $2.00 | $26.25 | — |

Steady state is smaller still: 100 headwords a day is **900 characters a day, 27 k a month** — inside
every character-metered free tier by two orders of magnitude, and $1.20/month on paid Vertex Gemini
TTS if nothing free is reachable. Even the 100,000-lexeme fantasy is $76 of Google Standard, spread
over five months of free allowance.

So: **stop optimising cost.** The real constraints are offline availability, latency, and whether
the voice is *right for the language* — which is a content question, not a billing one.

### 2 · Audio is thirty times cheaper to store than images, which means it should be replicated

At Opus 24 kbps mono (3 KB/s), a headword clip is **2.4 KB** and a sentence clip **10.5 KB**.

| | Count | On disk |
|---|---|---|
| Text replica (`§02`) | 10,000 lexemes | 20–50 MB |
| **Headword audio** | 10,000 | **23 MB** |
| **Sentence audio** | ~30,000 | **308 MB** |
| Sense images | ~30,000 | ~9 GB |

Headword audio costs about as much as *the text it belongs to*. The design document's rule — "images
and audio are not replicated… the text of your vocabulary works on a plane; the illustrations do not,
and shouldn't pretend to" — was written with 300 KB pictures in mind and is simply the wrong call for
a 2.4 KB clip. **Audio belongs in the replica. Images still do not.** Sentence audio at 308 MB is
affordable but is a separate, later decision; headwords alone settle the minimum requirement.

WebKit's current storage policy supports this: a home-screen web app gets the same quota as the
browser, **up to 60% of disk** per origin, with LRU eviction by origin and an exemption for
persistent-mode storage (`navigator.storage.persist()`). The "50 MB Cache API cap on iOS" that
circulates is pre-Safari-17 folklore — but it is still right to keep clips as Blobs in **their own
IndexedDB database**, the `dictionaryStore.ts` pattern, so neither wipe touches the other and
per-record overhead cannot undo the compression.

### 3 · A device's own voice cannot be captured, and cannot be trusted to know the language

The Web Speech API gives no audio stream. `speechSynthesis` output cannot be piped into
`MediaRecorder` — on most platforms the synthesis happens outside the tab's audio graph entirely, and
every published workaround routes through `getDisplayMedia`, which is not a thing a PWA can do on a
phone. **A device voice can play but can never fill a cache.** That alone disqualifies it as a tier
in the chain and confines it to a live last resort.

Worse, for a pronunciation *reference* it is pedagogically unsafe. Reports conflict on whether
`getVoices()` returns a usable list on iOS — one widely cited survey says Safari returns nothing and
a system default is chosen for you; another says Safari populates the list synchronously on first
read; Apple's own forums carry an iOS 26 regression where user-selected voices are ignored. What is
not in dispute: iOS has shipped releases with **no quality voice installed for a given language**,
premium voices are 100 MB+ manual downloads, Siri voices are locked away from the API entirely, and
`speak()` is dropped silently unless it is inside a user-gesture handler. If no Spanish voice is
present, the platform will read Spanish with an English voice and teach the wrong thing, and the
application may not be able to detect that it happened.

Other platform facts worth having: Chrome cancels utterances after roughly 15 seconds (irrelevant for
words, relevant for passages); iOS stops synthesising when the browser is backgrounded and sometimes
needs a reload to recover; `voice.localService` is the only signal distinguishing an offline voice
from a network one, where enumeration works at all.

**Verdict:** free, zero-storage, zero-latency, available on every target, and the only thing that
works when the replica has no clip — but it is a fallback that must be *labelled* in the interface,
never the system of record.

### 4 · Because writes are online-only, nothing needs to synthesise on the device

This is the finding that removes a whole category of work. Every utterance in the graph arrived
through a write, and writes are online by invariant. So the moment a word exists, the server can mint
its audio — and the clip travels to the device in the same cursor pull as the record. There is no
"word in the replica with no audio that the device must voice for itself", except in the narrow
window between a save and a backfill sweep, which the device-voice fallback covers.

That kills the strongest argument for on-device neural TTS. For the record, it *would* work:

- **Piper in the browser** (`piper-tts-web` and similar, ONNX Runtime Web + `piper-phonemize`
  compiled to WASM) runs a ~60 MB medium voice per language, caches it in OPFS/IndexedDB, and — the
  important part — **phonemises offline for every language it supports** (~30, including the European
  set and Spanish). WebGPU is now available everywhere including iOS 26, so this is no longer
  Chrome-only.
- **Kokoro in the browser** (`kokoro-js`, 92 MB q8 / 326 MB fp32, 54 voices) sounds better and is
  **English-only offline** — non-English phonemisation requires calling out to a service, which
  defeats the entire purpose. For a multi-language vocabulary this rules it out on the device.

Neither is worth 60–180 MB per language and a second synthesis pipeline to close a window that is
already closed.

### 5 · Batching utterances into one call saves nothing, and you can stop doing it

Every provider that matters here meters **characters** (Google, Azure, Cloudflare, Deepgram) or
**audio duration** (Gemini, OpenAI). Neither is reduced by concatenating ten words into one request.
Batching reduces only the **request count**, which matters for exactly one row in the catalogue:
Gemini's free tier at 10 requests/day. And the cost of it is real — splitting a batched render back
into per-word clips needs silence detection or forced alignment, and both are approximate.

The correct response to a request-metered free tier is not to batch, it is to **use a
character-metered provider**, of which there are four with permanent free allowances large enough to
cover the entire corpus. (This also answers the open question from the sibling prototype: its
batching is almost certainly not saving money.)

### 6 · The free tier that matters is Google **Cloud TTS**, not the Gemini free tier

The catalogue currently knows one free Google speech path — `gemini-3.1-flash-tts-preview` on the
free tier, **10 requests a day**, which cannot serve 30–100. The Cloud Text-to-Speech API is a
different product with a different meter: **1 M characters/month free on WaveNet at $4/1M, 4 M/month
free on Standard**, 50+ languages, and it is reachable with the **Vertex credential that already
exists** (same GCP project, a different API to enable). That is a permanent free allowance ~37× the
steady-state need, in more languages than anything else on the list.

It would be a new catalogue row with a hand-written adapter, like `cloudflare.py` — LiteLLM's speech
bridge covers OpenAI-shaped `/audio/speech` and Gemini, not Cloud TTS's own API.

Two more corrections to the current rows: **Cloudflare's Aura‑2 exists only as `-en` and `-es`**, so
Cloudflare covers precisely today's two languages and nothing beyond them; and Aura‑1's free
allowance works out to 7.3 k characters/day, which is generous for headwords and thin for sentences.

### 7 · Two kinds of clip, and the split is not "expressive vs plain"

The existing plan splits on delivery — expressive sentences, plain words. The more useful split is
what the clip *is for*:

- **A reference pronunciation of a headword or lemma.** One per lexeme, 2.4 KB, must be offline, must
  be *correct*, and wants one known-good voice per language held stable so that the owner learns the
  voice and hears deviations. This is the minimum requirement and the 95% path.
- **A reading of a sentence.** An example or an attestation, where prosody carries meaning and a
  frontier model earns its premium. Bigger in aggregate, fetched and cached opportunistically, and a
  missing one is simply absent rather than a failure.

Two chains, as the plan says — but the reason is reference-fidelity versus listening material, not
plainness versus expression. One practical hazard for the first kind: **TTS reads isolated words
badly**. Stress pairs (English *record*), tone sandhi, and Gemini's documented habit of answering a
short word with generated text instead of audio are all the same failure. The standard mitigation is a
carrier phrase that is synthesised and then trimmed, or a style instruction on a row that supports
one. This is a prototype question, not a settled one.

---

## The options, judged

| Route | Offline | Capturable | Languages | Quality for a reference | Cost | Verdict |
|---|---|---|---|---|---|---|
| **Device OS voice** (Web Speech API) | yes | **no** | whatever the device has, unverifiable | unknown and unstable; may read the wrong language | free | **Labelled last-resort fallback** |
| **Piper in the PWA** (WASM) | yes | yes | ~30, phonemised offline | good-not-native, uneven per language | free | Not needed — see finding 4 |
| **Kokoro in the PWA** | English only | yes | 1 offline | very good | free | **Rejected** — offline only in English |
| **Piper on the NAS** (CPU, Docker) | n/a | yes | ~30, 100+ voices | good-not-native | free | Optional bulk/fallback renderer |
| **Kokoro on the NAS** (CPU) | n/a | yes | 8 | excellent for 82 M params | free | Viable; ~1.3 core-hours per audio hour, fine for a patient sweep |
| **Google Cloud TTS** | n/a | yes | 50+ | very good (WaveNet/Chirp 3) | free at this volume | **Recommended for headwords** |
| **Vertex Gemini TTS** | n/a | yes | many, style instructions | best tried so far | ~$1.20/month | **Recommended for sentences** |
| **Cloudflare Aura** | n/a | yes | **en, es only** | good | free | Second in the headword chain |
| **Human recordings** (Lingua Libre / Commons / Wiktionary) | n/a | already files | 150–310 languages, **patchy per word** | native speaker — the gold standard | free, CC‑BY‑SA | Stage 2 source tier above TTS |
| **Forvo API** | n/a | already files | 430+ languages, 6 M pronunciations | native speaker | $2/month non-profit, 500 req/day, no commercial use, attribution required | Worth a look; check storage terms |

On the NAS specifically: it is x86‑64 with AVX2 and usually idle, so Piper at roughly 10× real time
per core on a desktop CPU and Kokoro at roughly real time are both comfortable for an overnight
sweep. The published Piper benchmark showing 2.6 GB peak memory is a Python/ONNX harness artefact
rather than the model, but it is worth measuring before trusting a 20 GB shared machine with it. The
honest argument for running anything locally is not cost — it is independence from free tiers that
expire (the Vertex trial will) and unlimited re-renders when a voice choice changes.

---

## The shape this suggests

**Audio is a record, not a call.** Pre-rendered, content-addressed, in the media store, replicated
like text — justified purely by finding 2, and true for no other media.

**The chain for a headword clip, in order:**

1. **The replica.** Instant, offline, the 95% path.
2. **The server's media store.** Fetch and cache, exactly as a sense image is fetched.
3. **Synthesise now** (online only): Cloud TTS → Cloudflare Aura → Vertex Gemini TTS. Store the
   result; it never has to be paid for twice.
4. **The device's own voice**, live, labelled as such in the interface. Nothing is stored.

**The chain for a sentence clip:** Vertex Gemini TTS (with a style instruction) → Gemini free tier →
Chirp 3: HD → *nothing*. A missing sentence clip is an absence, not an error.

**Backfill is a sweep**, a subcommand of the one worker, shaped like the image and clip sweeps: ask
the graph what has no audio, render, write, be idempotent. Running it late, twice or never costs
latency and nothing else.

**The per-language voice registry is the piece no layer currently has.** "Which voice is correct
Spanish, and is it es‑MX or es‑ES" is a content decision like a prompt, not a provider capability —
it belongs in tracked configuration keyed by vocabulary language, with the voice id recorded on every
clip so a later change is detectable rather than silent.

**Format:** Opus mono 24 kbps in WebM. Playable on every target including iOS since 18.4; roughly
half the bytes of AAC at equal clarity for speech. Name the file by a hash of (text, language,
provider, model, voice) so the same sentence under two lexemes shares one file and a voice change
does not orphan anything.

---

## What is genuinely unknown, and the prototype that settles it

Everything above is desk research. Four questions can only be answered on the actual devices, and
a single static HTML page run on the iPhone, the iPad, the Android phone and the Mac answers all
four:

1. **What does `speechSynthesis` actually offer on each of my devices?** Enumerate `getVoices()`,
   print each voice's `lang` and `localService`, and try Spanish and English with the network off.
   This is the one contested fact in the whole report and it decides how much weight the fallback can
   carry.
2. **Is a hosted plain voice clearly better than the device voice, for a single word?** Blind A/B on
   twenty real headwords — if the device voice is good enough, the chain gets simpler.
3. **Do isolated words come back with the right stress**, and does a carrier phrase fix it?
4. **Latency**, measured rather than assumed: device voice vs a cached clip vs a cold synthesis.

## Open questions for the owner

- **Sentence audio in the replica: yes or no?** 308 MB at the ceiling. Headwords-only is 23 MB and
  settles the stated minimum.
- **One voice per language held stable, or variety?** Stability helps a reference; the report assumes it.
- **Is human-recorded audio (Lingua Libre / Forvo) interesting enough to design a source tier for
  now**, or is it Stage 2 behind TTS?
- **Is a local renderer wanted at all**, given finding 1 — or only as insurance against the Vertex
  trial expiring?
