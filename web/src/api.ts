import { normalizeServerURL, sessionStore, type StoredSession } from "./session";

type Envelope<T> = { data?: T; error?: { code?: string; message?: string } };
type LoginResponse = { token: string; user: { id: string; email: string } };
const API_PATH = "/api/acervo/v1";
const REQUEST_TIMEOUT = 15_000;

export class AcervoApiError extends Error {
  constructor(message: string, readonly status: number, readonly code: string) { super(message); }
}

function timeoutSignal(): AbortSignal | undefined {
  return typeof AbortSignal !== "undefined" && "timeout" in AbortSignal ? AbortSignal.timeout(REQUEST_TIMEOUT) : undefined;
}

class ApiClient {
  private session: StoredSession | null = null;

  configure(session: StoredSession | null) { this.session = session; }
  current() { return this.session; }

  async call<T>(path: string, options: RequestInit = {}, anonymous = false): Promise<T> {
    if (!anonymous && !this.session?.token) throw new AcervoApiError("Sign in to continue.", 401, "unauthenticated");
    const baseUrl = this.session?.baseUrl;
    if (!baseUrl) throw new AcervoApiError("Configure the Acervo server first.", 0, "not_configured");
    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");
    if (options.body) headers.set("Content-Type", "application/json");
    if (!anonymous && this.session?.token) headers.set("Authorization", `Bearer ${this.session.token}`);
    let response: Response;
    try { response = await fetch(`${baseUrl}${API_PATH}${path}`, { ...options, headers, cache: "no-store", signal: timeoutSignal() }); }
    catch { throw new AcervoApiError("The Acervo server could not be reached. Local vocabulary remains available.", 0, "offline"); }
    let envelope: Envelope<T> = {};
    try { envelope = await response.json() as Envelope<T>; } catch { /* diagnosed below */ }
    if (!response.ok || envelope.error || envelope.data === undefined) {
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
  async logout() { client.configure(null); await sessionStore.clear(); }
};
