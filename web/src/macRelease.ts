export interface MacRelease {
  version: string;
  build: string;
  file: string;
  size: number;
  sha256: string;
  url: string;
}

interface ReleaseEnvelope {
  data: MacRelease | null;
}

const DOWNLOAD_ROOT = "/api/acervo/downloads/";

function validRelease(value: unknown): value is MacRelease {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<MacRelease>;
  return typeof candidate.version === "string"
    && typeof candidate.build === "string"
    && typeof candidate.file === "string"
    && typeof candidate.size === "number"
    && typeof candidate.sha256 === "string"
    && typeof candidate.url === "string"
    && candidate.url.startsWith(DOWNLOAD_ROOT);
}

export async function fetchMacRelease(signal?: AbortSignal): Promise<MacRelease | null> {
  const response = await fetch("/api/acervo/v1/mac-release", {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error("The native release endpoint is unavailable.");
  const envelope = await response.json() as ReleaseEnvelope;
  if (envelope.data === null) return null;
  if (!validRelease(envelope.data)) throw new Error("The native release manifest is invalid.");
  return envelope.data;
}
