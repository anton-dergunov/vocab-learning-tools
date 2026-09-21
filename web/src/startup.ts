/**
 * Where this launch spent its time before the words were on screen, measured on the device itself.
 *
 * A cold start on a tablet reads the whole replica back from IndexedDB before anything can be
 * shown. How long that takes on the device that matters cannot be measured from a laptop, so the
 * launch measures itself and Settings ▸ Sync says what it found. Kept in memory for this launch
 * only; the first time the words are shown is the one worth knowing, so later loads (a sign-in, a
 * fresh download) do not overwrite it.
 */

type Mark = "session" | "readStart" | "readEnd" | "checked" | "shown";

export interface StartupTimings {
  /** From the page starting to the stored sign-in being read back. */
  session: number;
  /** Reading every record of the replica from the device's storage. */
  read: number;
  records: number;
  /** Checking the replica once, as a whole, before it is trusted. */
  check: number;
  /** From the replica being ready to the first frame with words in it. */
  show: number;
  /** From the page starting to the first frame with words in it. */
  total: number;
  /** Why the stored copy was downloaded again instead of read, or null when it was read. */
  setAside: string | null;
}

const marks = new Map<Mark, number>();
let records = 0;
/** Whether the launch opened a stored sign-in; a launch that asked for a password has no timing. */
let restored = false;
/** Why this device's stored copy could not be used and was downloaded again, if it could not. */
let setAside: string | null = null;

export function markStartup(name: Mark, at: number = performance.now()): void {
  if (!marks.has(name)) marks.set(name, at);
}

export function markSession(present: boolean): void {
  if (marks.has("session")) return;
  restored = present;
  markStartup("session");
}

export function markReplicaRead(count: number): void {
  if (marks.has("readEnd")) return;
  records = count;
  markStartup("readEnd");
}

/** The stored copy was refused and is being downloaded again, for this reason. */
export function markReplicaSetAside(reason: string): void {
  setAside ??= reason;
}

export function startupTimings(): StartupTimings | null {
  const at = (name: Mark) => marks.get(name);
  const [session, readStart, readEnd, checked, shown] =
    (["session", "readStart", "readEnd", "checked", "shown"] as const).map(at);
  if (!restored || session === undefined || readStart === undefined || readEnd === undefined
    || checked === undefined || shown === undefined) return null;
  return {
    session, read: readEnd - readStart, records, check: checked - readEnd, show: shown - checked, total: shown,
    setAside
  };
}

/** Forget this launch's marks. For tests, which share one module across cases. */
export function resetStartup(): void {
  marks.clear();
  records = 0;
  restored = false;
  setAside = null;
}

const ms = (value: number) => value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${Math.round(value)} ms`;

/** One line for Settings: `Opened in 1.1 s — reading 10,812 records 820 ms · checking 60 ms · …`. */
export function describeStartup(timings: StartupTimings): string {
  return `Opened in ${ms(timings.total)} — reading ${timings.records.toLocaleString("en")} records `
    + `${ms(timings.read)} · checking ${ms(timings.check)} · first list ${ms(timings.show)}`
    + (timings.setAside ? `. This device's copy could not be used (${timings.setAside}) and was downloaded again.` : "");
}
