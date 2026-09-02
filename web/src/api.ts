import type { PartOfSpeech, VocabularyGraph } from "./domain";
import { normalizeServerURL, sessionStore, type StoredSession } from "./session";
import type { ArticleDraft } from "./yaml";

type Envelope<T> = { data?: T; error?: { code?: string; message?: string } };
type LoginResponse = { token: string; user: { id: string; email: string } };

/** Shared with the server hook. A mismatch stops synchronisation until the app is updated. */
export const SCHEMA_VERSION = 5;

interface SyncEnvelope {
  schemaVersion: number;
  datasetId: string;
  cursor: number;
  serverTime: string;
}
export type PullResponse = SyncEnvelope & { changes: VocabularyGraph };
export type PushResponse = SyncEnvelope & { records: Partial<VocabularyGraph> };
export type ResetResponse = SyncEnvelope & { deleted: number };

const API_PATH = "/api/acervo/v1";
/** Compiled dictionaries are served as plain files, outside the JSON API and outside `pb_public`. */
const DICTIONARY_PATH = "/api/acervo/dictionaries";
const REQUEST_TIMEOUT = 15_000;
/** Capture is two model calls deep, so the sync timeout would abort a request that is working. */
const CAPTURE_TIMEOUT = 120_000;

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

export interface CaptureResult {
  resolution: CaptureResolution;
  duplicates: CaptureDuplicate[];
  draft: ArticleDraft | null;
  applied: { lexemeId: string } | null;
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

  /** Where an artifact file lives, for the direct reads that do not go through the JSON envelope. */
  fileUrl(path: string): string {
    const baseUrl = this.session?.baseUrl;
    if (!baseUrl) throw new AcervoApiError("Configure the Acervo server first.", 0, "not_configured");
    return `${baseUrl}${DICTIONARY_PATH}${path}`;
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
    if (options.body) headers.set("Content-Type", "application/json");
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

  listDictionaries(): Promise<{ dictionaries: RemoteDictionary[] }> {
    return client.call<{ dictionaries: RemoteDictionary[] }>("/dictionaries");
  },
  lookupOnlineDictionary(source: string, word: string, language?: string): Promise<OnlineLookup> {
    const query = new URLSearchParams({ word });
    if (language) query.set("language", language);
    return client.call<OnlineLookup>(`/dictionaries/online/${encodeURIComponent(source)}?${query}`);
  },
  dictionaryFileUrl(id: string, extension: "dict" | "idx" | "json"): string {
    return client.fileUrl(`/${encodeURIComponent(id)}.${extension}`);
  },
  dictionaryHeaders(): Record<string, string> {
    return client.authHeaders();
  },

  resetGraph(deviceId: string): Promise<ResetResponse> {
    return client.call<ResetResponse>("/graph/reset", {
      method: "POST",
      body: JSON.stringify({ schemaVersion: SCHEMA_VERSION, deviceId, confirm: "delete-all-vocabulary" })
    });
  }
};
