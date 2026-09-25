import { useState } from "react";
import type { Topic, Vocabulary } from "./domain";
import { languageOf } from "./languages";
import { repository, type ReplicaSnapshot } from "./repository";
import { topicOptions, vocabularies as configuredVocabularies } from "./selectors";

/**
 * The two things capture cannot work without: which languages this owner keeps, and which topics a
 * word can be filed under (`docs/architecture/data-model.md` — both are records, never a fixed enum).
 *
 * Every action here is an ordinary online-only write through the repository, so it fails loudly and
 * changes nothing locally when the server is unreachable, exactly like editing an article.
 */

const LANGUAGE_TAG = /^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/;

function parseLanguageList(value: string): string[] | null {
  const codes = value.split(",").map((code) => code.trim()).filter(Boolean);
  if (!codes.length || codes.some((code) => !LANGUAGE_TAG.test(code))) return null;
  return [...new Set(codes)];
}

function VocabularyRow({ vocabulary, wordCount, onSave, onRemove }: {
  vocabulary: Vocabulary;
  wordCount: number;
  onSave(changes: Partial<Vocabulary>): void;
  onRemove(): void;
}) {
  const fallback = languageOf(vocabulary.language);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(vocabulary.displayName ?? fallback.name);
  const [flag, setFlag] = useState(vocabulary.flag ?? fallback.flag);
  const [definitionLang, setDefinitionLang] = useState(vocabulary.definitionLang);
  const [glossLangs, setGlossLangs] = useState(vocabulary.glossLangs.join(", "));
  const [notesLang, setNotesLang] = useState(vocabulary.notesLang);

  if (!editing) {
    return <div className="config-row">
      <span className="config-icon">{vocabulary.flag ?? fallback.flag}</span>
      <span className="config-main">
        <strong>{vocabulary.displayName ?? fallback.name}</strong>
        <span>
          {vocabulary.language} · defined in {vocabulary.definitionLang} · translated into{" "}
          {vocabulary.glossLangs.join(", ")} · noted in {vocabulary.notesLang} ·{" "}
          {wordCount} {wordCount === 1 ? "word" : "words"}
        </span>
      </span>
      <button className="tb-btn" onClick={() => setEditing(true)}>Edit</button>
      <button className="tb-btn danger" onClick={onRemove}>Remove</button>
    </div>;
  }

  return <div className="config-edit">
    <label className="label" htmlFor={`name-${vocabulary.id}`}>Name</label>
    <input id={`name-${vocabulary.id}`} value={name} onChange={(event) => setName(event.target.value)} />
    <label className="label" htmlFor={`flag-${vocabulary.id}`}>Flag</label>
    <input id={`flag-${vocabulary.id}`} value={flag} onChange={(event) => setFlag(event.target.value)} />
    <label className="label" htmlFor={`def-${vocabulary.id}`}>Senses defined in</label>
    <input
      id={`def-${vocabulary.id}`} value={definitionLang} spellCheck={false}
      onChange={(event) => setDefinitionLang(event.target.value)}
    />
    <label className="label" htmlFor={`gloss-${vocabulary.id}`}>Translated into</label>
    <input
      id={`gloss-${vocabulary.id}`} value={glossLangs} spellCheck={false} placeholder="en, ru"
      onChange={(event) => setGlossLangs(event.target.value)}
    />
    <label className="label" htmlFor={`notes-${vocabulary.id}`}>Notes written in</label>
    <input
      id={`notes-${vocabulary.id}`} value={notesLang} spellCheck={false}
      onChange={(event) => setNotesLang(event.target.value)}
    />
    <p className="config-help">
      Language tags, most preferred first. Translations are the languages every generated entry is
      translated into. Notes are the usage remarks under an entry — the language you read fastest,
      until you would rather read them in the language you are learning.
    </p>
    <div className="sync-actions">
      <button className="tb-btn" onClick={() => setEditing(false)}>Cancel</button>
      <button className="tb-btn primary" onClick={() => {
        setEditing(false);
        onSave({
          displayName: name.trim() || null,
          flag: flag.trim() || null,
          definitionLang: definitionLang.trim(),
          glossLangs: parseLanguageList(glossLangs) ?? vocabulary.glossLangs,
          notesLang: notesLang.trim() || vocabulary.notesLang
        });
      }}>Save</button>
    </div>
  </div>;
}

export function VocabularyEditor({ snapshot, onNotify, onChanged }: {
  snapshot: ReplicaSnapshot;
  onNotify(message: string): void;
  onChanged(): void;
}) {
  const entries = configuredVocabularies(snapshot);
  const [adding, setAdding] = useState(false);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);

  const counts = new Map<string, number>();
  snapshot.lexemes.filter((lexeme) => !lexeme.deleted)
    .forEach((lexeme) => counts.set(lexeme.language, (counts.get(lexeme.language) ?? 0) + 1));

  async function run(action: () => Promise<unknown>, failure: string): Promise<boolean> {
    setBusy(true);
    try {
      await action();
      onChanged();
      return true;
    } catch (error) {
      onNotify(error instanceof Error ? error.message : failure);
      return false;
    } finally {
      setBusy(false);
    }
  }

  function add() {
    const language = code.trim();
    if (!LANGUAGE_TAG.test(language)) {
      onNotify("That is not a language tag. Try es, en, ru or zh-Hans.");
      return;
    }
    if (entries.some((entry) => entry.language === language)) {
      onNotify(`You already keep a ${language} vocabulary.`);
      return;
    }
    const defaults = languageOf(language);
    // A language the table does not know has no sensible pivot to guess, so English is the
    // starting point and the row is immediately editable.
    const glossLangs = defaults.glossLangs.length ? defaults.glossLangs : ["en"];
    void run(() => repository.saveVocabulary({
      language,
      definitionLang: language,
      glossLangs,
      notesLang: glossLangs[0],
      displayName: defaults.name,
      flag: defaults.flag,
      order: entries.length
    }), "That vocabulary could not be added.").then((added) => {
      if (!added) return;
      setAdding(false);
      setCode("");
    });
  }

  function remove(vocabulary: Vocabulary) {
    const words = counts.get(vocabulary.language) ?? 0;
    if (words > 0) {
      // Removing the configuration would leave those words with no gloss preference and no way back
      // to it, which reads as data loss even though nothing was deleted.
      onNotify(`${vocabulary.displayName ?? vocabulary.language} still has ${words} ${words === 1 ? "word" : "words"}. Delete or move them first.`);
      return;
    }
    void run(() => repository.delete("vocabularies", vocabulary.id), "That vocabulary could not be removed.");
  }

  return <section className="config-section">
    <h3>Vocabularies</h3>
    <p className="config-help">The languages you study. A language has to be here before a word in it can be captured.</p>
    <div className="config-list">
      {entries.map((vocabulary) => <VocabularyRow
        key={vocabulary.id}
        vocabulary={vocabulary}
        wordCount={counts.get(vocabulary.language) ?? 0}
        onSave={(changes) => void run(() => repository.saveVocabulary({
          language: vocabulary.language,
          definitionLang: vocabulary.definitionLang,
          glossLangs: vocabulary.glossLangs,
          notesLang: vocabulary.notesLang,
          displayName: vocabulary.displayName,
          flag: vocabulary.flag,
          order: vocabulary.order,
          ...changes
        }, vocabulary.id), "That vocabulary could not be saved.")}
        onRemove={() => remove(vocabulary)}
      />)}
      {!entries.length && <p className="config-help">None yet — add the first language you are learning.</p>}
    </div>
    {adding ? <div className="config-edit">
      <label className="label" htmlFor="new-vocabulary">Language tag</label>
      <input
        id="new-vocabulary" value={code} autoComplete="off" spellCheck={false} placeholder="es"
        onChange={(event) => setCode(event.target.value)}
      />
      <div className="sync-actions">
        <button className="tb-btn" onClick={() => { setAdding(false); setCode(""); }}>Cancel</button>
        <button className="tb-btn primary" disabled={busy} onClick={add}>Add vocabulary</button>
      </div>
    </div> : <button className="tb-btn" onClick={() => setAdding(true)}>Add a vocabulary…</button>}
  </section>;
}

function TopicRow({ topic, count, onSave, onRemove, onMove }: {
  topic: Topic;
  count: number;
  onSave(name: string, icon: string): void;
  onRemove(): void;
  onMove(direction: -1 | 1): void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(topic.name);
  const [icon, setIcon] = useState(topic.icon ?? "");

  if (!editing) {
    return <div className="config-row">
      <span className="config-icon">{topic.icon ?? "📌"}</span>
      <span className="config-main">
        <strong>{topic.name}</strong>
        <span>{count} {count === 1 ? "word" : "words"}</span>
      </span>
      <button className="icon-btn" aria-label={`Move ${topic.name} up`} onClick={() => onMove(-1)}>↑</button>
      <button className="icon-btn" aria-label={`Move ${topic.name} down`} onClick={() => onMove(1)}>↓</button>
      <button className="tb-btn" onClick={() => setEditing(true)}>Edit</button>
      <button className="tb-btn danger" onClick={onRemove}>Remove</button>
    </div>;
  }

  return <div className="config-edit">
    <label className="label" htmlFor={`topic-name-${topic.id}`}>Name</label>
    <input id={`topic-name-${topic.id}`} value={name} onChange={(event) => setName(event.target.value)} />
    <label className="label" htmlFor={`topic-icon-${topic.id}`}>Icon</label>
    <input id={`topic-icon-${topic.id}`} value={icon} onChange={(event) => setIcon(event.target.value)} />
    <div className="sync-actions">
      <button className="tb-btn" onClick={() => setEditing(false)}>Cancel</button>
      <button className="tb-btn primary" onClick={() => { setEditing(false); onSave(name.trim(), icon.trim()); }}>Save</button>
    </div>
  </div>;
}

export function TopicEditor({ snapshot, language, onNotify, onChanged }: {
  snapshot: ReplicaSnapshot;
  language: string;
  onNotify(message: string): void;
  onChanged(): void;
}) {
  const topics = snapshot.topics.filter((topic) => !topic.deleted)
    .slice()
    .sort((left, right) => left.order - right.order || left.name.localeCompare(right.name));
  const counts = new Map(topicOptions(snapshot, language).map((option) => [option.id, option.count ?? 0]));
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [icon, setIcon] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<unknown>, failure: string): Promise<boolean> {
    setBusy(true);
    try {
      await action();
      onChanged();
      return true;
    } catch (error) {
      onNotify(error instanceof Error ? error.message : failure);
      return false;
    } finally {
      setBusy(false);
    }
  }

  function add() {
    const trimmed = name.trim();
    if (!trimmed) {
      onNotify("A topic needs a name.");
      return;
    }
    if (topics.some((topic) => topic.name.toLowerCase() === trimmed.toLowerCase())) {
      onNotify(`You already have a topic called ${trimmed}.`);
      return;
    }
    void run(() => repository.saveTopic({
      name: trimmed, icon: icon.trim() || null, order: topics.length
    }), "That topic could not be added.").then((added) => {
      if (!added) return;
      setAdding(false);
      setName("");
      setIcon("");
    });
  }

  /* Two writes rather than one: the repository saves a record at a time, and reordering is rare
     enough that a second round trip costs less than a bespoke batch path would. */
  function move(index: number, direction: -1 | 1) {
    const other = topics[index + direction];
    const topic = topics[index];
    if (!other) return;
    void run(async () => {
      await repository.saveTopic({ name: topic.name, icon: topic.icon, order: other.order }, topic.id);
      await repository.saveTopic({ name: other.name, icon: other.icon, order: topic.order }, other.id);
    }, "Those topics could not be reordered.");
  }

  return <section className="config-section">
    <h3>Topics</h3>
    <p className="config-help">
      What a word can be filed under. Generated entries are classified into these and nothing else.
    </p>
    <div className="config-list">
      {topics.map((topic, index) => <TopicRow
        key={topic.id}
        topic={topic}
        count={counts.get(topic.id) ?? 0}
        onSave={(nextName, nextIcon) => void run(
          () => repository.saveTopic({ name: nextName || topic.name, icon: nextIcon || null, order: topic.order }, topic.id),
          "That topic could not be saved."
        )}
        onRemove={() => void run(() => repository.delete("topics", topic.id), "That topic could not be removed.")}
        onMove={(direction) => move(index, direction)}
      />)}
      {!topics.length && <p className="config-help">None yet — words cannot be filed until you add one.</p>}
    </div>
    {adding ? <div className="config-edit">
      <label className="label" htmlFor="new-topic">Name</label>
      <input id="new-topic" value={name} autoComplete="off" placeholder="Slang" onChange={(event) => setName(event.target.value)} />
      <label className="label" htmlFor="new-topic-icon">Icon</label>
      <input id="new-topic-icon" value={icon} autoComplete="off" placeholder="💬" onChange={(event) => setIcon(event.target.value)} />
      <div className="sync-actions">
        <button className="tb-btn" onClick={() => { setAdding(false); setName(""); setIcon(""); }}>Cancel</button>
        <button className="tb-btn primary" disabled={busy} onClick={add}>Add topic</button>
      </div>
    </div> : <button className="tb-btn" onClick={() => setAdding(true)}>Add a topic…</button>}
  </section>;
}
