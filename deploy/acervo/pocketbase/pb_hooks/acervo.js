const API_ROOT = "/api/acervo/v1";
const DOWNLOAD_ROOT = "/api/acervo/downloads/";
const RECORD_ID = /^[a-z0-9]{15}$/;
const INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
const LANGUAGE = /^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/;

function trimmed(value) {
  return String(value == null ? "" : value).trim();
}

function jsonValue(value) {
  try { return JSON.parse(toString(value)); }
  catch (_) {}
  try { return JSON.parse(JSON.stringify(value)); }
  catch (_) { return value; }
}

function respond(event, data, status) {
  return event.json(status || 200, { data: data });
}

function apiError(status, code, message) {
  const error = new Error(message);
  error.acervoStatus = status;
  error.acervoCode = code;
  return error;
}

function respondError(event, error) {
  const status = error.acervoStatus || 500;
  const message = status >= 500 ? "The Acervo server could not complete the request." : String(error.message || error);
  if (status >= 500) event.app.logger().error("Acervo API request failed", "error", error);
  return event.json(status, { error: { code: error.acervoCode || "server_error", message: message } });
}

function body(event) {
  return event.requestInfo().body || {};
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
  const method = String(event.request.method || "GET").toUpperCase();
  try {
    if (method === "GET" && relative === "/health") {
      return respond(event, {
        name: "Acervo",
        version: trimmed($os.getenv("ACERVO_APP_VERSION")) || "0.0.0",
        build: trimmed($os.getenv("ACERVO_APP_BUILD")) || "0",
        schemaVersion: 1,
      });
    }
    if (method === "GET" && relative === "/mac-release") return respond(event, releaseManifest());
    if (method === "POST" && relative === "/session") {
      const request = body(event);
      let user;
      try { user = event.app.findAuthRecordByEmail("users", trimmed(request.email)); }
      catch (_) { throw apiError(401, "invalid_credentials", "The email or password is incorrect."); }
      if (!user.validatePassword(String(request.password || ""))) {
        throw apiError(401, "invalid_credentials", "The email or password is incorrect.");
      }
      return respond(event, { token: user.newAuthToken(), user: { id: user.id, email: user.email() } });
    }
    if (method === "POST" && relative === "/session/refresh") {
      if (!event.auth || event.auth.collection().name !== "users") {
        throw apiError(401, "unauthenticated", "Sign in to continue.");
      }
      return respond(event, { token: event.auth.newAuthToken(), user: { id: event.auth.id, email: event.auth.email() } });
    }
    throw apiError(404, "not_found", "The requested Acervo API route does not exist.");
  } catch (error) {
    return respondError(event, error);
  }
}

function invalid(message) {
  throw new BadRequestError(message);
}

function validLanguage(value, label) {
  const language = trimmed(value);
  if (!LANGUAGE.test(language)) invalid(label + " must be a BCP-47 language tag.");
  return language;
}

function stringArray(value, label) {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string" || !item.trim())) {
    invalid(label + " must be an array of non-empty strings.");
  }
  const seen = {};
  value.forEach((item) => {
    if (seen[item]) invalid(label + " must not contain duplicates.");
    seen[item] = true;
  });
}

function glossArray(value) {
  if (!Array.isArray(value) || value.length === 0) invalid("Glosses must contain at least one language group.");
  const languages = {};
  value.forEach((gloss) => {
    if (!gloss || typeof gloss !== "object") invalid("Each gloss must be an object.");
    const language = validLanguage(gloss.lang, "Gloss language");
    if (languages[language]) invalid("Gloss languages must be unique within a sense.");
    languages[language] = true;
    stringArray(gloss.terms, "Gloss terms");
    if (gloss.terms.length === 0) invalid("Each gloss must contain at least one term.");
  });
}

function syncRecord(record) {
  if (!RECORD_ID.test(record.id)) invalid("Record ids must be 15 lowercase letters or digits.");
  if (!INSTANT.test(record.getString("created_at")) || !INSTANT.test(record.getString("edited_at"))) {
    invalid("Record timestamps must be ISO-8601 UTC instants with milliseconds.");
  }
}

function related(app, collection, id, label) {
  try { return app.findRecordById(collection, id); }
  catch (_) { invalid(label + " does not exist."); }
}

function sameOwner(record, parent, label) {
  if (record.getString("owner") !== parent.getString("owner")) invalid(label + " must belong to the same owner.");
}

function validateRecord(app, record) {
  const collection = record.collection().name;
  syncRecord(record);
  if (collection === "lexemes") {
    const language = validLanguage(record.getString("language"), "Lexeme language");
    if (language.toLowerCase().indexOf("zh") === 0 && !trimmed(record.getString("reading"))) {
      invalid("Chinese lexemes require a reading.");
    }
    stringArray(jsonValue(record.get("topics")), "Topics");
    stringArray(jsonValue(record.get("notes")), "Notes");
    return;
  }
  if (collection === "senses") {
    sameOwner(record, related(app, "lexemes", record.getString("lexeme"), "Lexeme"), "Sense");
    validLanguage(record.getString("definition_lang"), "Definition language");
    glossArray(jsonValue(record.get("glosses")));
    return;
  }
  if (collection === "attestations") {
    sameOwner(record, related(app, "lexemes", record.getString("lexeme"), "Lexeme"), "Attestation");
    return;
  }
  if (collection === "examples") {
    const sense = related(app, "senses", record.getString("sense"), "Sense");
    sameOwner(record, sense, "Example");
    validLanguage(record.getString("text_lang"), "Example language");
    const translation = trimmed(record.getString("translation"));
    const translationLanguage = trimmed(record.getString("translation_lang"));
    if (Boolean(translation) !== Boolean(translationLanguage)) invalid("Example translation and language must be provided together.");
    if (translationLanguage) validLanguage(translationLanguage, "Translation language");
    const sourceId = record.getString("source_attestation");
    if (record.getString("origin") === "attestation" && !sourceId) invalid("Attestation examples require a source attestation.");
    if (sourceId) {
      const attestation = related(app, "attestations", sourceId, "Source attestation");
      sameOwner(record, attestation, "Example source attestation");
      if (attestation.getString("lexeme") !== sense.getString("lexeme")) {
        invalid("Example source attestation and sense must belong to the same lexeme.");
      }
    }
    return;
  }
  if (collection === "image_prompts") {
    const lexeme = related(app, "lexemes", record.getString("lexeme"), "Lexeme");
    sameOwner(record, lexeme, "Image prompt");
    const senseId = record.getString("sense");
    if (senseId) {
      const sense = related(app, "senses", senseId, "Sense");
      sameOwner(record, sense, "Image prompt sense");
      if (sense.getString("lexeme") !== lexeme.id) invalid("Image prompt sense must belong to its lexeme.");
    }
    return;
  }
  if (collection === "study_states") {
    sameOwner(record, related(app, "lexemes", record.getString("lexeme"), "Lexeme"), "Study state");
    const cardIds = jsonValue(record.get("card_ids"));
    if (!Array.isArray(cardIds) || cardIds.some((id) => !Number.isSafeInteger(id) || id < 0)) {
      invalid("Study-state card ids must be non-negative safe integers.");
    }
  }
}

module.exports = { dispatch: dispatch, validateRecord: validateRecord };
