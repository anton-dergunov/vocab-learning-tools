const API_ROOT = "/api/acervo/v1";
const DOWNLOAD_ROOT = "/api/acervo/downloads/";

function trimmed(value) {
  return String(value == null ? "" : value).trim();
}

function respond(event, data, status) {
  return event.json(status || 200, { data: data });
}

function releaseManifest() {
  const directory = trimmed($os.getenv("ACERVO_DOWNLOADS_PATH")) || "/pb/downloads";
  let manifest;
  try {
    manifest = JSON.parse(toString($os.readFile(directory + "/release.json")));
  } catch (_) {
    return null;
  }
  const file = trimmed(manifest.file);
  const version = trimmed(manifest.version);
  const build = trimmed(manifest.build);
  const sha256 = trimmed(manifest.sha256);
  if (!file || !version || !build || !sha256) return null;
  return {
    version: version,
    build: build,
    file: file,
    size: Number(manifest.size) || 0,
    sha256: sha256,
    url: DOWNLOAD_ROOT + encodeURIComponent(file),
  };
}

function dispatch(event) {
  const path = String(event.request.url.path || "");
  const relative = path.indexOf(API_ROOT) === 0 ? path.slice(API_ROOT.length) || "/" : path;
  if (relative === "/health") {
    return respond(event, {
      name: "Acervo",
      version: trimmed($os.getenv("ACERVO_APP_VERSION")) || "0.0.0",
      build: trimmed($os.getenv("ACERVO_APP_BUILD")) || "0",
    });
  }
  if (relative === "/mac-release") return respond(event, releaseManifest());
  return event.json(404, { error: { code: "not_found", message: "The requested Acervo API route does not exist." } });
}

module.exports = { dispatch: dispatch };
