"""The ten owner-scoped tables, plus `users`.

Ported column for column and index for index from the PocketBase bootstrap migration this replaces.
Two of those indexes carry reasoning that must survive the move, and both comments are below.

Timestamps are `TEXT` of exactly 24 characters throughout. The migration already stored `created_at`
and `edited_at` that way; `captured_at`, `last_review` and `synced_at` were PocketBase `date` fields
normalised back to the same 24-character form on every read, so storing the wire form directly is
what removes a conversion rather than what adds one.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

metadata = MetaData()

# The eight replicated tables, in graph order: topics before lexemes, lexemes before senses and
# attestations, those before examples and sense-linked image prompts. Applying a batch in this order
# means a relation always resolves, so it is also the merge order the write route uses — and,
# reversed and with the first two dropped, the tombstone order.
REPLICATED = (
    "vocabularies",
    "topics",
    "lexemes",
    "senses",
    "attestations",
    "examples",
    "image_prompts",
    "study_states",
)


def _owner() -> Column:
    return Column("owner", String(15), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


def _sync_fields() -> list[Column]:
    return [
        Column("deleted", Boolean, nullable=False, default=False),
        Column("created_at", String(24), nullable=False),
        Column("edited_at", String(24), nullable=False),
        Column("edited_by", String(32), nullable=False),
        Column("revision", Integer, nullable=False, default=0),
    ]


users = Table(
    "users",
    metadata,
    Column("id", String(15), primary_key=True),
    Column("email", Text, nullable=False),
    Column("password_hash", Text, nullable=False),
    # Mixed into the token signing key, so changing a password invalidates outstanding tokens. The
    # one PocketBase auth behaviour worth reproducing.
    Column("token_key", Text, nullable=False),
    Column("verified", Boolean, nullable=False, default=True),
    Column("created_at", String(24), nullable=False),
    Column("updated_at", String(24), nullable=False),
    # Safe here for the same reason as on `sync_state`: this table is never replicated, so it cannot
    # be the constraint two offline devices independently satisfy.
    Index("idx_users_email", "email", unique=True),
)

# The replication cursor: one strictly increasing sequence per owner, and the record id doubles as
# the dataset identity a client checks its cursor against. Deliberately its own table and never
# replicated — a counter only the server may advance must not be a field a stale device can
# overwrite. The unique index is safe here for exactly the same reason: this row never syncs, so it
# cannot be the constraint two offline devices independently satisfy.
sync_state = Table(
    "sync_state",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("sequence", Integer, nullable=False, default=0),
    Index("idx_sync_state_owner", "owner", unique=True),
)

# Which (provider, model) pairs answer, per kind, for this owner. Its own table and never
# replicated: it is server state read through a route rather than vocabulary, and a client that
# cannot reach the server cannot capture anyway. No `revision`, `deleted` or `edited_by` — nothing
# merges this, so none of the three would have a reader, and their absence is what makes the table
# structurally unreplicable rather than merely unreplicated. The unique index is safe for exactly
# `sync_state`'s reason: this row never syncs, so it cannot be the constraint two offline devices
# independently satisfy.
#
# **No row means "use the deployment default"**, which is a legitimate answer rather than a gap, so
# nothing creates one eagerly — see `repository/model_selection.py`.
model_selection = Table(
    "model_selection",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    # {kind: [{"provider": id, "model": model}, ...]} — exactly the document the route takes and
    # returns, so the column and the wire are one shape and neither can drift from the other.
    # Ordering *is* the content here, which in rows would be a `position` integer renumbered on
    # every save; `vocabularies.gloss_langs` is the same call already made in this schema.
    Column("chains", JSON, nullable=False, default=dict),
    Column("edited_at", String(24), nullable=False),
    Index("idx_model_selection_owner", "owner", unique=True),
)

# How this owner wants sense images drawn. Server state for the same reason `model_selection` is:
# the drawing happens on the server, so unlike the editor's wrapping preference this cannot live on
# the device. Never replicated, no `revision`/`deleted`/`edited_by`, and the unique index is safe for
# `sync_state`'s reason — this row never syncs, so it cannot be a constraint two offline devices
# each satisfy on their own.
#
# **No row means "use the deployment default"**, exactly as with `model_selection`, so nothing
# creates one eagerly — see `repository/image_settings.py`.
image_settings = Table(
    "image_settings",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    # Whether pictures are drawn on their own at all — by the sweep, and by a client enriching a
    # word that was just saved. It deliberately does not gate the buttons: you pressed those, so
    # you meant them, and switching this off is how you get a word with no pictures and then add
    # the one you want by hand.
    Column("draw_enabled", Boolean, nullable=False, default=True),
    # The styles switched **off**, never the ones switched on. A set of switched-on ids left the
    # online dictionary sources permanently silent when one was added later; a style added to
    # `config/image-styles.yaml` must be on by default, and only this direction gives that.
    Column("styles_off", JSON, nullable=False, default=list),
    # Present each style with a few of its example subjects, sampled per word, which pushes the
    # writer toward styles it would otherwise pass over. `StyleTable.hints()` on or off.
    Column("boost_variety", Boolean, nullable=False, default=True),
    Column("edited_at", String(24), nullable=False),
    Index("idx_image_settings_owner", "owner", unique=True),
)

# The languages this owner studies, and how they want each presented. Replicated like any other
# record and deliberately without a unique index on `language`: uniqueness is forbidden on a
# replicated collection, because it is exactly the constraint two offline devices can each satisfy on
# their own. The client refuses a duplicate at graph level instead.
vocabularies = Table(
    "vocabularies",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("language", String(35), nullable=False),
    Column("definition_lang", String(35), nullable=False),
    Column("gloss_langs", JSON, nullable=False, default=list),
    Column("notes_lang", String(35), nullable=False),
    Column("display_name", String(120), nullable=False, default=""),
    Column("flag", String(32), nullable=False, default=""),
    Column("vocab_order", Integer, nullable=False, default=0),
    *_sync_fields(),
    Index("idx_vocabularies_owner_revision", "owner", "revision"),
    Index("idx_vocabularies_owner_language", "owner", "language"),
)

topics = Table(
    "topics",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("name", String(120), nullable=False),
    Column("icon", String(120), nullable=False, default=""),
    Column("topic_order", Integer, nullable=False, default=0),
    *_sync_fields(),
    Index("idx_topics_owner_revision", "owner", "revision"),
    Index("idx_topics_owner_name", "owner", "name"),
)

lexemes = Table(
    "lexemes",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("language", String(35), nullable=False),
    Column("headword", String(240), nullable=False),
    Column("lemma", String(240), nullable=False),
    Column("reading", String(240), nullable=False, default=""),
    Column("ipa", String(240), nullable=False, default=""),
    Column("pos", String(32), nullable=False),
    Column("gender", String(32), nullable=False, default=""),
    Column("register", String(32), nullable=False, default=""),
    Column("dialect", String(35), nullable=False, default=""),
    Column("emoji", String(32), nullable=False, default=""),
    # A list of topic ids rather than a join table: it is what `getStringSlice` projected, nothing on
    # the server queries by topic, and the same-owner rule is a validation concern either way.
    Column("topics", JSON, nullable=False, default=list),
    Column("status", String(32), nullable=False),
    Column("short_gloss", String(500), nullable=False, default=""),
    Column("notes", JSON, nullable=False, default=list),
    *_sync_fields(),
    Index("idx_lexemes_owner_revision", "owner", "revision"),
    Index("idx_lexemes_owner_language_headword", "owner", "language", "headword"),
)

senses = Table(
    "senses",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("lexeme", String(15), ForeignKey("lexemes.id", ondelete="CASCADE"), nullable=False),
    Column("definition", String(2000), nullable=False),
    Column("definition_lang", String(35), nullable=False),
    Column("glosses", JSON, nullable=False, default=list),
    Column("domain", String(120), nullable=False, default=""),
    Column("sense_order", Integer, nullable=False, default=0),
    *_sync_fields(),
    Index("idx_senses_owner_revision", "owner", "revision"),
    Index("idx_senses_owner_lexeme_order", "owner", "lexeme", "sense_order"),
)

attestations = Table(
    "attestations",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("lexeme", String(15), ForeignKey("lexemes.id", ondelete="CASCADE"), nullable=False),
    Column("text", String(5000), nullable=False),
    Column("translation", String(5000), nullable=False, default=""),
    Column("source_url", Text, nullable=False, default=""),
    Column("source_title", String(500), nullable=False, default=""),
    Column("source_kind", String(32), nullable=False),
    Column("captured_at", String(24), nullable=False),
    *_sync_fields(),
    Index("idx_attestations_owner_revision", "owner", "revision"),
    Index("idx_attestations_owner_lexeme", "owner", "lexeme"),
)

examples = Table(
    "examples",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("sense", String(15), ForeignKey("senses.id", ondelete="CASCADE"), nullable=False),
    Column("text", String(5000), nullable=False),
    Column("text_lang", String(35), nullable=False),
    Column("translation", String(5000), nullable=False, default=""),
    Column("translation_lang", String(35), nullable=False, default=""),
    Column("origin", String(32), nullable=False),
    # Not a cascade: an attestation and the example drawn from it are two records, and tombstoning
    # one must not remove the other.
    Column("source_attestation", String(15), ForeignKey("attestations.id"), nullable=True),
    Column("model_id", String(240), nullable=False, default=""),
    Column("video_ref", String(500), nullable=False, default=""),
    Column("video_title", String(500), nullable=False, default=""),
    Column("video_start", Integer, nullable=False, default=0),
    Column("image_ref", String(500), nullable=False, default=""),
    Column("audio_ref", String(500), nullable=False, default=""),
    Column("note", String(2000), nullable=False, default=""),
    Column("matched_form", String(240), nullable=False, default=""),
    Column("matched_translation_form", String(240), nullable=False, default=""),
    Column("approved", Boolean, nullable=False, default=False),
    *_sync_fields(),
    Index("idx_examples_owner_revision", "owner", "revision"),
    Index("idx_examples_owner_sense", "owner", "sense"),
    Index("idx_examples_owner_attestation", "owner", "source_attestation"),
)

image_prompts = Table(
    "image_prompts",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("lexeme", String(15), ForeignKey("lexemes.id", ondelete="CASCADE"), nullable=False),
    Column("sense", String(15), ForeignKey("senses.id", ondelete="CASCADE"), nullable=True),
    Column("prompt", String(10000), nullable=False),
    Column("style_id", String(120), nullable=False),
    Column("seed", Integer, nullable=False, default=0),
    Column("model_id", String(240), nullable=False),
    Column("prompt_version", String(128), nullable=False),
    Column("image_ref", String(500), nullable=False, default=""),
    Column("image_model_id", String(240), nullable=False, default=""),
    # Which sentence the picture illustrates. Not a cascade, for the reason `source_attestation`
    # above is not one: deleting the example must not delete the picture drawn from it.
    Column("example", String(15), ForeignKey("examples.id"), nullable=True),
    # Why an undrawn row is undrawn. Without these three, `image_ref = ""` meant both "briefed, not
    # yet drawn" and "drawing was refused", so a sweep defined as "which senses lack a picture"
    # retried a permanently blocked sense forever.
    Column("attempts", Integer, nullable=False, default=0),
    Column("failure_reason", String(500), nullable=False, default=""),
    # The owner has ruled on this sense. Deliberately not a tombstone: `image_prompt_id` is derived
    # from `sense`, so a tombstoned row is invisible to the sweep, which re-briefs the sense and
    # mints the same id — tombstoning does not prevent regeneration, it guarantees a collision.
    Column("suppressed", Boolean, nullable=False, default=False),
    *_sync_fields(),
    Index("idx_image_prompts_owner_revision", "owner", "revision"),
    Index("idx_image_prompts_owner_lexeme", "owner", "lexeme"),
    Index("idx_image_prompts_owner_sense", "owner", "sense"),
)

study_states = Table(
    "study_states",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("lexeme", String(15), ForeignKey("lexemes.id", ondelete="CASCADE"), nullable=False),
    Column("system", String(80), nullable=False),
    Column("note_id", Integer, nullable=False, default=0),
    Column("card_ids", JSON, nullable=False, default=list),
    Column("reps", Integer, nullable=False, default=0),
    Column("lapses", Integer, nullable=False, default=0),
    Column("stability", Float, nullable=False, default=0.0),
    Column("difficulty", Float, nullable=False, default=0.0),
    Column("retrievability", Float, nullable=False, default=0.0),
    Column("last_review", String(24), nullable=False, default=""),
    Column("synced_at", String(24), nullable=False, default=""),
    *_sync_fields(),
    Index("idx_study_states_owner_revision", "owner", "revision"),
    Index("idx_study_states_owner_lexeme_system", "owner", "lexeme", "system"),
)

TABLES = {table.name: table for table in metadata.tables.values()}
