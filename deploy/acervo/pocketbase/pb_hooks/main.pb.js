routerAdd("GET", "/api/acervo/v1/{path...}", (event) => require(`${__hooks}/acervo.js`).dispatch(event));
routerAdd("POST", "/api/acervo/v1/{path...}", (event) => require(`${__hooks}/acervo.js`).dispatch(event));
onRecordValidate((event) => {
  require(`${__hooks}/acervo.js`).validateRecord(event.app, event.record);
  event.next();
}, "lexemes", "senses", "attestations", "examples", "image_prompts", "study_states");

// Native archives remain outside pb_public so the PWA service worker never downloads them.
// A release without a published Mac application simply exposes an empty directory.
try {
  const downloads = $os.getenv("ACERVO_DOWNLOADS_PATH") || "/pb/downloads";
  routerAdd("GET", "/api/acervo/downloads/{path...}", $apis.static($os.dirFS(downloads), false));
} catch (error) {
  console.log("Acervo: no macOS download directory; the desktop application is not offered.");
}
