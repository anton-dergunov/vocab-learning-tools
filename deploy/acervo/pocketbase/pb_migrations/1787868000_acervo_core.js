migrate((app) => {
  let users;
  try {
    users = app.findCollectionByNameOrId("users");
  } catch (_) {
    users = new Collection({ type: "auth", name: "users" });
  }
  users.listRule = null;
  users.viewRule = null;
  users.createRule = null;
  users.updateRule = null;
  users.deleteRule = null;
  users.manageRule = null;
  users.passwordAuth = { enabled: true };
  app.save(users);

  const locked = {
    listRule: null,
    viewRule: null,
    createRule: null,
    updateRule: null,
    deleteRule: null,
  };
  const syncFields = [
    { type: "bool", name: "deleted" },
    { type: "text", name: "created_at", required: true, min: 24, max: 24 },
    { type: "text", name: "edited_at", required: true, min: 24, max: 24 },
    { type: "text", name: "edited_by", required: true, min: 1, max: 32, pattern: "^[a-z0-9]+$" },
    { type: "number", name: "revision", min: 0, onlyInt: true },
  ];
  const ownerField = () => ({
    type: "relation", name: "owner", required: true, maxSelect: 1,
    collectionId: users.id, cascadeDelete: true,
  });

  const lexemes = new Collection({
    type: "base",
    name: "lexemes",
    ...locked,
    fields: [
      ownerField(),
      { type: "text", name: "language", required: true, min: 2, max: 35, pattern: "^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$" },
      { type: "text", name: "headword", required: true, min: 1, max: 240 },
      { type: "text", name: "lemma", required: true, min: 1, max: 240 },
      { type: "text", name: "reading", max: 240 },
      { type: "select", name: "pos", required: true, maxSelect: 1, values: ["noun", "verb", "adj", "adv", "phrase", "idiom", "expression"] },
      { type: "select", name: "gender", maxSelect: 1, values: ["masculine", "feminine", "common", "neuter"] },
      { type: "select", name: "register", maxSelect: 1, values: ["neutral", "formal", "colloquial", "slang", "vulgar"] },
      { type: "text", name: "dialect", max: 35, pattern: "^(?:[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*)?$" },
      { type: "text", name: "emoji", max: 32 },
      { type: "json", name: "topics" },
      { type: "select", name: "status", required: true, maxSelect: 1, values: ["inbox", "active", "learned", "retired", "suppressed"] },
      { type: "text", name: "short_gloss", max: 500 },
      { type: "json", name: "notes" },
      ...syncFields,
    ],
    indexes: [
      "CREATE INDEX idx_lexemes_owner_revision ON lexemes (owner, revision)",
      "CREATE INDEX idx_lexemes_owner_language_headword ON lexemes (owner, language, headword COLLATE NOCASE)",
    ],
  });
  app.save(lexemes);

  const senses = new Collection({
    type: "base",
    name: "senses",
    ...locked,
    fields: [
      ownerField(),
      { type: "relation", name: "lexeme", required: true, maxSelect: 1, collectionId: lexemes.id, cascadeDelete: true },
      { type: "text", name: "definition", required: true, min: 1, max: 2000 },
      { type: "text", name: "definition_lang", required: true, min: 2, max: 35, pattern: "^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$" },
      { type: "json", name: "glosses" },
      { type: "text", name: "domain", max: 120 },
      { type: "number", name: "sense_order", min: 0, onlyInt: true },
      ...syncFields,
    ],
    indexes: [
      "CREATE INDEX idx_senses_owner_revision ON senses (owner, revision)",
      "CREATE INDEX idx_senses_owner_lexeme_order ON senses (owner, lexeme, sense_order)",
    ],
  });
  app.save(senses);

  const attestations = new Collection({
    type: "base",
    name: "attestations",
    ...locked,
    fields: [
      ownerField(),
      { type: "relation", name: "lexeme", required: true, maxSelect: 1, collectionId: lexemes.id, cascadeDelete: true },
      { type: "text", name: "text", required: true, min: 1, max: 5000 },
      { type: "text", name: "translation", max: 5000 },
      { type: "url", name: "source_url" },
      { type: "text", name: "source_title", max: 500 },
      { type: "select", name: "source_kind", required: true, maxSelect: 1, values: ["web", "book", "conversation", "video", "lesson", "unknown"] },
      { type: "date", name: "captured_at", required: true },
      ...syncFields,
    ],
    indexes: [
      "CREATE INDEX idx_attestations_owner_revision ON attestations (owner, revision)",
      "CREATE INDEX idx_attestations_owner_lexeme ON attestations (owner, lexeme)",
    ],
  });
  app.save(attestations);

  const examples = new Collection({
    type: "base",
    name: "examples",
    ...locked,
    fields: [
      ownerField(),
      { type: "relation", name: "sense", required: true, maxSelect: 1, collectionId: senses.id, cascadeDelete: true },
      { type: "text", name: "text", required: true, min: 1, max: 5000 },
      { type: "text", name: "text_lang", required: true, min: 2, max: 35, pattern: "^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$" },
      { type: "text", name: "translation", max: 5000 },
      { type: "text", name: "translation_lang", max: 35, pattern: "^(?:[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*)?$" },
      { type: "select", name: "origin", required: true, maxSelect: 1, values: ["attestation", "llm", "tatoeba", "subtitle", "wiktionary", "manual"] },
      { type: "relation", name: "source_attestation", maxSelect: 1, collectionId: attestations.id, cascadeDelete: false },
      { type: "text", name: "model_id", max: 240 },
      { type: "text", name: "video_ref", max: 500 },
      { type: "text", name: "image_ref", max: 500 },
      { type: "text", name: "audio_ref", max: 500 },
      { type: "text", name: "note", max: 2000 },
      { type: "bool", name: "approved" },
      ...syncFields,
    ],
    indexes: [
      "CREATE INDEX idx_examples_owner_revision ON examples (owner, revision)",
      "CREATE INDEX idx_examples_owner_sense ON examples (owner, sense)",
      "CREATE INDEX idx_examples_owner_attestation ON examples (owner, source_attestation)",
    ],
  });
  app.save(examples);

  const imagePrompts = new Collection({
    type: "base",
    name: "image_prompts",
    ...locked,
    fields: [
      ownerField(),
      { type: "relation", name: "lexeme", required: true, maxSelect: 1, collectionId: lexemes.id, cascadeDelete: true },
      { type: "relation", name: "sense", maxSelect: 1, collectionId: senses.id, cascadeDelete: true },
      { type: "text", name: "prompt", required: true, min: 1, max: 10000 },
      { type: "text", name: "style_id", required: true, min: 1, max: 120 },
      { type: "number", name: "seed", min: 0, max: 2147483647, onlyInt: true },
      { type: "text", name: "model_id", required: true, min: 1, max: 240 },
      { type: "text", name: "prompt_version", required: true, min: 1, max: 128 },
      ...syncFields,
    ],
    indexes: [
      "CREATE INDEX idx_image_prompts_owner_revision ON image_prompts (owner, revision)",
      "CREATE INDEX idx_image_prompts_owner_lexeme ON image_prompts (owner, lexeme)",
      "CREATE INDEX idx_image_prompts_owner_sense ON image_prompts (owner, sense)",
    ],
  });
  app.save(imagePrompts);

  const studyStates = new Collection({
    type: "base",
    name: "study_states",
    ...locked,
    fields: [
      ownerField(),
      { type: "relation", name: "lexeme", required: true, maxSelect: 1, collectionId: lexemes.id, cascadeDelete: true },
      { type: "text", name: "system", required: true, min: 1, max: 80 },
      { type: "number", name: "note_id", min: 0, onlyInt: true },
      { type: "json", name: "card_ids" },
      { type: "number", name: "reps", min: 0, onlyInt: true },
      { type: "number", name: "lapses", min: 0, onlyInt: true },
      { type: "number", name: "stability", min: 0 },
      { type: "number", name: "difficulty", min: 0 },
      { type: "number", name: "retrievability", min: 0, max: 1 },
      { type: "date", name: "last_review" },
      { type: "date", name: "synced_at" },
      ...syncFields,
    ],
    indexes: [
      "CREATE INDEX idx_study_states_owner_revision ON study_states (owner, revision)",
      "CREATE INDEX idx_study_states_owner_lexeme_system ON study_states (owner, lexeme, system)",
    ],
  });
  app.save(studyStates);
}, (app) => {
  ["study_states", "image_prompts", "examples", "attestations", "senses", "lexemes"].forEach((name) => {
    try { app.delete(app.findCollectionByNameOrId(name)); } catch (_) { /* already absent */ }
  });
});
