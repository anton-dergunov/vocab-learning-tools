"""Piped over stdin into `docker exec -i acervo-server-1 python3 -` on the NAS. Read-only.

Never written to disk on the NAS and never run as a file there — `ssh nas "docker exec -i
acervo-server-1 python3 -" < extract_remote.py` sends this as a stream and the container never sees
a path. Opens the database by URI in explicit read-only mode (`mode=ro`) plus `PRAGMA query_only`,
rather than through `acervo.db.engine.create_database_engine`, which issues pragma writes
(`journal_mode`, `foreign_keys`) on connect — harmless on a database already in WAL, but unnecessary
for a read and easy to avoid.

Prints one JSON object to stdout: every non-deleted lexeme's fields this experiment needs, plus the
owner's vocabularies (for `definitionLang`/`glossLangs`/`notesLang`). Nothing else is read — no
senses, no examples, no owner email.
"""

import json
import os
import sqlite3

DB_PATH = os.environ["ACERVO_DB_PATH"]

conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
conn.execute("PRAGMA query_only = ON")

lexemes = conn.execute(
    "SELECT id, owner, language, headword, lemma, pos, short_gloss, primary_gloss, emotion, topics "
    "FROM lexemes WHERE deleted = 0"
).fetchall()
lexeme_cols = [d[0] for d in conn.execute("SELECT * FROM lexemes LIMIT 0").description]

vocabularies = conn.execute(
    "SELECT owner, language, definition_lang, gloss_langs, notes_lang "
    "FROM vocabularies WHERE deleted = 0"
).fetchall()
vocabulary_cols = [d[0] for d in conn.execute("SELECT * FROM vocabularies LIMIT 0").description]

payload = {
    "lexemes": [dict(zip(lexeme_cols, row)) for row in lexemes],
    "vocabularies": [dict(zip(vocabulary_cols, row)) for row in vocabularies],
}
print(json.dumps(payload, ensure_ascii=False))
