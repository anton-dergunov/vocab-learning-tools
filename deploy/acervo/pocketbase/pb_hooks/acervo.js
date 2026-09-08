const API_ROOT = "/api/acervo/v1";
const SCHEMA_VERSION = 6;
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
  // An unhandled exception must not leak its internals, but an error this file raised deliberately
  // carries a message written for the owner — including the ones that say what to do about it.
  const message = status < 500 || error.acervoCode
    ? String(error.message || error)
    : "The Acervo server could not complete the request.";
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
    key: "vocabularies", name: "vocabularies",
    project: (record) => ({
      language: record.getString("language"),
      definitionLang: record.getString("definition_lang"),
      glossLangs: jsonValue(record.get("gloss_langs")) || [],
      notesLang: record.getString("notes_lang"),
      displayName: textOrNull(record, "display_name"),
      flag: textOrNull(record, "flag"),
      order: Number(record.get("vocab_order")) || 0,
    }),
    assign: (record, value) => {
      setText(record, "language", value.language);
      setText(record, "definition_lang", value.definitionLang);
      setList(record, "gloss_langs", value.glossLangs);
      setText(record, "notes_lang", value.notesLang);
      setText(record, "display_name", value.displayName);
      setText(record, "flag", value.flag);
      setNumber(record, "vocab_order", value.order);
    },
  },
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

/**
 * A schema change is deployed by rewriting the bootstrap migration, and PocketBase records applied
 * migrations by filename — so a database that predates the rewrite silently lacks the collection.
 * Every graph route then failed with an anonymous 500 that the client reported as "offline", which
 * is a long way from "this database must be rebuilt". Say which it is.
 */
function requireCollection(app, name) {
  try { return app.findCollectionByNameOrId(name); }
  catch (_) {
    throw apiError(500, "schema_missing",
      "The Acervo database is missing the '" + name + "' collection, so it predates this server's "
      + "schema. Redeploy with --reset-pocketbase to rebuild it.");
  }
}

function sequenceRecord(app, ownerId) {
  const existing = firstRecord(app, "sync_state", "owner = {:owner}", { owner: ownerId });
  if (existing) return existing;
  const record = new Record(requireCollection(app, "sync_state"));
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

/** Tombstones every word and its descendants, while retaining language and topic configuration. */
function tombstoneAllWords(app, ownerId, device) {
  const at = new Date().toISOString();
  let count = 0;
  COLLECTIONS.slice(2).reverse().forEach((entry) => {
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

/* ── capture ────────────────────────────────────────────────────────────
   One ingest endpoint, several thin transports (§05). Everything intelligent lives here, so a
   transport is a single authenticated POST: an iOS Shortcut, an Android share target or the
   Obsidian ingest script all submit text and get back either an entry or a reason there is none.

   Two model calls, deliberately. The first decides what the text is *about* — which word, which
   language, which of the sentences are the learner's — and that answer is what makes the duplicate
   check and the file walk possible at all. Only then is an article worth generating. */

const LLM_TIMEOUT_SECONDS = 120;
const ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789";
const PROMPT_CACHE = {};

/**
 * What this server is configured to build entries with, and — when it cannot — why.
 *
 * `reason` exists because a bare "capture is unavailable" is what let a real outage stay invisible:
 * false could equally mean no key, the wrong key name, a missing Vertex project or an unknown
 * provider, and nobody could tell which without shell access to the server. It names the first
 * unmet requirement as an environment variable, and deliberately never carries a value — health
 * serves it unauthenticated.
 */
function llmSettings() {
  const provider = trimmed($os.getenv("ACERVO_LLM_PROVIDER")) || "gemini";
  const key = provider === "vertex"
    ? trimmed($os.getenv("VERTEX_API_KEY"))
    : trimmed($os.getenv("GEMINI_API_KEY"));
  const project = trimmed($os.getenv("ACERVO_VERTEX_PROJECT"));
  return {
    provider: provider,
    key: key,
    model: trimmed($os.getenv("ACERVO_LLM_MODEL")) || "gemini-3.1-flash-lite",
    // Kept as a test seam for the disposable real-PocketBase integration server. Vertex always
    // uses Google's full project/location endpoint and cannot be redirected.
    geminiEndpoint: trimmed($os.getenv("ACERVO_LLM_ENDPOINT")) || "https://generativelanguage.googleapis.com",
    project: project,
    location: trimmed($os.getenv("ACERVO_VERTEX_LOCATION")) || "global",
    reason: llmReason(provider, key, project),
  };
}

/**
 * The first unmet requirement, or null when the configuration can work.
 *
 * `llmJson` re-checks these same three conditions rather than reading this, and that is deliberate:
 * each one raises a *different* error code there, and `scripts/ingest_vocabulary_file.py` retries
 * on exactly three codes. This is the reporting view of those facts, not a second gate.
 *
 * `ACERVO_VERTEX_LOCATION` can never be the reason: it defaults to `global`.
 */
function llmReason(provider, key, project) {
  if (provider !== "gemini" && provider !== "vertex") {
    return "ACERVO_LLM_PROVIDER is not one of gemini, vertex";
  }
  if (!key) return provider === "vertex" ? "VERTEX_API_KEY is not set" : "GEMINI_API_KEY is not set";
  if (provider === "vertex" && !project) return "ACERVO_VERTEX_PROJECT is not set";
  return null;
}

/** What health says about capture. Never a key, an endpoint or a project id. */
function captureHealth() {
  const settings = llmSettings();
  return {
    available: settings.reason === null,
    provider: settings.provider,
    model: settings.model,
    reason: settings.reason,
  };
}

/** 15 lowercase alphanumerics, the one id format §03 allows, minted the same way everywhere. */
function newRecordId() {
  let id = "";
  try {
    id = trimmed($security.randomStringWithAlphabet(15, ID_ALPHABET));
  } catch (_) {
    id = "";
  }
  if (!RECORD_ID.test(id)) {
    // Fall back to the general random string, folded into the alphabet ids are allowed to use.
    const source = String($security.randomString(40)).toLowerCase().replace(/[^a-z0-9]/g, "");
    id = source.slice(0, 15);
  }
  if (!RECORD_ID.test(id)) throw apiError(500, "id_generation_failed", "The Acervo server could not mint a record identifier.");
  return id;
}

function promptText(name) {
  if (PROMPT_CACHE[name]) return PROMPT_CACHE[name];
  const directory = trimmed($os.getenv("ACERVO_PROMPTS_PATH")) || "/pb/pb_hooks/prompts";
  let text;
  try {
    text = trimmed(toString($os.readFile(directory + "/" + name + ".txt")));
  } catch (_) {
    text = "";
  }
  if (!text) {
    throw apiError(500, "prompt_missing",
      "The Acervo server is missing its '" + name + "' prompt, so it cannot build entries.");
  }
  PROMPT_CACHE[name] = text;
  return text;
}

/** Models wrap JSON in ``` often enough that not handling it would be the top cause of failure. */
function unfenced(text) {
  const value = trimmed(text);
  const fenced = value.match(/^```[a-zA-Z]*\s*\n([\s\S]*?)\n?```$/);
  return fenced ? trimmed(fenced[1]) : value;
}

function llmJson(system, user) {
  const settings = llmSettings();
  if (settings.provider !== "gemini" && settings.provider !== "vertex") {
    throw apiError(503, "llm_configuration",
      "This Acervo server has an invalid language model provider configured, so it cannot build entries.");
  }
  if (!settings.key) {
    throw apiError(503, "capture_unavailable",
      "This Acervo server has no language model configured, so it cannot build entries.");
  }
  if (settings.provider === "vertex" && (!settings.project || !settings.location)) {
    throw apiError(503, "llm_configuration",
      "This Acervo server is missing its Vertex project or location, so it cannot build entries.");
  }
  const vertex = settings.provider === "vertex";
  const url = vertex
    ? "https://aiplatform.googleapis.com/v1/projects/" + encodeURIComponent(settings.project)
      + "/locations/" + encodeURIComponent(settings.location)
      + "/publishers/google/models/" + encodeURIComponent(settings.model) + ":generateContent"
    : settings.geminiEndpoint.replace(/\/+$/, "") + "/v1beta/models/"
      + encodeURIComponent(settings.model) + ":generateContent";
  const generationConfig = { responseMimeType: "application/json" };
  if (vertex) generationConfig.thinkingConfig = { thinkingLevel: "MEDIUM" };
  else generationConfig.temperature = 0.2;
  let response;
  try {
    response = $http.send({
      url: url,
      method: "POST",
      headers: { "content-type": "application/json", "x-goog-api-key": settings.key },
      body: JSON.stringify({
        systemInstruction: { parts: [{ text: system }] },
        contents: [{ role: "user", parts: [{ text: user }] }],
        generationConfig: generationConfig,
      }),
      timeout: LLM_TIMEOUT_SECONDS,
    });
  } catch (error) {
    throw apiError(502, "llm_unreachable", "The language model could not be reached, so nothing was created.");
  }
  if (response.statusCode < 200 || response.statusCode >= 300) {
    if (response.statusCode === 401 || response.statusCode === 403) {
      throw apiError(503, "llm_authentication",
        "The language model credential was rejected, so nothing was created.");
    }
    if (response.statusCode === 400 || response.statusCode === 404) {
      throw apiError(503, "llm_configuration",
        "The language model configuration was rejected, so nothing was created.");
    }
    if (response.statusCode === 429) {
      throw apiError(503, "llm_rate_limited",
        "The language model is temporarily rate limited, so nothing was created.");
    }
    if (response.statusCode >= 500) {
      throw apiError(503, "llm_unavailable",
        "The language model is temporarily unavailable, so nothing was created.");
    }
    throw apiError(502, "llm_failed", "The language model refused the request, so nothing was created.");
  }
  const payload = response.json || jsonValue(response.body);
  const candidate = payload && payload.candidates && payload.candidates[0];
  const parts = candidate && candidate.content && candidate.content.parts;
  let text = "";
  if (Array.isArray(parts)) {
    for (let index = 0; index < parts.length; index += 1) {
      if (!parts[index].thought && trimmed(parts[index].text)) {
        text = String(parts[index].text);
        break;
      }
    }
  }
  if (!trimmed(text)) throw apiError(502, "llm_empty", "The language model returned nothing, so nothing was created.");
  try {
    return JSON.parse(unfenced(text));
  } catch (_) {
    throw apiError(502, "llm_unusable", "The language model did not return a usable answer, so nothing was created.");
  }
}

/* ── reading the model's answer ─────────────────────────────────────────
   Everything below treats the response as untrusted input. A model that mislabels a part of speech
   or marks a form that is not in its own sentence would otherwise fail record validation, and the
   whole capture would surface to the owner as an anonymous refusal. Coerce what can be coerced,
   drop what cannot, and never let a bad field abort an otherwise good entry. */

function pickChoice(value, allowed, fallback) {
  const text = trimmed(value).toLowerCase();
  for (let index = 0; index < allowed.length; index += 1) {
    if (allowed[index] === text) return allowed[index];
  }
  return fallback;
}

function pickOptionalChoice(value, allowed) {
  return pickChoice(value, allowed, null);
}

function textList(value) {
  if (!Array.isArray(value)) return [];
  const kept = [];
  value.forEach((item) => {
    const text = trimmed(item);
    if (text && kept.indexOf(text) < 0) kept.push(text);
  });
  return kept;
}

function languageOrNull(value) {
  const text = trimmed(value);
  return LANGUAGE.test(text) ? text : null;
}

const POS_VALUES = ["noun", "verb", "adj", "adv", "phrase", "idiom", "expression"];
const GENDER_VALUES = ["masculine", "feminine", "common", "neuter"];
const REGISTER_VALUES = ["neutral", "formal", "colloquial", "slang", "vulgar"];
const SOURCE_KIND_VALUES = ["web", "book", "conversation", "video", "lesson", "unknown"];

function ownerVocabularies(app, ownerId) {
  return app.findRecordsByFilter("vocabularies", "owner = {:owner} && deleted = false", "vocab_order", 0, 0, { owner: ownerId })
    .map((record) => ({
      language: record.getString("language"),
      definitionLang: record.getString("definition_lang"),
      glossLangs: jsonValue(record.get("gloss_langs")) || [],
      notesLang: record.getString("notes_lang"),
      displayName: textOrNull(record, "display_name"),
    }));
}

function ownerTopics(app, ownerId) {
  return app.findRecordsByFilter("topics", "owner = {:owner} && deleted = false", "topic_order", 0, 0, { owner: ownerId })
    .map((record) => ({ id: record.id, name: record.getString("name") }));
}

/** Case-insensitive, because the learner types `picar` and the store holds `Picar` just as often. */
function duplicateLexemes(app, ownerId, language, headword, lemma) {
  const found = {};
  const matches = [];
  [headword, lemma].forEach((form) => {
    const needle = trimmed(form).toLowerCase();
    if (!needle) return;
    app.findRecordsByFilter(
      "lexemes",
      "owner = {:owner} && language = {:language} && deleted = false && (headword ~ {:form} || lemma ~ {:form})",
      "", 0, 0, { owner: ownerId, language: language, form: needle }
    ).forEach((record) => {
      if (found[record.id]) return;
      if (record.getString("headword").toLowerCase() !== needle && record.getString("lemma").toLowerCase() !== needle) return;
      found[record.id] = true;
      matches.push({
        id: record.id,
        headword: record.getString("headword"),
        shortGloss: textOrNull(record, "short_gloss"),
      });
    });
  });
  return matches;
}

/**
 * An external dictionary's entry for the word, when the caller sent one.
 *
 * Grounding, and nothing else. It never reaches `resolution.sentences`, so it can never become an
 * attestation: an attestation is a sentence the owner met, and a dictionary's own examples are not
 * that. Provenance is modelled here, never flagged, and the modelling is this separation.
 */
const REFERENCE_LIMIT = 8000;

function referenceOf(request) {
  const text = trimmed(request.reference);
  if (!text) return null;
  const mode = trimmed(request.referenceMode);
  return {
    text: text.length > REFERENCE_LIMIT ? text.slice(0, REFERENCE_LIMIT) : text,
    mode: mode === "faithful" || mode === "expand" ? mode : null,
  };
}

function resolveCapture(app, ownerId, request) {
  const stream = trimmed(request.mode) === "stream";
  const reference = referenceOf(request);
  const vocabularies = ownerVocabularies(app, ownerId);
  const known = vocabularies.map((entry) => entry.language + (entry.displayName ? " (" + entry.displayName + ")" : ""));
  const lines = String(request.text).split("\n");
  const user = [
    "Mode: " + (stream ? "stream" : "single"),
    "Languages this learner studies: " + (known.length ? known.join(", ") : "none configured yet"),
    trimmed(request.language) ? "The caller believes this is " + trimmed(request.language) + "; verify it." : "",
    trimmed(request.headword) ? "The learner says the word is: " + trimmed(request.headword) : "",
    reference ? "\nReference (an external dictionary's entry for this word — CONTEXT ONLY. Do not\n"
      + "take any sentence from it as one the learner supplied):\n```\n" + reference.text + "\n```" : "",
    "",
    "Input (" + lines.length + " lines):",
    "```",
    String(request.text),
    "```",
  ].filter((line) => line !== "").join("\n");

  const answer = llmJson(promptText("acervo_resolve"), user);
  if (answer && trimmed(answer.error)) {
    throw apiError(422, "unreadable_input",
      "That text could not be read as a word to learn, so nothing was created.");
  }
  const language = languageOrNull(answer && answer.language);
  const headword = trimmed(answer && answer.headword);
  if (!language || !headword) {
    throw apiError(422, "unreadable_input",
      "That text could not be read as a word to learn, so nothing was created.");
  }
  const consumed = Math.round(Number(answer.consumedLines) || 0);
  const sentences = [];
  if (Array.isArray(answer.sentences)) {
    answer.sentences.forEach((item) => {
      const text = trimmed(item && item.text);
      if (!text) return;
      sentences.push({ text: text, translation: trimmed(item.translation) || null });
    });
  }
  const consumedLines = stream ? Math.max(1, Math.min(consumed || 1, lines.length)) : lines.length;
  const consumedText = trimmed(answer.consumedText);
  if (stream && consumedText !== trimmed(lines.slice(0, consumedLines).join("\n"))) {
    throw apiError(502, "stream_boundary_mismatch",
      "The language model returned an unsafe stream boundary, so nothing was created.");
  }
  return {
    language: language,
    headword: headword,
    lemma: trimmed(answer.lemma) || headword,
    pos: pickChoice(answer.pos, POS_VALUES, "noun"),
    sentences: sentences,
    note: trimmed(answer.note) || null,
    // At least one line, always: a walk that consumes nothing loops on the same block forever.
    consumedLines: consumedLines,
    consumedText: consumedText || null,
  };
}

function composeArticle(app, ownerId, resolution, request, vocabulary, topics) {
  const reference = referenceOf(request);
  const names = {};
  topics.forEach((topic) => { names[topic.name.toLowerCase()] = topic.name; });
  const preferred = textList(request.topics).map((name) => names[name.toLowerCase()]).filter((name) => Boolean(name));
  const user = [
    "Language: " + resolution.language,
    "Headword: " + resolution.headword,
    "Lemma: " + resolution.lemma,
    "Part of speech: " + resolution.pos,
    "Define senses in: " + vocabulary.definitionLang,
    "Gloss into: " + vocabulary.glossLangs.join(", "),
    "Write notes in: " + (vocabulary.notesLang || vocabulary.glossLangs[0]),
    "Topics to choose from: " + (topics.length ? topics.map((topic) => topic.name).join(" | ") : "(none — return an empty list)"),
    // A file of notes already filed under one heading knows its own topic better than the model
    // can infer it from a single word, so say so — as a preference, not an instruction.
    preferred.length ? "The learner already files these under: " + preferred.join(", ") + ". Prefer that unless it is plainly wrong." : "",
    "",
    "Sentences the learner supplied (index them from 0 for `fromSentence`):",
    resolution.sentences.length
      ? resolution.sentences.map((item, index) =>
          index + ": " + item.text + (item.translation ? "  —  " + item.translation : "")).join("\n")
      : "(none)",
    trimmed(request.note) ? "\nThe learner asks specifically: " + trimmed(request.note) : "",
    reference ? "\nReference entry from an external dictionary, which the learner was reading when\n"
      + "they asked for this. Ground the article on it. Its example sentences are the dictionary's,\n"
      + "NOT sentences the learner supplied:\n```\n" + reference.text + "\n```" : "",
    reference && reference.mode === "faithful"
      ? "\nTreatment: STAY CLOSE TO THE REFERENCE. Carry over its senses and no others, in its\n"
        + "order. Translate and tidy; do not add senses, examples or notes it does not have." : "",
    reference && reference.mode === "expand"
      ? "\nTreatment: FILL IN THE GAPS. Keep what the reference says right, condense it to the three\n"
        + "to five senses worth reading, and add what it lacks — glosses, an example where the word\n"
        + "needs one, a note on usage, an emoji." : "",
  ].filter((line) => line !== "").join("\n");

  const answer = llmJson(promptText("acervo_compose"), user);
  if (!answer || typeof answer !== "object") {
    throw apiError(502, "llm_unusable", "The language model did not return an entry, so nothing was created.");
  }
  return answer;
}

/**
 * Turns the model's answer into an ArticleDraft — the exact shape `web/src/yaml.ts` reads, so the
 * review surface renders a generated entry through the same serialiser as a stored one.
 *
 * Ids are minted here rather than left absent, because an example has to name the attestation it
 * was drawn from and both are created by the same save.
 */
function draftFrom(answer, resolution, request, vocabulary, topics, modelId) {
  const capturedAt = new Date().toISOString();
  const topicNames = {};
  topics.forEach((topic) => { topicNames[topic.name.toLowerCase()] = topic.name; });

  const sourceUrl = trimmed(request.sourceUrl) || null;
  const attestations = resolution.sentences.map((sentence) => ({
    id: newRecordId(),
    text: sentence.text,
    translation: sentence.translation,
    sourceUrl: sourceUrl,
    sourceTitle: trimmed(request.sourceTitle) || null,
    sourceKind: pickChoice(request.sourceKind, SOURCE_KIND_VALUES, sourceUrl ? "web" : "unknown"),
    capturedAt: capturedAt,
  }));

  const glossLangs = vocabulary.glossLangs;
  const senses = [];
  const rawSenses = Array.isArray(answer.senses) ? answer.senses : [];
  rawSenses.forEach((raw, index) => {
    const definition = trimmed(raw && raw.definition);
    if (!definition) return;
    const glosses = [];
    const seenLangs = {};
    (Array.isArray(raw.glosses) ? raw.glosses : []).forEach((gloss) => {
      const lang = languageOrNull(gloss && gloss.lang);
      const terms = textList(gloss && gloss.terms);
      if (!lang || !terms.length || seenLangs[lang]) return;
      seenLangs[lang] = true;
      glosses.push({ lang: lang, terms: terms });
    });
    // A sense without a gloss is refused by the record validator, so rather than lose the sense,
    // fall back to the headword in the language the learner asked to be glossed into.
    if (!glosses.length) glosses.push({ lang: glossLangs[0] || "en", terms: [resolution.headword] });

    const examples = [];
    (Array.isArray(raw.examples) ? raw.examples : []).forEach((example) => {
      const text = trimmed(example && example.text);
      if (!text) return;
      const translation = trimmed(example.translation) || null;
      // `Number(null)` is 0, so a plain `Number()` here would read "I invented this" as "this is
      // sentence 0" and quietly credit the learner with every example the model wrote.
      const claimed = example.fromSentence;
      const fromSentence = claimed === null || claimed === undefined || claimed === "" ? -1 : Number(claimed);
      const attestation = Number.isInteger(fromSentence) && fromSentence >= 0 && attestations[fromSentence]
        ? attestations[fromSentence] : null;
      const matchedForm = trimmed(example.matchedForm) || null;
      const matchedTranslationForm = trimmed(example.matchedTranslationForm) || null;
      examples.push({
        id: newRecordId(),
        text: text,
        textLang: resolution.language,
        translation: translation,
        translationLang: translation ? (glossLangs[0] || "en") : null,
        // What makes an example the learner's own rather than the model's, and what §12's Obsidian
        // export reads to mark it as such. A generated one carries the model that wrote it instead.
        origin: attestation ? "attestation" : "llm",
        sourceAttestationId: attestation ? attestation.id : null,
        modelId: attestation ? null : modelId,
        videoRef: null,
        videoTitle: null,
        videoStart: null,
        imageRef: null,
        audioRef: null,
        note: trimmed(example.note) || null,
        // The validator requires these to occur verbatim in the text they mark. A model that
        // retypes an inflected form instead of copying it would otherwise refuse the whole batch.
        matchedForm: matchedForm && text.indexOf(matchedForm) >= 0 ? matchedForm : null,
        matchedTranslationForm:
          matchedTranslationForm && translation && translation.indexOf(matchedTranslationForm) >= 0
            ? matchedTranslationForm : null,
        approved: false,
      });
    });

    senses.push({
      id: newRecordId(),
      order: index,
      definition: definition,
      definitionLang: languageOrNull(raw.definitionLang) || vocabulary.definitionLang,
      glosses: glosses,
      domain: trimmed(raw.domain) || null,
      examples: examples,
      images: [],
    });
  });

  if (!senses.length) {
    throw apiError(502, "llm_unusable", "The language model returned an entry with no meanings, so nothing was created.");
  }

  const reading = trimmed(answer.reading) || null;
  // Chinese records are refused without a reading (§03). Saying which field is missing beats
  // letting the save fail later with a validation message about a field nobody was shown.
  if (resolution.language.toLowerCase().indexOf("zh") === 0 && !reading) {
    throw apiError(502, "llm_unusable",
      "The language model returned a Chinese entry with no reading, so nothing was created.");
  }
  return {
    id: null,
    language: resolution.language,
    headword: trimmed(answer.headword) || resolution.headword,
    lemma: trimmed(answer.lemma) || resolution.lemma,
    reading: reading,
    ipa: trimmed(answer.ipa) || null,
    pos: pickChoice(answer.pos, POS_VALUES, resolution.pos),
    gender: pickOptionalChoice(answer.gender, GENDER_VALUES),
    register: pickOptionalChoice(answer.register, REGISTER_VALUES),
    dialect: languageOrNull(answer.dialect),
    emoji: trimmed(answer.emoji).slice(0, 32) || null,
    // Only topics this owner actually holds. `saveArticle` refuses an unknown name, and inventing
    // one here would turn a good entry into an error the learner has to decode.
    topics: textList(answer.topics)
      .map((name) => topicNames[name.toLowerCase()])
      .filter((name) => Boolean(name)),
    status: "inbox",
    shortGloss: trimmed(answer.shortGloss) || null,
    notes: textList(answer.notes),
    senses: senses,
    attestations: attestations,
    images: [],
  };
}

/** The draft as a change set, for the transports that have no replica to diff against. */
function applyDraft(app, ownerId, device, draft, topics) {
  const at = new Date().toISOString();
  const stamp = { deleted: false, createdAt: at, editedAt: at, editedBy: device, revision: 0 };
  const topicIds = {};
  topics.forEach((topic) => { topicIds[topic.name.toLowerCase()] = topic.id; });
  const lexemeId = newRecordId();

  const changes = { topics: [], lexemes: [], senses: [], attestations: [], examples: [], imagePrompts: [], studyStates: [] };
  changes.lexemes.push(Object.assign({
    id: lexemeId,
    language: draft.language,
    headword: draft.headword,
    lemma: draft.lemma,
    reading: draft.reading,
    ipa: draft.ipa,
    pos: draft.pos,
    gender: draft.gender,
    register: draft.register,
    dialect: draft.dialect,
    emoji: draft.emoji,
    topicIds: draft.topics.map((name) => topicIds[name.toLowerCase()]).filter((id) => Boolean(id)),
    status: draft.status,
    shortGloss: draft.shortGloss,
    notes: draft.notes,
  }, stamp));

  draft.attestations.forEach((attestation) => {
    changes.attestations.push(Object.assign({
      id: attestation.id,
      lexemeId: lexemeId,
      text: attestation.text,
      translation: attestation.translation,
      sourceUrl: attestation.sourceUrl,
      sourceTitle: attestation.sourceTitle,
      sourceKind: attestation.sourceKind,
      capturedAt: attestation.capturedAt,
    }, stamp));
  });

  draft.senses.forEach((sense) => {
    changes.senses.push(Object.assign({
      id: sense.id,
      lexemeId: lexemeId,
      definition: sense.definition,
      definitionLang: sense.definitionLang,
      glosses: sense.glosses,
      domain: sense.domain,
      order: sense.order,
    }, stamp));
    sense.examples.forEach((example) => {
      changes.examples.push(Object.assign({}, example, { senseId: sense.id }, stamp));
    });
  });

  // The same route every other writer uses: same validation, same revision allocation, same
  // transaction. Nothing about capture gets a private way into the store.
  mergeGraph(app, ownerId, device, changes);
  return lexemeId;
}

function captureRoute(event) {
  const ownerId = requireOwner(event);
  const request = body(event);
  requireSchemaVersion(request);
  const device = requireDeviceId(request.deviceId);
  const text = String(request.text == null ? "" : request.text);
  if (!trimmed(text)) throw apiError(400, "invalid_input", "There is nothing to capture.");
  if (text.length > 20000) throw apiError(400, "invalid_input", "That capture is too long to process in one request.");

  const resolution = resolveCapture(event.app, ownerId, request);

  const vocabularies = ownerVocabularies(event.app, ownerId);
  let vocabulary = null;
  vocabularies.forEach((entry) => { if (entry.language === resolution.language) vocabulary = entry; });
  if (!vocabulary) {
    // Deliberately before generation: building an article for a language the owner does not keep
    // would spend a model call on something with nowhere to go.
    throw apiError(409, "language_not_configured",
      "This looks like " + resolution.language + ", which you have no vocabulary for yet. "
      + "Add it in Settings, then capture this again.");
  }
  if (!Array.isArray(vocabulary.glossLangs) || !vocabulary.glossLangs.length) {
    throw apiError(409, "language_not_configured",
      "Your " + resolution.language + " vocabulary has no translation language set, so an entry cannot be built. "
      + "Choose one in Settings.");
  }

  const duplicates = duplicateLexemes(event.app, ownerId, resolution.language, resolution.headword, resolution.lemma);
  if (duplicates.length) {
    // Merging a repeat capture into the entry it belongs to is §06's job, and it needs the article
    // conversation to do it well. Until then, say so plainly rather than making a near-duplicate.
    return respond(event, {
      resolution: resolution,
      duplicates: duplicates,
      draft: null,
      applied: null,
    });
  }

  const topics = ownerTopics(event.app, ownerId);
  const modelId = llmSettings().model;
  const answer = composeArticle(event.app, ownerId, resolution, request, vocabulary, topics);
  const draft = draftFrom(answer, resolution, request, vocabulary, topics, modelId);

  let applied = null;
  if (request.apply === true) {
    let lexemeId;
    event.app.runInTransaction((tx) => {
      lexemeId = applyDraft(tx, ownerId, device, draft, topics);
    });
    applied = { lexemeId: lexemeId };
  }
  return respond(event, {
    resolution: resolution,
    duplicates: [],
    draft: draft,
    applied: applied,
  });
}


/* ── external dictionaries ──────────────────────────────────────────────
   Two jobs only. Say which compiled dictionaries this server holds, so the interface can offer
   them; and answer an online lookup on the client's behalf, so §9's User-Agent obligation is
   honoured in one place and the browser never depends on a third party's CORS headers.

   Notably absent: a lookup route for compiled dictionaries. The artifact is served as a static
   file with byte ranges, so "this device, then the server" is the same reader over a different
   byte source, and the format is never implemented twice. */

const DICTIONARY_USER_AGENT = "Acervo/1.0 (self-hosted vocabulary store; +https://acervo.example.com)";
const DICTIONARY_TIMEOUT_SECONDS = 20;

function dictionaryDirectory() {
  return trimmed($os.getenv("ACERVO_DICTIONARIES_PATH")) || "/pb/dictionaries";
}

/** The metadata sidecar of every artifact on disk. A dictionary with no `.json` is a failed build. */
function installedDictionaries() {
  const directory = dictionaryDirectory();
  let names;
  try { names = $os.readDir(directory); }
  catch (_) { return []; }
  const found = [];
  for (const item of names) {
    const name = item.name();
    if (item.isDir() || name.slice(-5) !== ".json") continue;
    try {
      const metadata = JSON.parse(toString($os.readFile(directory + "/" + name)));
      if (metadata && metadata.id) found.push(metadata);
    } catch (_) {
      // A half-written artifact must not take the whole list down with it.
      console.log("Acervo: ignoring unreadable dictionary metadata " + name);
    }
  }
  found.sort((left, right) => (left.id < right.id ? -1 : left.id > right.id ? 1 : 0));
  return found;
}

function fetchJson(url) {
  let response;
  try {
    response = $http.send({
      url: url,
      method: "GET",
      headers: { "User-Agent": DICTIONARY_USER_AGENT, "Accept": "application/json" },
      timeout: DICTIONARY_TIMEOUT_SECONDS,
    });
  } catch (_) {
    throw apiError(502, "dictionary_unreachable", "The dictionary service could not be reached.");
  }
  // A 404 is an answer, not a failure: it means the source genuinely has no entry for the word.
  if (response.statusCode === 404) return null;
  if (response.statusCode >= 400) {
    throw apiError(502, "dictionary_failed",
      "The dictionary service answered with status " + response.statusCode + ".");
  }
  try { return JSON.parse(toString(response.body)); }
  catch (_) { throw apiError(502, "dictionary_unusable", "The dictionary service returned an unreadable answer."); }
}

function plainText(markup) {
  return trimmed(String(markup == null ? "" : markup).replace(/<[^>]*>/g, "").replace(/\s+/g, " "));
}

/**
 * freedictionaryapi.com. Wiktionary-derived but its own field shape: `partOfSpeech`,
 * `pronunciations[].text`, and `senses[].definition` as a *string* where wiktextract has a list.
 * §11.5 withdrew the claim that these share the offline mapper.
 */
function lookupFreeDictionary(word, language) {
  const payload = fetchJson("https://freedictionaryapi.com/api/v1/entries/"
    + encodeURIComponent(language || "en") + "/" + encodeURIComponent(word));
  if (!payload || !payload.entries || !payload.entries.length) return [];
  return payload.entries.map((entry) => {
    const senses = (entry.senses || [])
      .filter((sense) => trimmed(sense.definition))
      .map((sense) => {
        const mapped = { definition: trimmed(sense.definition) };
        const examples = (sense.examples || []).filter((text) => trimmed(text)).slice(0, 3);
        if (examples.length) mapped.examples = examples.map((text) => ({ text: trimmed(text) }));
        return mapped;
      });
    const ipa = (entry.pronunciations || []).filter((sound) => trimmed(sound.text))[0];
    return pruneEntry({
      headword: trimmed(payload.word) || word,
      language: (entry.language && entry.language.code) || language || null,
      posLabel: trimmed(entry.partOfSpeech) || null,
      ipa: ipa ? trimmed(ipa.text) : null,
      senses: senses,
    });
  }).filter((entry) => entry.senses && entry.senses.length);
}

/**
 * The Wikimedia REST definition endpoint. It lives only on en.wiktionary.org — a per-language host
 * 404s on everything — and keys its answer by language *inside* the response. Definitions arrive as
 * HTML fragments carrying mw:WikiLink markup, so mapping means stripping it.
 */
function lookupWikimedia(word, language) {
  const payload = fetchJson("https://en.wiktionary.org/api/rest_v1/page/definition/"
    + encodeURIComponent(word));
  if (!payload) return [];
  const wanted = trimmed(language);
  const codes = wanted && payload[wanted] ? [wanted] : Object.keys(payload);
  const entries = [];
  for (const code of codes) {
    for (const group of payload[code] || []) {
      const senses = (group.definitions || [])
        .map((item) => {
          const definition = plainText(item.definition);
          if (!definition) return null;
          const sense = { definition: definition };
          const examples = (item.parsedExamples || [])
            .map((sample) => ({ text: plainText(sample.example),
                                translation: plainText(sample.translation) || null }))
            .filter((sample) => sample.text)
            .slice(0, 3);
          if (examples.length) sense.examples = examples;
          return sense;
        })
        .filter((sense) => sense);
      if (!senses.length) continue;
      entries.push(pruneEntry({
        headword: word,
        language: code,
        posLabel: trimmed(group.partOfSpeech) || null,
        senses: senses,
      }));
    }
  }
  return entries;
}

/** Drops empties, so an online answer is the same shape the compiler writes into an artifact. */
function pruneEntry(entry) {
  const cleaned = {};
  for (const key of Object.keys(entry)) {
    const value = entry[key];
    if (value === null || value === "" || (Array.isArray(value) && !value.length)) continue;
    cleaned[key] = value;
  }
  return cleaned;
}

const ONLINE_DICTIONARIES = {
  "freedictionaryapi": lookupFreeDictionary,
  "wikimedia-rest": lookupWikimedia,
};

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
        // Whether this server can build entries at all, so the app can say why the button is off
        // rather than failing at the moment someone finally uses it. Provider and model are
        // identifiers the owner chose and needs to see; the key, the endpoint and the Vertex
        // project are deployment details and stay on the server.
        capture: captureHealth(),
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
    if (method === "GET" && relative === "/dictionaries") {
      requireOwner(event);
      return respond(event, { dictionaries: installedDictionaries() });
    }
    if (method === "GET" && relative.indexOf("/dictionaries/online/") === 0) {
      requireOwner(event);
      const source = relative.slice("/dictionaries/online/".length);
      const connector = ONLINE_DICTIONARIES[source];
      if (!connector) throw apiError(404, "not_found", "No such online dictionary.");
      const parameters = query(event);
      const word = trimmed(parameters.word);
      if (!word) throw apiError(400, "word_required", "Ask for a word.");
      return respond(event, {
        source: source,
        word: word,
        entries: connector(word, trimmed(parameters.language)),
      });
    }
    if (method === "POST" && relative === "/capture") return captureRoute(event);
    if (method === "POST" && relative === "/graph/reset") {
      const ownerId = requireOwner(event);
      const request = body(event);
      requireSchemaVersion(request);
      const device = requireDeviceId(request.deviceId);
      // Deleting every word is the one genuinely dangerous call in this API. The
      // interface asks for the word to be typed; the token is what stops a stray request.
      if (trimmed(request.confirm) !== "delete-all-words") {
        throw apiError(400, "confirmation_required", "This request must confirm that all words are to be deleted.");
      }
      let result;
      event.app.runInTransaction((tx) => {
        const deleted = tombstoneAllWords(tx, ownerId, device);
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
  if (collection === "vocabularies") {
    validLanguage(record.getString("language"), "Vocabulary language");
    validLanguage(record.getString("definition_lang"), "Vocabulary definition language");
    const glossLangs = jsonValue(record.get("gloss_langs"));
    stringArray(glossLangs, "Vocabulary gloss languages");
    if (!Array.isArray(glossLangs) || glossLangs.length === 0) invalid("A vocabulary needs at least one gloss language.");
    glossLangs.forEach((code) => validLanguage(code, "Vocabulary gloss language"));
    validLanguage(record.getString("notes_lang"), "Vocabulary notes language");
    return;
  }
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
