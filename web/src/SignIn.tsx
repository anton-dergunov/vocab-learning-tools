import { useState } from "react";
import { backendSession } from "./api";
import { isNativeHost } from "./pwa";
import type { StoredSession } from "./session";

export default function SignIn({ onSignedIn }: { onSignedIn(session: StoredSession): void }) {
  const native = isNativeHost();
  const [serverUrl, setServerUrl] = useState(native ? "" : window.location.origin);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      onSignedIn(await backendSession.login(serverUrl, email, password));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Sign in failed.");
    } finally {
      setBusy(false);
    }
  }

  return <div className="signin-page">
    <form className="signin" onSubmit={submit}>
      <h1 className="mark">Acervo</h1>
      <p className="lead">Sign in to your account. Your vocabulary is kept on this device afterwards, so Acervo opens offline.</p>
      {native && <div className="field">
        <label className="label" htmlFor="serverUrl">Server</label>
        <input id="serverUrl" type="url" inputMode="url" autoComplete="url" required
          placeholder="https://acervo.example.com" value={serverUrl}
          onChange={(event) => setServerUrl(event.target.value)} />
      </div>}
      <div className="field">
        <label className="label" htmlFor="email">Email</label>
        <input id="email" type="email" autoComplete="username" required
          value={email} onChange={(event) => setEmail(event.target.value)} />
      </div>
      <div className="field">
        <label className="label" htmlFor="password">Password</label>
        <input id="password" type="password" autoComplete="current-password" required
          value={password} onChange={(event) => setPassword(event.target.value)} />
      </div>
      {error && <div className="validation bad"><b>{error}</b></div>}
      <button className="tb-btn primary" type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
    </form>
  </div>;
}
