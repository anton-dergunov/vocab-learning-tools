const REPLICATED = ["topics", "lexemes", "senses", "attestations", "examples", "image_prompts", "study_states"];

routerAdd("GET", "/api/acervo/v1/{path...}", (event) => require(`${__hooks}/acervo.js`).dispatch(event));
routerAdd("POST", "/api/acervo/v1/{path...}", (event) => require(`${__hooks}/acervo.js`).dispatch(event));
onRecordValidate((event) => {
  require(`${__hooks}/acervo.js`).validateRecord(event.app, event.record);
  event.next();
}, ...REPLICATED);

// Revisions are the replication cursor, so every writer must get one — not just the graph route.
// The seeder, the generation flows and the Anki consumer all save records directly, and a record
// left at revision zero is invisible to every `revision > cursor` pull, permanently and silently.
// Allocating here is what makes that impossible to forget. `event.app` is the transaction, so the
// counter and the record it numbers commit together.
const stampRevision = (event) => {
  const owner = event.record.getString("owner");
  if (owner) event.record.set("revision", require(`${__hooks}/acervo.js`).allocateRevision(event.app, owner));
  event.next();
};
onRecordCreateExecute(stampRevision, ...REPLICATED);
onRecordUpdateExecute(stampRevision, ...REPLICATED);

// Native archives remain outside pb_public so the PWA service worker never downloads them.
// A release without a published Mac application simply exposes an empty directory.
try {
  const downloads = $os.getenv("ACERVO_DOWNLOADS_PATH") || "/pb/downloads";
  routerAdd("GET", "/api/acervo/downloads/{path...}", $apis.static($os.dirFS(downloads), false));
} catch (error) {
  console.log("Acervo: no macOS download directory; the desktop application is not offered.");
}
