const API_ROOT = "/api/acervo/v1";
const SCHEMA_VERSION = 4;
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

function query(event) {
  return event.requestInfo().query || {};
}

/** `findFirstRecordByFilter` reports "not found" by throwing; absence is ordinary here. */
function firstRecord(app, collection, filter, params) {
  try { return app.findFirstRecordByFilter(collection, filter, params); }
  catch (_) { return null; }
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

/* ── owner-scoped graph projection ──────────────────────────────────────
   Maps the snake_case storage boundary onto the camelCase client model in
   web/src/domain.ts. Tombstones are included; the client owns filtering. */

function textOrNull(record, field) {
  return trimmed(record.getString(field)) || null;
}

function instantOrNull(record, field) {
  let value;
  try { value = record.getDateTime(field); } catch (_) { return null; }
  const text = trimmed(value ? value.string() : "");
  if (!text) return null;
  return text.replace(" ", "T");
}

function syncFieldsOf(record) {
  return {
    ownerId: record.getString("owner"),
    deleted: Boolean(record.get("deleted")),
    createdAt: record.getString("created_at"),
    editedAt: record.getString("edited_at"),
    editedBy: record.getString("edited_by"),
    revision: Number(record.get("revision")) || 0,
  };
}

function projected(record, project) {
  const value = project(record);
  value.id = record.id;
  return Object.assign(value, syncFieldsOf(record));
}

/** Everything this owner holds past `since`, in revision order. `since = 0` returns the lot. */
function ownerRecords(app, collection, ownerId, since, project) {
  return app.findRecordsByFilter(
    collection, "owner = {:owner} && revision > {:since}", "revision", 0, 0,
    { owner: ownerId, since: since }
  ).map((record) => projected(record, project));
}

/* Storage <-> client mapping, in graph order: topics before lexemes, lexemes before senses and
   attestations, those before examples and sense-linked image prompts. Applying a batch in this
   order means a relation always resolves, so it is also the merge order the write route uses. */

function setText(record, field, value) { record.set(field, trimmed(value)); }
function setNumber(record, field, value) { record.set(field, Number(value) || 0); }
function setList(record, field, value) { record.set(field, Array.isArray(value) ? value : []); }

const COLLECTIONS = [
  {
    key: "topics", name: "topics",
    project: (record) => ({
      name: record.getString("name"),
      icon: textOrNull(record, "icon"),
      order: Number(record.get("topic_order")) || 0,
    }),
    assign: (record, value) => {
      setText(record, "name", value.name);
      setText(record, "icon", value.icon);
      setNumber(record, "topic_order", value.order);
    },
  },
  {
    key: "lexemes", name: "lexemes",
    project: (record) => ({
      language: record.getString("language"),
      headword: record.getString("headword"),
      lemma: record.getString("lemma"),
      reading: textOrNull(record, "reading"),
      ipa: textOrNull(record, "ipa"),
      pos: record.getString("pos"),
      gender: textOrNull(record, "gender"),
      register: textOrNull(record, "register"),
      dialect: textOrNull(record, "dialect"),
      emoji: textOrNull(record, "emoji"),
      topicIds: jsonValue(record.getStringSlice("topics")) || [],
      status: record.getString("status"),
      shortGloss: textOrNull(record, "short_gloss"),
      notes: jsonValue(record.get("notes")) || [],
    }),
    assign: (record, value) => {
      setText(record, "language", value.language);
      setText(record, "headword", value.headword);
      setText(record, "lemma", value.lemma);
      setText(record, "reading", value.reading);
      setText(record, "ipa", value.ipa);
      setText(record, "pos", value.pos);
      setText(record, "gender", value.gender);
      setText(record, "register", value.register);
      setText(record, "dialect", value.dialect);
      setText(record, "emoji", value.emoji);
      setList(record, "topics", value.topicIds);
      setText(record, "status", value.status);
      setText(record, "short_gloss", value.shortGloss);
      setList(record, "notes", value.notes);
    },
  },
  {
    key: "senses", name: "senses",
    project: (record) => ({
      lexemeId: record.getString("lexeme"),
      definition: record.getString("definition"),
      definitionLang: record.getString("definition_lang"),
      glosses: jsonValue(record.get("glosses")) || [],
      domain: textOrNull(record, "domain"),
      order: Number(record.get("sense_order")) || 0,
    }),
    assign: (record, value) => {
      setText(record, "lexeme", value.lexemeId);
      setText(record, "definition", value.definition);
      setText(record, "definition_lang", value.definitionLang);
      setList(record, "glosses", value.glosses);
      setText(record, "domain", value.domain);
      setNumber(record, "sense_order", value.order);
    },
  },
  {
    key: "attestations", name: "attestations",
    project: (record) => ({
      lexemeId: record.getString("lexeme"),
      text: record.getString("text"),
      translation: textOrNull(record, "translation"),
      sourceUrl: textOrNull(record, "source_url"),
      sourceTitle: textOrNull(record, "source_title"),
      sourceKind: record.getString("source_kind"),
      capturedAt: instantOrNull(record, "captured_at"),
    }),
    assign: (record, value) => {
      setText(record, "lexeme", value.lexemeId);
      setText(record, "text", value.text);
      setText(record, "translation", value.translation);
      setText(record, "source_url", value.sourceUrl);
      setText(record, "source_title", value.sourceTitle);
      setText(record, "source_kind", value.sourceKind);
      setText(record, "captured_at", value.capturedAt);
    },
  },
  {
    key: "examples", name: "examples",
    project: (record) => {
      const videoRef = textOrNull(record, "video_ref");
      return {
        senseId: record.getString("sense"),
        text: record.getString("text"),
        textLang: record.getString("text_lang"),
        translation: textOrNull(record, "translation"),
        translationLang: textOrNull(record, "translation_lang"),
        origin: record.getString("origin"),
        sourceAttestationId: textOrNull(record, "source_attestation"),
        modelId: textOrNull(record, "model_id"),
        videoRef: videoRef,
        videoTitle: videoRef ? textOrNull(record, "video_title") : null,
        videoStart: videoRef ? Number(record.get("video_start")) || 0 : null,
        imageRef: textOrNull(record, "image_ref"),
        audioRef: textOrNull(record, "audio_ref"),
        note: textOrNull(record, "note"),
        matchedForm: textOrNull(record, "matched_form"),
        matchedTranslationForm: textOrNull(record, "matched_translation_form"),
        approved: Boolean(record.get("approved")),
      };
    },
    assign: (record, value) => {
      setText(record, "sense", value.senseId);
      setText(record, "text", value.text);
      setText(record, "text_lang", value.textLang);
      setText(record, "translation", value.translation);
      setText(record, "translation_lang", value.translationLang);
      setText(record, "origin", value.origin);
      setText(record, "source_attestation", value.sourceAttestationId);
      setText(record, "model_id", value.modelId);
      setText(record, "video_ref", value.videoRef);
      setText(record, "video_title", value.videoTitle);
      setNumber(record, "video_start", value.videoStart);
      setText(record, "image_ref", value.imageRef);
      setText(record, "audio_ref", value.audioRef);
      setText(record, "note", value.note);
      setText(record, "matched_form", value.matchedForm);
      setText(record, "matched_translation_form", value.matchedTranslationForm);
      record.set("approved", value.approved === true);
    },
  },
  {
    key: "imagePrompts", name: "image_prompts",
    project: (record) => ({
      lexemeId: record.getString("lexeme"),
      senseId: textOrNull(record, "sense"),
      prompt: record.getString("prompt"),
      styleId: record.getString("style_id"),
      seed: Number(record.get("seed")) || 0,
      modelId: record.getString("model_id"),
      promptVersion: record.getString("prompt_version"),
      imageRef: textOrNull(record, "image_ref"),
      imageModelId: textOrNull(record, "image_model_id"),
    }),
    assign: (record, value) => {
      setText(record, "lexeme", value.lexemeId);
      setText(record, "sense", value.senseId);
      setText(record, "prompt", value.prompt);
      setText(record, "style_id", value.styleId);
      setNumber(record, "seed", value.seed);
      setText(record, "model_id", value.modelId);
      setText(record, "prompt_version", value.promptVersion);
      setText(record, "image_ref", value.imageRef);
      setText(record, "image_model_id", value.imageModelId);
    },
  },
  {
    key: "studyStates", name: "study_states",
    project: (record) => ({
      lexemeId: record.getString("lexeme"),
      system: record.getString("system"),
      noteId: Number(record.get("note_id")) || null,
      cardIds: jsonValue(record.get("card_ids")) || [],
      reps: Number(record.get("reps")) || 0,
      lapses: Number(record.get("lapses")) || 0,
      stability: Number(record.get("stability")) || 0,
      difficulty: Number(record.get("difficulty")) || 0,
      retrievability: Number(record.get("retrievability")) || 0,
      lastReview: instantOrNull(record, "last_review"),
      syncedAt: instantOrNull(record, "synced_at"),
    }),
    assign: (record, value) => {
      setText(record, "lexeme", value.lexemeId);
      setText(record, "system", value.system);
      setNumber(record, "note_id", value.noteId);
      setList(record, "card_ids", value.cardIds);
      setNumber(record, "reps", value.reps);
      setNumber(record, "lapses", value.lapses);
      setNumber(record, "stability", value.stability);
      setNumber(record, "difficulty", value.difficulty);
      setNumber(record, "retrievability", value.retrievability);
      setText(record, "last_review", value.lastReview);
      setText(record, "synced_at", value.syncedAt);
    },
  },
];

const COLLECTION_BY_KEY = {};
COLLECTIONS.forEach((entry) => { COLLECTION_BY_KEY[entry.key] = entry; });

function ownerGraph(app, ownerId, since) {
  const graph = {};
  COLLECTIONS.forEach((entry) => {
    graph[entry.key] = ownerRecords(app, entry.name, ownerId, since, entry.project);
  });
  return graph;
}

/* ── replication ────────────────────────────────────────────────────────
   One strictly increasing sequence per owner. Its record id is the dataset identity: rebuild the
   database and every outstanding client cursor is invalidated, which is the only thing that stops
   a client asking for revisions the new database has not reached yet. */

function sequenceRecord(app, ownerId) {
  const existing = firstRecord(app, "sync_state", "owner = {:owner}", { owner: ownerId });
  if (existing) return existing;
  const record = new Record(app.findCollectionByNameOrId("sync_state"));
  record.set("owner", ownerId);
  record.set("sequence", 0);
  try {
    app.save(record);
  } catch (error) {
    // Two first-ever requests for one account can both find nothing; the unique owner index
    // decides which creates the row, and the loser reads what the winner wrote.
    const raced = firstRecord(app, "sync_state", "owner = {:owner}", { owner: ownerId });
    if (!raced) throw error;
    return raced;
  }
  return record;
}

/**
 * Takes the next revision for this owner. Called from the record save hooks rather than only from
 * the write route, because the route is not the only writer: the seeder, the future generation
 * flows and the Anki consumer all save records directly. A record saved with revision zero is
 * invisible to every `revision > cursor` pull, permanently and silently.
 */
function allocateRevision(app, ownerId) {
  const sequence = sequenceRecord(app, ownerId);
  const next = sequence.getInt("sequence") + 1;
  sequence.set("sequence", next);
  app.save(sequence);
  return next;
}

function requireOwner(event) {
  if (!event.auth || event.auth.collection().name !== "users") {
    throw apiError(401, "unauthenticated", "Sign in to continue.");
  }
  return event.auth.id;
}

function requireSchemaVersion(request) {
  if (Number(request.schemaVersion) !== SCHEMA_VERSION) {
    throw apiError(409, "schema_version_mismatch",
      "This copy of Acervo is out of date and cannot synchronise. Update the app to continue.");
  }
}

function requireDeviceId(value) {
  const device = trimmed(value);
  if (!/^[a-z0-9]{1,32}$/.test(device)) throw apiError(400, "invalid_input", "A valid device identifier is required.");
  return device;
}

function requireInstant(value, label) {
  const instant = trimmed(value);
  if (!INSTANT.test(instant)) {
    throw apiError(400, "invalid_input", label + " must be an ISO-8601 UTC timestamp with milliseconds.");
  }
  return instant;
}

/** The record this owner holds under `id`, or null. An id held by somebody else is a hard stop. */
function ownedOrFree(app, collection, ownerId, id) {
  const owned = firstRecord(app, collection, "id = {:id} && owner = {:owner}", { id: id, owner: ownerId });
  if (owned) return owned;
  const foreign = firstRecord(app, collection, "id = {:id}", { id: id });
  if (foreign) throw apiError(400, "id_conflict", "That record identifier is already in use.");
  return null;
}

/**
 * Applies one client record. The whole batch is refused if anything here throws: a save is one
 * article, and half an article is worse than none.
 */
function mergeRecord(app, entry, ownerId, device, value) {
  const id = trimmed(value.id);
  if (!RECORD_ID.test(id)) throw apiError(400, "invalid_input", "Record ids must be 15 lowercase letters or digits.");
  const stored = ownedOrFree(app, entry.name, ownerId, id);
  const claimed = Number(value.revision) || 0;
  if (stored) {
    if (claimed !== stored.getInt("revision")) {
      throw apiError(409, "stale_record",
        "This entry was changed somewhere else. Refresh to see the current version, then try again.");
    }
  } else if (claimed !== 0) {
    // The client believes it is editing a record this database has never held. Nothing is ever
    // hard-deleted, so this means its cursor belongs to a different database.
    throw apiError(409, "stale_record", "This entry no longer exists on the server. Refresh and try again.");
  }
  const record = stored || new Record(app.findCollectionByNameOrId(entry.name));
  if (!stored) {
    record.set("id", id);
    record.set("owner", ownerId);
    record.set("created_at", requireInstant(value.createdAt, "Creation timestamp"));
  }
  entry.assign(record, value);
  record.set("deleted", value.deleted === true);
  record.set("edited_at", requireInstant(value.editedAt, "Change timestamp"));
  record.set("edited_by", device);
  try {
    app.save(record);
  } catch (error) {
    // The record validation hook rejects malformed records by throwing. That is the caller's
    // mistake, not the server's, and it must abort the whole batch: half an article is worse
    // than none. Rolling back is what `runInTransaction` does with anything thrown here.
    if (error.acervoStatus) throw error;
    throw apiError(400, "invalid_record", entry.key + " " + id + ": " + String(error.message || error));
  }
  // Re-read inside the transaction: the revision was allocated by the save hook, and the response
  // is what the client stores as the precondition for its next edit of this record.
  return app.findRecordById(entry.name, id);
}

/** Applies a change set in graph order, so a record's relations always resolve before it lands. */
function mergeGraph(app, ownerId, device, changes) {
  const written = {};
  COLLECTIONS.forEach((entry) => {
    const incoming = Array.isArray(changes[entry.key]) ? changes[entry.key] : [];
    written[entry.key] = incoming.map((value) => projected(mergeRecord(app, entry, ownerId, device, value), entry.project));
  });
  return written;
}

/** Tombstones everything this owner still holds. Rows are never removed; a reset stays undoable. */
function tombstoneAll(app, ownerId, device) {
  const at = new Date().toISOString();
  let count = 0;
  COLLECTIONS.slice().reverse().forEach((entry) => {
    app.findRecordsByFilter(entry.name, "owner = {:owner}", "", 0, 0, { owner: ownerId })
      .forEach((record) => {
        if (record.getBool("deleted")) return;
        record.set("deleted", true);
        record.set("edited_at", at);
        record.set("edited_by", device);
        app.save(record);
        count += 1;
      });
  });
  return count;
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
        schemaVersion: SCHEMA_VERSION,
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
    if (method === "GET" && relative === "/graph") {
      const ownerId = requireOwner(event);
      const parameters = query(event);
      requireSchemaVersion(parameters);
      const since = Math.max(0, Math.round(Number(parameters.since) || 0));
      let result;
      event.app.runInTransaction((tx) => {
        const sequence = sequenceRecord(tx, ownerId);
        result = {
          schemaVersion: SCHEMA_VERSION,
          datasetId: sequence.id,
          cursor: sequence.getInt("sequence"),
          serverTime: new Date().toISOString(),
          changes: ownerGraph(tx, ownerId, since),
        };
      });
      return respond(event, result);
    }
    if (method === "POST" && relative === "/graph") {
      const ownerId = requireOwner(event);
      const request = body(event);
      requireSchemaVersion(request);
      const device = requireDeviceId(request.deviceId);
      let result;
      event.app.runInTransaction((tx) => {
        const records = mergeGraph(tx, ownerId, device, request.changes || {});
        const sequence = sequenceRecord(tx, ownerId);
        result = {
          schemaVersion: SCHEMA_VERSION,
          datasetId: sequence.id,
          cursor: sequence.getInt("sequence"),
          serverTime: new Date().toISOString(),
          records: records,
        };
      });
      return respond(event, result);
    }
    if (method === "POST" && relative === "/graph/reset") {
      const ownerId = requireOwner(event);
      const request = body(event);
      requireSchemaVersion(request);
      const device = requireDeviceId(request.deviceId);
      // Deleting the whole vocabulary is the one genuinely dangerous call in this API. The
      // interface asks for the word to be typed; the token is what stops a stray request.
      if (trimmed(request.confirm) !== "delete-all-vocabulary") {
        throw apiError(400, "confirmation_required", "This request must confirm that all vocabulary is to be deleted.");
      }
      let result;
      event.app.runInTransaction((tx) => {
        const deleted = tombstoneAll(tx, ownerId, device);
        const sequence = sequenceRecord(tx, ownerId);
        result = {
          schemaVersion: SCHEMA_VERSION,
          datasetId: sequence.id,
          cursor: sequence.getInt("sequence"),
          serverTime: new Date().toISOString(),
          deleted: deleted,
        };
      });
      return respond(event, result);
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
  if (collection === "topics") {
    if (!trimmed(record.getString("name"))) invalid("Topic name is required.");
    return;
  }
  if (collection === "lexemes") {
    const language = validLanguage(record.getString("language"), "Lexeme language");
    if (language.toLowerCase().indexOf("zh") === 0 && !trimmed(record.getString("reading"))) {
      invalid("Chinese lexemes require a reading.");
    }
    const topicIds = record.getStringSlice("topics");
    for (let index = 0; index < topicIds.length; index += 1) {
      sameOwner(record, related(app, "topics", topicIds[index], "Topic"), "Lexeme topic");
    }
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
    const videoRef = trimmed(record.getString("video_ref"));
    if (!videoRef && (trimmed(record.getString("video_title")) || Number(record.get("video_start")) > 0)) {
      invalid("An example clip title or start time requires a video reference.");
    }
    const matched = trimmed(record.getString("matched_form"));
    if (matched && record.getString("text").indexOf(matched) < 0) invalid("The matched form must occur in the example text.");
    const matchedTranslation = trimmed(record.getString("matched_translation_form"));
    if (matchedTranslation && translation.indexOf(matchedTranslation) < 0) {
      invalid("The matched translation form must occur in the example translation.");
    }
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
    const imageRef = trimmed(record.getString("image_ref"));
    const imageModelId = trimmed(record.getString("image_model_id"));
    if (Boolean(imageRef) !== Boolean(imageModelId)) {
      invalid("A rendered image and its rendering model must be provided together.");
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

module.exports = { dispatch: dispatch, validateRecord: validateRecord, allocateRevision: allocateRevision };
