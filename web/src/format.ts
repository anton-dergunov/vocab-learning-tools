const DAY = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

/** "11 Feb 2026" — the compact form the article and attestation footers use. */
export function formatDay(instant: string | null): string {
  if (!instant) return "—";
  const parsed = Date.parse(instant);
  return Number.isNaN(parsed) ? "—" : DAY.format(parsed);
}

/** "7:41" — a clip start expressed as minutes and seconds. */
export function formatClock(seconds: number | null): string {
  const total = Math.max(0, Math.floor(seconds ?? 0));
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
}

/** "just now" / "4 minutes ago" — how recently a sync happened, at the precision anyone cares about. */
export function relativeTime(instant: string | null): string {
  if (!instant) return "never";
  const parsed = Date.parse(instant);
  if (Number.isNaN(parsed)) return "never";
  const seconds = Math.max(0, Math.round((Date.now() - parsed) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  return formatDay(instant);
}
