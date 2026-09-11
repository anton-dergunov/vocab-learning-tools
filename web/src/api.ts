import type { PartOfSpeech, VocabularyGraph } from "./domain";
import { normalizeServerURL, sessionStore, type StoredSession } from "./session";
import type { ArticleDraft } from "./yaml";

type Envelope<T> = { data?: T; error?: { code?: string; message?: string } };
type LoginResponse = { token: string; user: { id: string; email: string } };

/** Shared with the server hook. A mismatch stops synchronisation until the app is updated. */
export const SCHEMA_VERSION = 8;

interface SyncEnvelope {
  schemaVersion: number;
  datasetId: string;
  cursor: number;
  serverTime: string;
}

/**
 * What this server can build entries with.
 *
 * `reason` names an environment variable and never a value, so it is safe to show. It exists so the
 * Capture control can be off *with a reason* rather than live and failing at the moment it is used.
 */
export interface CaptureHealth {
  available: boolean;
  /* The provider that would be asked first, and its model. Null when nothing can be asked: with a
     chain of providers, "unavailable" means no row has its credentials, so there is no model to
     name. `reason` names the first missing environment variable and is the actionable part. */
  provider: string | null;
  model: string | null;
  reason: string | null;
}

/* ── which model builds an entry ──────────────────────────────────────────
   Server state read through a route, not vocabulary: it is owner-scoped, never replicated, and it
   decides what the words are *made of*. It deliberately does not go through `AcervoRepository`,
   which owns the replica and nothing else — the external-dictionary list arrives the same way. */

/** One provider the server knows about, and whether this deployment can actually use it. */
export interface ModelProvider {
  id: string;
  label: string;
  kinds: string[];
  /** The models it offers, per kind. A chain entry is one of these, not a whole provider. */
  models: Record<string, string[]>;
  available: boolean;
  /** Names an environment variable and never a value, so it is safe to show. */
  reason: string | null;
  /** Where the owner reads their own usage. No provider serves that figure over an API. */
  usageUrl: string | null;
  /**
   * Whose credentials this provider spends, where the credential names one. Null for a provider
   * whose key is just a key, and for a Google login that does not record the account.
   */
  account?: string | null;
  /**
   * Which credential this provider would use, named and abbreviated. `hint` is four characters at
   * each end of the key and never more — enough to tell two keys apart, never enough to use one —
   * and is null for a credential that is a file, which is identified by its `account` instead.
   */
  credential?: ProviderCredential;
  /** The provider's non-secret deployment facts: a project, an account id, a local URL. */
  settings?: { name: string; value: string }[];
  notes: string | null;
}

/* Sense images. Owner-scoped server state and a picture the server draws, so like the provider
   types above these do not go through `AcervoRepository` — but the *rows* they return are ordinary
   `imagePrompts`, and they reach the replica the way everything else does, on the next sync pull. */

/** One image prompt as the image routes answer, which is the stored row plus one derived field. */
export interface ImagePromptRow {
  id: string;
  lexemeId: string;
  senseId: string | null;
  exampleId: string | null;
  prompt: string;
  styleId: string;
  seed: number;
  modelId: string;
  promptVersion: string;
  imageRef: string | null;
  imageModelId: string | null;
  attempts: number;
  failureReason: string | null;
  suppressed: boolean;
  /**
   * The whole prompt the image model is sent — brief, style and frame. Composed on the server and
   * deliberately never stored: the brief, the style id and the version reproduce it exactly, and
   * storing it too would hold the same text twice. Null where there is no brief to compose from.
   */
  composedPrompt: string | null;
}

export interface ImageStyle {
  id: string;
  label: string;
  /** A style with no colour to spend, which the writer avoids where the meaning needs colour. */
  mono: boolean;
}

export interface ImageSettings {
  /** Whether the unattended sweep may spend money while nobody is watching. */
  drawEnabled: boolean;
  /** The styles switched **off**, never the ones switched on — so a new style arrives on. */
  stylesOff: string[];
  boostVariety: boolean;
  /** False means nothing has been chosen and the deployment default is in force. */
  chosen: boolean;
  maxAttempts: number;
  styles: ImageStyle[];
  /** Whether this server is credentialed to draw at all, so a screen can say so plainly. */
  available: boolean;
}

export interface ProviderCredential {
  kind: "key" | "file" | "none";
  variable: string | null;
  present: boolean;
  hint: string | null;
}

export interface ModelPair {
  provider: string;
  model: string;
}

export interface ModelChain {
  /** `deployment` means nothing has been chosen and the server's own order is in force. */
  source: "owner" | "deployment";
  /** Why nothing in this chain can be asked, or null. Same producer as the health readout. */
  reason: string | null;
  /** What is *stored*, not what will be walked: an unavailable pair keeps its place. */
  pairs: ModelPair[];
}

export interface ModelCatalogue {
  providers: ModelProvider[];
  chains: Record<string, ModelChain>;
}

export interface ServerHealth {
  name: string;
  version: string;
  build: string;
  schemaVersion: number;
  capture: CaptureHealth;
}

export type PullResponse = SyncEnvelope & { changes: VocabularyGraph };
export type PushResponse = SyncEnvelope & { records: Partial<VocabularyGraph> };
export type ResetResponse = SyncEnvelope & { deleted: number };

const API_PATH = "/api/acervo/v1";
// The corpus's own `/api/v1` surface, allow-listed behind Acervo's auth. The packaged typed client
// is pointed here, so this is a *base URL* rather than a route.
const SPEECH_PATH = "/speech";
/** Compiled dictionaries are served as plain files, outside the JSON API and outside `pb_public`. */
const DICTIONARY_PATH = "/api/acervo/dictionaries";
const MEDIA_PATH = "/api/acervo/media";
const REQUEST_TIMEOUT = 15_000;
/** Capture is two model calls deep, so the sync timeout would abort a request that is working. */
const CAPTURE_TIMEOUT = 300_000;
// Model calls, so nowhere near the 15 seconds an ordinary read gets. A brief is one text call over
// a chain that waits out a rate limit; an image is 30-60 seconds and providers meter roughly one a
// minute, so a pause on the way is normal rather than a fault.
const BRIEF_TIMEOUT = 180_000;
const RENDER_TIMEOUT = 300_000;

/* ── capture ────────────────────────────────────────────────────────────
   The ingest endpoint of design §05. What comes back is a *proposal*: a draft the interface renders
   for review and then saves through the repository like any other article. Nothing here writes. */

export interface CaptureSentence {
  text: string;
  translation: string | null;
}

export interface CaptureResolution {
  language: string;
  headword: string;
  lemma: string;
  pos: PartOfSpeech;
  sentences: CaptureSentence[];
  note: string | null;
  /** How many leading lines of the submitted text the entry covered. Only meaningful in a stream. */
  consumedLines: number;
  consumedText: string | null;
}

/** An entry this word already has. Merging into it is §06's job; here it is a signpost. */
export interface CaptureDuplicate {
  id: string;
  headword: string;
  shortGloss: string | null;
}

/** A provider that was asked before the one that answered, and why it was passed over. */
export interface CapturePassedOver {
  provider: string;
  model: string;
  /** One of the retryable reasons: `rate_limited`, `unavailable`, `unreachable`. */
  reason: string;
}

export interface CaptureResult {
  resolution: CaptureResolution;
  duplicates: CaptureDuplicate[];
  draft: ArticleDraft | null;
  applied: { lexemeId: string } | null;
  /**
   * Empty on the ordinary path. Non-empty means the chain fell through, which is otherwise
   * invisible: the entry names the model that wrote it, but a provider at the head of the order
   * that is quietly broken looks exactly like one that was never chosen.
   */
  passedOver?: CapturePassedOver[];
}

export interface CaptureRequest {
  text: string;
  /**
   * The word the submitter means, when they know it. A hint, not an instruction: the server still
   * corrects spelling and picks the lemma, and still overrides it if the text plainly says otherwise.
   * Absent is the ordinary case — a shared sentence carries no way to point at a word.
   */
  headword?: string | null;
  sourceUrl?: string | null;
  sourceTitle?: string | null;
  /** A free-text nudge for the generator — §05's "regenerate with a note". */
  note?: string | null;
  /**
   * An external dictionary's entry for this word, as the reader saw it.
   *
   * Grounding, and only grounding. It is deliberately *not* sent as `text`: the resolver reads that
   * as sentences the learner met, and every one of them would become an attestation — a claim about
   * where this person encountered the word, forged out of a dictionary's own examples. Provenance
   * is modelled here, never flagged, so the two arrive by different doors.
   */
  reference?: string | null;
  /** How closely to follow it. Absent means the `note` says what to do instead. */
  referenceMode?: "faithful" | "expand" | null;
}

/** An artifact this server holds, as its metadata sidecar describes it. */
export interface RemoteDictionary {
  id: string;
  name: string;
  sourceLang: string;
  targetLang: string;
  tier: "fields" | "html";
  licence: string;
  attribution: string;
  entryCount: number;
  keyCount: number;
  blobBytes: number;
  indexBytes: number;
  schemaVersion: number;
  sourceDate?: string;
  builtAt?: string;
}

export interface OnlineLookup {
  source: string;
  word: string;
  entries: OnlineArticle[];
}

export interface OnlineArticle {
  headword: string;
  language?: string;
  posLabel?: string;
  ipa?: string;
  senses: { definition: string; examples?: { text: string; translation?: string | null }[] }[];
}

/* ── clips ────────────────────────────────────────────────────────────────
   Server state read through a route, like the model chain and the picture settings: owner-scoped,
   never replicated, and about what the words are *made of* rather than what they are. */

/** What this deployment's corpus holds, so Settings can say more than "on" or "off". */
export interface CorpusReadout {
  configured: boolean;
  reachable: boolean;
  ready?: boolean;
  builtAt?: string | null;
  indexedLanguages?: string[];
  videos?: number;
  segments?: number;
  error?: string;
}

export interface ClipSettings {
  searchEnabled: boolean;
  /** False means "following the deployment default", which is a real answer and not a gap. */
  chosen: boolean;
  corpus: CorpusReadout;
}

export interface ClipSearchResult {
  lexemeId: string;
  /** False when nothing was asked: the corpus does not index this language yet. */
  searched: boolean;
  skipped: string | null;
  examples: unknown[];
  /** Ids the model named that the request never offered. A prompt bug, surfaced rather than hidden. */
  dropped: number;
  usage: { provider?: string; model?: string; seconds?: number } | null;
}

export class AcervoApiError extends Error {
  constructor(message: string, readonly status: number, readonly code: string) { super(message); }
}

function timeoutSignal(milliseconds: number): AbortSignal | undefined {
  return typeof AbortSignal !== "undefined" && "timeout" in AbortSignal ? AbortSignal.timeout(milliseconds) : undefined;
}

class ApiClient {
  private session: StoredSession | null = null;
  private onUnauthorized: (() => void) | null = null;

  configure(session: StoredSession | null) { this.session = session; }
  current() { return this.session; }

  /** Where a file lives, for the direct reads that do not go through the JSON envelope. */
  fileUrl(root: string, path: string): string {
    const baseUrl = this.session?.baseUrl;
    if (!baseUrl) throw new AcervoApiError("Configure the Acervo server first.", 0, "not_configured");
    return `${baseUrl}${root}${path}`;
  }

  authHeaders(): Record<string, string> {
    return this.session?.token ? { Authorization: `Bearer ${this.session.token}` } : {};
  }
  /** Called when the server rejects the stored token. The replica is deliberately kept. */
  handleUnauthorized(handler: (() => void) | null) { this.onUnauthorized = handler; }

  async call<T>(path: string, options: RequestInit = {}, anonymous = false, timeout = REQUEST_TIMEOUT): Promise<T> {
    if (!anonymous && !this.session?.token) throw new AcervoApiError("Sign in to continue.", 401, "unauthenticated");
    const baseUrl = this.session?.baseUrl;
    if (!baseUrl) throw new AcervoApiError("Configure the Acervo server first.", 0, "not_configured");
    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");
    // Only where the caller has not said otherwise: a picture is sent as a raw body with its own
    // type, and overwriting that would hand the server a WebP labelled as JSON.
    if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    if (!anonymous && this.session?.token) headers.set("Authorization", `Bearer ${this.session.token}`);
    let response: Response;
    try { response = await fetch(`${baseUrl}${API_PATH}${path}`, { ...options, headers, cache: "no-store", signal: timeoutSignal(timeout) }); }
    catch { throw new AcervoApiError("The Acervo server could not be reached. Local vocabulary remains available.", 0, "offline"); }
    let envelope: Envelope<T> = {};
    try { envelope = await response.json() as Envelope<T>; } catch { /* diagnosed below */ }
    if (!response.ok || envelope.error || envelope.data === undefined) {
      if (response.status === 401 && !anonymous) this.onUnauthorized?.();
      throw new AcervoApiError(envelope.error?.message || "The Acervo server returned an invalid response.", response.status, envelope.error?.code || "request_failed");
    }
    return envelope.data;
  }
}

const client = new ApiClient();

export const backendSession = {
  current: () => client.current(),
  async restore(): Promise<StoredSession | null> {
    const session = await sessionStore.load();
    client.configure(session);
    return session;
  },
  async login(rawUrl: string, email: string, password: string): Promise<StoredSession> {
    const baseUrl = normalizeServerURL(rawUrl);
    client.configure({ baseUrl, email: email.trim(), token: "", userId: "" });
    try {
      const result = await client.call<LoginResponse>("/session", {
        method: "POST", body: JSON.stringify({ email: email.trim(), password })
      }, true);
      const session = { baseUrl, email: result.user.email, token: result.token, userId: result.user.id };
      await sessionStore.save(session);
      client.configure(session);
      return session;
    } catch (error) { client.configure(null); throw error; }
  },
  async refresh(): Promise<StoredSession | null> {
    const current = client.current();
    if (!current?.token) return current;
    try {
      const result = await client.call<LoginResponse>("/session/refresh", { method: "POST" });
      const session = { ...current, email: result.user.email, token: result.token, userId: result.user.id };
      await sessionStore.save(session);
      client.configure(session);
      return session;
    } catch (error) {
      if (error instanceof AcervoApiError && error.status === 401) {
        client.configure(null);
        await sessionStore.clear();
        return null;
      }
      return current;
    }
  },
  async logout() { client.configure(null); await sessionStore.clear(); },
  /** Drops the token but keeps the replica: the vocabulary is still the owner's. */
  async reject() { const current = client.current(); client.configure(null); if (current) await sessionStore.clear(); },
  onUnauthorized(handler: (() => void) | null) { client.handleUnauthorized(handler); },

  /**
   * A server fact, read once. Unauthenticated on the server, and asked for anonymously here so it
   * still answers while a session is being restored — but it goes through `client.call` like every
   * other route, because on the native host the server is not the page's origin.
   */
  health(): Promise<ServerHealth> {
    return client.call<ServerHealth>("/health", {}, true);
  },

  pullGraph(since: number): Promise<PullResponse> {
    return client.call<PullResponse>(`/graph?schemaVersion=${SCHEMA_VERSION}&since=${since}`);
  },
  pushGraph(deviceId: string, changes: Partial<VocabularyGraph>): Promise<PushResponse> {
    return client.call<PushResponse>("/graph", {
      method: "POST", body: JSON.stringify({ schemaVersion: SCHEMA_VERSION, deviceId, changes })
    });
  },
  /**
   * Submits text to the ingest endpoint and returns what it made of it.
   *
   * `apply` is deliberately never set from here: the interface reviews a draft and then writes it
   * through the repository, so capture gets no private path into the store. The headless transports
   * are the ones that ask the server to apply.
   */
  captureText(deviceId: string, request: CaptureRequest): Promise<CaptureResult> {
    return client.call<CaptureResult>("/capture", {
      method: "POST",
      body: JSON.stringify({
        schemaVersion: SCHEMA_VERSION,
        deviceId,
        mode: "single",
        apply: false,
        text: request.text,
        headword: request.headword?.trim() || null,
        sourceUrl: request.sourceUrl ?? null,
        sourceTitle: request.sourceTitle ?? null,
        note: request.note ?? null,
        reference: request.reference?.trim() || null,
        referenceMode: request.referenceMode ?? null
      })
    }, false, CAPTURE_TIMEOUT);
  },
  /* ── external dictionaries ────────────────────────────────────────────
     Two calls and two addresses. The list and an online lookup are ordinary JSON; the artifact
     itself is a static file read with byte ranges, so the reader can treat a dictionary the server
     holds exactly like one this device stored. */

  /** The catalogue as this owner sees it, and their chains. Owner-scoped, so it needs a session. */
  fetchModels(): Promise<ModelCatalogue> {
    return client.call<ModelCatalogue>("/models");
  },
  /**
   * Changes the chains named and returns the whole readout.
   *
   * `null` for a kind forgets the choice and returns it to the server's own order — without it, one
   * saved chain would be a one-way door, since unchecking everything is refused as an empty chain.
   * The answer is the server's, not this client's optimism, and it carries fresh availability.
   */
  saveModelSelection(chains: Record<string, ModelPair[] | null>): Promise<ModelCatalogue> {
    return client.call<ModelCatalogue>("/models/selection", {
      method: "PUT", body: JSON.stringify({ chains })
    });
  },

  imageSettings(): Promise<ImageSettings> {
    return client.call<ImageSettings>("/images/settings");
  },
  saveImageSettings(changes: Partial<Pick<ImageSettings, "drawEnabled" | "stylesOff" | "boostVariety">>): Promise<ImageSettings> {
    return client.call<ImageSettings>("/images/settings", {
      method: "PUT", body: JSON.stringify(changes)
    });
  },

  /** One text call covering every sense of the word. Its own timeout — a model call, not a read. */
  briefLexeme(lexemeId: string, deviceId: string): Promise<{ lexemeId: string; imagePrompts: ImagePromptRow[] }> {
    return client.call<{ lexemeId: string; imagePrompts: ImagePromptRow[] }>(
      `/images/lexemes/${encodeURIComponent(lexemeId)}/brief`,
      { method: "POST", body: JSON.stringify({ deviceId }) },
      false,
      BRIEF_TIMEOUT
    );
  },

  /**
   * One image call. `prompt` and `styleId` are edit-and-draw and cost no text call; without them
   * the stored brief is drawn again with a fresh seed.
   */
  renderImage(promptId: string, deviceId: string, overrides: { prompt?: string; styleId?: string } = {}): Promise<ImagePromptRow> {
    return client.call<ImagePromptRow>(
      `/images/prompts/${encodeURIComponent(promptId)}/render`,
      { method: "POST", body: JSON.stringify({ deviceId, ...overrides }) },
      false,
      RENDER_TIMEOUT
    );
  },

  /**
   * The owner's own file, as a raw body — one part, so no multipart and no dependency for it.
   *
   * Keyed by the sense rather than by a prompt: a picture you supply may be the first thing that
   * sense ever gets, and the prompt id is derived from the sense, so the server finds or mints the
   * row at the id it was always going to have.
   */
  async attachImage(
    senseId: string, deviceId: string, file: Blob, drawnBy: string | null = null
  ): Promise<ImagePromptRow> {
    return client.call<ImagePromptRow>(
      `/images/senses/${encodeURIComponent(senseId)}/picture`,
      {
        method: "PUT",
        body: file,
        headers: {
          "Content-Type": file.type || "application/octet-stream",
          "X-Acervo-Device": deviceId,
          /* Naming the model that drew it makes this a *restore* rather than a picture you chose:
             the row keeps its provenance and stays replaceable. Absent, it is your own file, which
             carries no model and is left alone by anything that draws. */
          ...(drawnBy ? { "X-Acervo-Drawn-By": drawnBy } : {})
        }
      },
      false,
      RENDER_TIMEOUT
    );
  },

  /** Remove the picture and rule the sense out. Not a tombstone — see `services/images.py`. */
  removeImage(promptId: string, deviceId: string): Promise<ImagePromptRow> {
    return client.call<ImagePromptRow>(
      `/images/prompts/${encodeURIComponent(promptId)}`,
      { method: "DELETE", headers: { "X-Acervo-Device": deviceId } }
    );
  },

  listDictionaries(): Promise<{ dictionaries: RemoteDictionary[] }> {
    return client.call<{ dictionaries: RemoteDictionary[] }>("/dictionaries");
  },
  lookupOnlineDictionary(source: string, word: string, language?: string): Promise<OnlineLookup> {
    const query = new URLSearchParams({ word });
    if (language) query.set("language", language);
    return client.call<OnlineLookup>(`/dictionaries/online/${encodeURIComponent(source)}?${query}`);
  },
  dictionaryFileUrl(id: string, extension: "dict" | "idx" | "json"): string {
    return client.fileUrl(DICTIONARY_PATH, `/${encodeURIComponent(id)}.${extension}`);
  },
  dictionaryHeaders(): Record<string, string> {
    return client.authHeaders();
  },

  /**
   * Where a picture lives. The route is behind bearer auth, so this URL cannot go in an `<img src>`
   * — `media.ts` fetches it with the token and hands the element a blob URL instead.
   */
  mediaFileUrl(reference: string): string {
    return client.fileUrl(MEDIA_PATH, `/${reference.split("/").map(encodeURIComponent).join("/")}`);
  },
  mediaHeaders(): Record<string, string> {
    return client.authHeaders();
  },

  /**
   * Where the corpus answers, through Acervo's own allow-listed proxy.
   *
   * A base URL and a header set rather than a method per route, because `clips.ts` hands both to
   * the *packaged* typed client — the one the retrieval repository ships and tests. Reimplementing
   * its fifteen methods here to gain Acervo's envelope would mean keeping a second copy of its
   * response types in two languages, and the proxy forwards the body verbatim so that it does not
   * have to.
   */
  speechBaseUrl(): string {
    return client.fileUrl(API_PATH, SPEECH_PATH);
  },
  speechHeaders(): Record<string, string> {
    return client.authHeaders();
  },

  findClips(deviceId: string, lexemeId: string): Promise<ClipSearchResult> {
    return client.call<ClipSearchResult>(
      `/clips/lexemes/${encodeURIComponent(lexemeId)}/find`,
      { method: "POST", body: JSON.stringify({ deviceId }) },
      false,
      CAPTURE_TIMEOUT
    );
  },
  clipSettings(): Promise<ClipSettings> {
    return client.call<ClipSettings>("/clips/settings");
  },
  saveClipSettings(changes: Partial<Pick<ClipSettings, "searchEnabled">>): Promise<ClipSettings> {
    return client.call<ClipSettings>("/clips/settings", {
      method: "PUT", body: JSON.stringify(changes)
    });
  },

  resetGraph(deviceId: string): Promise<ResetResponse> {
    return client.call<ResetResponse>("/graph/reset", {
      method: "POST",
      body: JSON.stringify({ schemaVersion: SCHEMA_VERSION, deviceId, confirm: "delete-all-words" })
    });
  }
};
