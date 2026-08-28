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
