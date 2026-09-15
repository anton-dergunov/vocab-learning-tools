/* Acervo — UI prototype behaviour.
   Everything here is view logic over the fixtures in data.js. No storage, no
   network: buttons that would call the repository or a provider are stubs. */

const state = {
  lang: "es",
  topic: "all",
  sort: "recent",
  query: "",
  openId: null,
  add: false,       // composing a new entry, which replaces the list
  mode: "read",     // read | yaml | edit
  /* External dictionaries. `openExt` is a word, not an id: an external entry has no id, which is
     most of what distinguishes it from one of yours. `onlineDone` is what ⏎ sets. */
  openExt: null,
  onlineDone: false,
  scope: { device: true, server: true, online: true },
  /* How far the ask dock is open, and which block a question is bounded to. Three detents and no
     intermediate state: dock | half | full (design §06 §7.3). */
  ask: "dock",   // dock | open | full
  askFocus: null,
  /* A proposal under review. Painted rather than applied — the prototype has no applier — so the
     marks, the review bar and the struck-through removal can all be looked at. */
  review: false,
  /* The article redesign spike. `view` null means "the default for this device" (`currentView`);
     `card` is which card Cards is showing; `pictureAt` is the open question of where a picture goes
     in Cards — "anchor", with the sentence it was drawn from, or "first", always first; and
     `sayTranslations` puts listen buttons after translations too. */
  view: null,
  card: 0,
  pictureAt: "anchor",
  sayTranslations: false
};

const $  = (sel, root = document) => root.querySelector(sel);
const el = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; };
const topicOf = (key) => TOPICS.find((t) => t.key === key);
const langOf  = (code) => LANGUAGES.find((l) => l.code === code);
const strip   = (s) => String(s).replace(/<[^>]+>/g, "");
const esc     = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const ICON = {
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.6-3.6"/></svg>',
  back:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>',
  plus:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  play:   '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13l11-6.5z"/></svg>',
  caret:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5l7 7-7 7"/></svg>',
  pencil: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4l10-10-4-4L4 16z"/><path d="M13.5 6.5l4 4"/></svg>',
  trash:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13"/></svg>',
  close:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  book:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H18v14H5.5A1.5 1.5 0 0 0 4 19.5z"/><path d="M4 19.5A1.5 1.5 0 0 1 5.5 18H20v2.5H5.5"/><path d="M8 8h6"/></svg>',
  globe:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17"/><path d="M12 3.5c2.2 2.3 3.3 5.2 3.3 8.5S14.2 18.2 12 20.5c-2.2-2.3-3.3-5.2-3.3-8.5S9.8 5.8 12 3.5z"/></svg>',
  /* Asking about a word — deliberately not `✳`, which is already "where you met it". */
  ask:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 14.5A2.5 2.5 0 0 1 17.5 17H12l-4.5 3.5V17H6.5A2.5 2.5 0 0 1 4 14.5v-8A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5z"/><path d="M10.2 8.6a1.9 1.9 0 1 1 2.6 1.8c-.5.2-.8.7-.8 1.2v.3"/><path d="M12 14.2v.1"/></svg>',
  chevron:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 15l7-7 7 7"/></svg>',
  send:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12h14"/><path d="M13 6l6 6-6 6"/></svg>'
};

/* ── external dictionaries ───────────────────────────────────────────────
   Below a rule, after every one of your own words, and never interleaved with them. Carries no
   emoji, no sense count and no strength bars, because it has none of those things. */

function externalHits() {
  const q = state.query.trim().toLowerCase();
  if (!q) return [];
  return EXTERNAL.filter((x) => x.word.toLowerCase().startsWith(q.slice(0, 3))
    && (x.origin !== "online" || state.onlineDone)
    && (x.origin !== "device" || state.scope.device)
    && (x.origin !== "online" || state.scope.online));
}

function externalOf(word) { return EXTERNAL.find((x) => x.word === word); }

function sourceLabel(x) {
  return x.sources.length > 2 ? `${x.sources.length} sources` : x.sources.map((s) => s.name).join(" · ");
}

function renderExternal() {
  const q = state.query.trim();
  const hits = externalHits();
  const anyScope = state.scope.device || state.scope.server || state.scope.online;
  if (!q || !anyScope) return "";
  return `
    <div class="ext-section">
      <div class="list-sep"><span class="label">Other dictionaries</span></div>
      <div class="rows">
        ${hits.map((x) => `
          <button class="row ext" data-ext="${esc(x.word)}">
            <span class="plate ext">${x.origin === "online" ? ICON.globe : ICON.book}</span>
            <span data-sources="${esc(sourceLabel(x))}">
              <span class="word">${esc(x.word)}</span>
              <span class="gloss">${esc(x.gloss)}</span>
            </span>
            <span class="meta"><span class="src">${esc(sourceLabel(x))}</span></span>
          </button>`).join("")}
      </div>
      ${hits.length ? "" : `<p class="ext-status">No dictionary here holds “${esc(q)}”.</p>`}
      ${state.scope.online && !state.onlineDone ? `
        <button class="ext-online" id="onlineBtn">${ICON.globe}
          <span>Press ⏎ to look “${esc(q)}” up online</span></button>` : ""}
    </div>`;
}

function renderExternalArticle(x) {
  const section = (s) => `
    <section class="sec ext-sec" id="ext-${esc(s.id)}">
      <div class="rail-l"><div class="inner">
        <span class="num">${s.origin === "online" ? "\u{1F310}" : "\u{1F4D6}"}</span>
        <span class="label">${esc(s.name.replace(/\s*[([].*$/, ""))}</span>
      </div></div>
      <div class="body">
        ${s.tier === "html" ? `<div class="ext-body">${s.html}</div>` : `
          <div class="ext-entry">
            <p class="gram"><span>${esc(x.posLabel || "")}</span><span class="sep">·</span><span>${esc(state.lang)}</span></p>
            <ol class="ext-senses">
              ${s.senses.map((sense) => `
                <li><p class="sense-def">${esc(sense.definition)}</p>
                  ${(sense.examples || []).map((e) => `
                    <div class="ex ext-ex"><p class="t">${esc(e.text)}</p>
                      ${e.translation ? `<p class="tr">${esc(e.translation)}</p>` : ""}</div>`).join("")}
                </li>`).join("")}
            </ol>
          </div>`}
        <p class="ext-credit"><span>${esc(s.attribution)}</span><span class="sep">·</span>
          <span>${s.origin === "device" ? "stored on this device" : s.origin === "server" ? "on your server" : "looked up online"}</span></p>
      </div>
    </section>`;

  return `
    ${review}
    <div class="masthead">
      <div class="head-row">
        <div class="emoji-plate ext">${x.online ? ICON.globe : ICON.book}</div>
        <div class="head-text">
          <h1 class="headword">${esc(x.word)}</h1>
          ${x.ipa ? `<div class="pron-row"><span class="ipa">${esc(x.ipa)}</span></div>` : ""}
          <p class="gram"><span>${esc(x.posLabel || "")}</span><span class="sep">·</span>
            <span>${esc(langOf(state.lang).name)}</span><span class="sep">·</span><span>external dictionary</span></p>
        </div>
      </div>
      <div class="chips">
        <span class="chip ext">not in your words</span>
        ${x.sections.length === 1 ? `<span class="chip">${esc(x.sections[0].name)}</span>` : ""}
      </div>
    </div>
    ${x.sections.length > 1 ? `<nav class="ext-jump" aria-label="Sources">
      ${x.sections.map((s) => `<button data-jump="ext-${esc(s.id)}">${esc(s.name)}</button>`).join("")}
    </nav>` : ""}
    <div class="ext-actions"><button class="tb-btn primary" id="extAdd">Add to my words</button></div>
    ${x.sections.map(section).join("")}`;
}

/* ── selection helpers ───────────────────────────────────────────────── */

function inLanguage()  { return LEXEMES.filter((x) => x.language === state.lang); }
function inboxCount()  { return inLanguage().filter((x) => x.status === "inbox").length; }
function topicCount(k) { return inLanguage().filter((x) => x.topics.includes(k) && x.status !== "inbox").length; }

function visible() {
  let rows = inLanguage();
  const q = state.query.trim().toLowerCase();
  if (q) {
    rows = rows.filter((x) => {
      const hay = [x.headword, x.lemma, x.reading || "", x.shortGloss || "",
        ...x.senses.map((s) => s.definition),
        ...x.senses.flatMap((s) => s.glosses.flatMap((g) => g.terms))].join(" ").toLowerCase();
      return hay.includes(q);
    });
  } else if (state.topic === "inbox") {
    rows = rows.filter((x) => x.status === "inbox");
  } else {
    rows = rows.filter((x) => x.status !== "inbox");
    if (state.topic !== "all") rows = rows.filter((x) => x.topics.includes(state.topic));
  }
  const key = (x) => x.headword.replace(/^(el|la|los|las) /, "");
  const sorters = {
    recent: (a, b) => b.createdAt.localeCompare(a.createdAt),
    alpha:  (a, b) => key(a).localeCompare(key(b), state.lang),
    hard:   (a, b) => (b.study ? b.study.difficulty : 99) - (a.study ? a.study.difficulty : 99)
  };
  return rows.slice().sort(sorters[state.sort]);
}

function shortGlossOf(x) {
  if (x.shortGloss) return x.shortGloss;
  const first = x.senses[0];
  const pref = langOf(x.language).glossLangs[0];
  const g = first.glosses.find((y) => y.lang === pref) || first.glosses[0];
  return g ? g.terms.join("; ") : strip(first.definition);
}

/* ── chrome ──────────────────────────────────────────────────────────── */

function renderRail() {
  const rail = $("#rail");
  const tab = (id, icon, name, count, on) => `
    <button class="tab ${on ? "on" : ""}" data-topic="${id}" title="${name}">
      <span class="ic">${icon}</span><span class="nm">${name}</span>
      ${count !== null ? `<span class="cnt">${count}</span>` : ""}
    </button>`;
  const all = inLanguage().filter((x) => x.status !== "inbox").length;
  rail.innerHTML =
    tab("all", "\u{1F4D6}", "All", all, state.topic === "all") +
    (inboxCount() ? tab("inbox", "\u{1F4E5}", "Inbox", inboxCount(), state.topic === "inbox") : "") +
    '<div class="rail-sep"></div>' +
    TOPICS.map((t) => tab(t.key, t.icon, t.name, topicCount(t.key) || null, state.topic === t.key)).join("");
}

function renderLangButton() {
  const l = langOf(state.lang);
  $("#langBtn").innerHTML = `<span class="flag">${l.flag}</span><span class="code">${l.code.toUpperCase()}</span>`;
  $("#langMenu").innerHTML =
    '<div class="label menu-label">Vocabulary language</div>' +
    LANGUAGES.map((x) => `<button data-lang="${x.code}" class="${x.code === state.lang ? "on" : ""}">
        <span>${x.flag}</span><span>${x.name}</span>
        <span class="cnt">${LEXEMES.filter((y) => y.language === x.code).length}</span>
      </button>`).join("");
}

/* ── list view ───────────────────────────────────────────────────────── */

function renderList() {
  const rows = visible();
  const q = state.query.trim();
  let title, icon, sub;
  if (q) {
    title = "Search"; icon = "\u{1F50D}";
    sub = `${rows.length} match${rows.length === 1 ? "" : "es"} for “${esc(q)}” in ${langOf(state.lang).name}`;
  } else if (state.topic === "inbox") {
    title = "Inbox"; icon = "\u{1F4E5}";
    sub = "Captured, processed, waiting for your review";
  } else if (state.topic === "all") {
    title = "All words"; icon = "\u{1F4D6}";
    sub = `${rows.length} in ${langOf(state.lang).name}`;
  } else {
    const t = topicOf(state.topic);
    title = t.name; icon = t.icon;
    sub = `${rows.length} word${rows.length === 1 ? "" : "s"} in ${langOf(state.lang).name}`;
  }

  const sortBtn = (id, text) => `<button class="sort-btn ${state.sort === id ? "on" : ""}" data-sort="${id}">${text}</button>`;
  const strength = (x) => {
    const s = x.study ? Math.min(4, Math.max(1, Math.round(Math.log10(Math.max(x.study.stability, 1.1)) * 1.7 + 1))) : 0;
    return `<span class="strength" title="${x.study ? `stability ${x.study.stability} d · difficulty ${x.study.difficulty}` : "not scheduled yet"}">` +
      [1, 2, 3, 4].map((i) => `<i class="${i <= s ? "f" : ""}"></i>`).join("") + "</span>";
  };

  return `
    <div class="list-head">
      <div>
        <h1><span class="ic">${icon}</span>${esc(title)}</h1>
        <p class="label sub">${sub}</p>
      </div>
      <div class="sortbar">
        ${sortBtn("recent", "Recent")}${sortBtn("alpha", "A–Z")}${sortBtn("hard", "Hardest")}
      </div>
    </div>
    <div class="rows">
      ${rows.length ? rows.map((x) => `
        <button class="row ${x.status === "inbox" ? "inbox" : ""}" data-open="${x.id}">
          <span class="plate">${x.emoji || "\u{1F4C4}"}</span>
          <span>
            <span class="word">${esc(x.headword)}${x.reading ? `<span class="rdg">${esc(x.reading)}</span>` : ""}</span>
            <span class="gloss">${esc(shortGlossOf(x))}</span>
          </span>
          <span class="meta">
            ${x.senses.length > 1 ? `<span class="senses">${x.senses.length} senses</span>` : ""}
            ${x.status === "inbox" ? '<span class="prov">unreviewed</span>' : strength(x)}
          </span>
        </button>`).join("")
      : q ? `<p class="ext-status none-yours">No words of yours match “${esc(q)}”.</p>`
          : '<p class="empty">Nothing here yet.</p>'}
    </div>
    ${renderExternal()}`;
}

/* ── article view ────────────────────────────────────────────────────────
   One article, two ways to read it. **Page** is the whole entry scrolled top to bottom, and is where
   the conversation lives, because an edit that reorders senses needs every sense in view. **Cards**
   is one thing at a time, swiped left and right, for glancing at a word on a phone. Both draw from
   the same record and neither has anything the other lacks except the ask dock.

   Everything that used to sit under a sentence as a badge — origin, model, "unapproved", the
   picture's style, where a clip starts — is gone from the reading surface. Nobody reads them while
   learning a word, and what little is worth keeping lives in Details. */

/* Plain words rather than a grammarian's abbreviations: "noun, feminine", not "n. · f.". */
const POS_WORD = { noun: "noun", verb: "verb", adj: "adjective", adv: "adverb", phrase: "phrase", idiom: "idiom", expression: "expression" };
const REGISTER_WORD = { colloquial: "informal", formal: "formal", slang: "slang", vulgar: "vulgar" };
const DIALECT_WORD = { "es-ES": "Spain", "es-MX": "Mexico", "es-AR": "Argentina", "en-GB": "British", "en-US": "American" };

function grammarWords(x) {
  const bits = [(POS_WORD[x.pos] || x.pos) + (x.gender ? `, ${x.gender}` : "")];
  if (x.register && x.register !== "neutral") bits.push(REGISTER_WORD[x.register] || x.register);
  if (x.dialect) bits.push(DIALECT_WORD[x.dialect] || x.dialect);
  return bits.join(" · ");
}

/* Where the word is filed, as a quiet line rather than a row of chips. */
function placeLine(x) {
  const status = x.status === "inbox" ? "Inbox" : x.status === "learned" ? "Learned" : null;
  const topics = x.topics.map((k) => topicOf(k).name).join(", ");
  return [status, topics].filter(Boolean).join(" — ");
}

/* A small listen button after a sentence. `always` keeps it visible where hovering is possible. */
function say(text, extra = "") {
  return `<button class="say${extra ? ` ${extra}` : ""}" data-say="${esc(strip(text))}" aria-label="Listen">${ICON.play}</button>`;
}
const sayTranslation = (text) => (state.sayTranslations ? say(text, "say-tr") : "");

/* A sentence with its listen button glued to the last word, so the button never wraps onto a line
   of its own. Left alone when the last word is inside markup, which only a painted proposal has. */
function spoken(html, button) {
  if (!button) return html;
  const tail = html.match(/(\S+)$/);
  if (!tail || /[<>]/.test(tail[1])) return html + button;
  return `${html.slice(0, tail.index)}<span class="say-tail">${tail[1]}${button}</span>`;
}

/* A video title is the loudest text a creator can write and the least useful thing on the page, so
   it is made quiet by rule rather than by taste: hashtags and emoji out, everything lower case. */
function quietTitle(s) {
  return String(s)
    .replace(/#[\p{L}\p{N}_]+/gu, " ")
    .replace(/[\p{Extended_Pictographic}\u{FE0F}\u{200D}\u{1F3FB}-\u{1F3FF}]/gu, "")
    .replace(/\s*[|•]\s*/g, " · ")
    .replace(/\s+/g, " ")
    .replace(/^[\s·:\-–—]+|[\s·:\-–—]+$/g, "")
    .toLowerCase();
}

const isClip = (e) => Boolean(e.clip);
const isOwn = (e) => e.origin === "attestation" || e.origin === "manual";

/* Written examples first, clips last: a clip is the least legible way to meet a sentence. */
function orderedExamples(s) {
  const items = s.examples.map((e, at) => ({ e, at }));
  return [...items.filter(({ e }) => !isClip(e)), ...items.filter(({ e }) => isClip(e))];
}

/* A sentence you supplied is shown once, in its sense. "Where you met it" keeps only the ones no
   example was drawn from. */
function looseAttestations(x) {
  const used = new Set(x.senses.flatMap((s) => s.examples.map((e) => e.sourceAttestationId).filter(Boolean)));
  return x.attestations.filter((a) => !a.id || !used.has(a.id));
}

const senseName = (s) => (s.domain ? `${s.emoji ? `${s.emoji} ` : ""}${s.domain}` : "");

function clipLine(e) {
  const source = [quietTitle(e.clip.title), e.clip.channel ? e.clip.channel.toLowerCase() : null].filter(Boolean).join(" · ");
  return `
    <button class="clip-line" data-clip="1" aria-label="Play the clip">
      <span class="pl">${ICON.play}</span><span class="src">${esc(source)}</span>
    </button>`;
}

function pictureFrame(im) {
  return `
    <figure class="sense-image">
      <button class="sense-image-frame" data-picture aria-label="Open the picture"><img src="${im.src}" alt="" loading="lazy"></button>
    </figure>`;
}

function attestationBlock(a) {
  return `
    <div class="att${a.photo ? " has-photo" : ""}">
      ${a.photo ? `<button class="att-photo" data-picture aria-label="Open the photo"><img src="${a.photo}" alt=""></button>` : ""}
      <div class="att-text">
        <p class="t">${spoken(esc(a.text), say(a.text))}</p>
        ${a.translation ? `<p class="tr">${spoken(esc(a.translation), sayTranslation(a.translation))}</p>` : ""}
        <p class="src">
          ${a.sourceTitle ? (a.sourceUrl ? `<a href="${a.sourceUrl}">${esc(a.sourceTitle)}</a>` : `<span>${esc(a.sourceTitle)}</span>`) : ""}
          <span class="when">${esc(a.capturedAt)}</span>
        </p>
      </div>
    </div>`;
}

/* Which blocks a painted proposal touches. Position-based on purpose: this is a picture of the
   design, and the application computes the real thing from `diffDrafts`. */
function reviewMark(kind, index) {
  if (!state.review) return "";
  if (kind === "example" && index === 0) return " mark mark-add mark-current";
  if (kind === "example" && index === 1) return " mark mark-cut";
  if (kind === "example" && index === 2) return " mark mark-change";
  if (kind === "sense" && index === 0) return " mark mark-change";
  if (kind === "sense" && index === 1) return " mark mark-moved";
  if (kind === "note" && index === 0) return " mark mark-change";
  if (kind === "note" && index === 1) return " mark mark-cut";
  return "";
}

/* ── Page ── */

/* Every section folds on its own. Kept across re-renders per word, so opening Details stays open
   while a play button or the dock redraws the article. */
const folded = new Map();
const isFolded = (key, byDefault) => (folded.has(key) ? folded.get(key) : byDefault);

function section(key, byDefault, rail, body, extra = "") {
  const shut = isFolded(key, byDefault);
  return `
    <section class="sec${shut ? " folded" : ""}${extra}" data-fold="${esc(key)}">
      <div class="rail-l"><button class="inner sec-toggle" aria-expanded="${!shut}">
        <span class="caret">${ICON.caret}</span>${rail}
      </button></div>
      <div class="body">${body}</div>
    </section>`;
}

function exampleBlock(e, at) {
  const mark = reviewMark("example", at);
  const glyph = mark.includes("mark-add") ? "+" : mark.includes("mark-cut") ? "−" : mark ? "~" : "";
  /* The glyph is a direct child of the block and absolutely positioned — never inside the
     paragraph, which is what used to push a marked block's text right of its neighbours. */
  const text = mark.includes("mark-change")
    ? `${e.text.replace(/\.$/, "")} <span class="wd-del">un montón</span><span class="wd-ins">muchísimo</span>.`
    : e.text;
  return `
    <div class="ex${isOwn(e) ? " own" : ""}${isClip(e) ? " clip-ex" : ""}${mark}" data-record="${esc(e.id || "")}">
      ${glyph ? `<span class="mark-glyph">${glyph}</span>` : ""}
      <div class="ex-text">
        <p class="t">${spoken(text, say(e.text))}</p>
        ${e.translation ? `<p class="tr">${spoken(e.translation, sayTranslation(e.translation))}</p>` : ""}
        ${isOwn(e) ? '<p class="own-hint">your sentence</p>' : ""}
        ${e.note ? `<p class="tr ex-note">✎ ${esc(e.note)}</p>` : ""}
        ${isClip(e) ? clipLine(e) : ""}
      </div>
      <button class="ask-anchor" aria-label="Ask about this example">${ICON.ask}</button>
    </div>`;
}

function senseSection(s, i, x) {
  const mark = reviewMark("sense", i);
  const glossLine = (g) => `<div class="gloss-line"><span class="lg">${esc(g.lang)}</span><span class="tm">${g.terms.map((t) => `<b>${esc(t)}</b>`).join(" · ")}</span></div>`;
  const rail = `
    <span class="num">${state.review && mark
      ? `<span class="mark-glyph">${mark.includes("mark-moved") ? "↕" : "~"}</span>` : ""}${String(i + 1).padStart(2, "0")}</span>
    <span class="label">${senseName(s) ? esc(senseName(s)) : "Sense"}</span>
    ${state.review && mark.includes("mark-moved") ? '<span class="label mark-was">was 01</span>' : ""}`;
  const body = `
    <div class="sense-head">
      <p class="sense-def${state.review && mark.includes("mark-change") ? " field-change" : ""}">${spoken(esc(s.definition), say(s.definition))}</p>
      <button class="ask-anchor" aria-label="Ask about this meaning">${ICON.ask}</button>
    </div>
    <div class="glosses">${s.glosses.map(glossLine).join("")}</div>
    ${s.images.map(pictureFrame).join("")}
    ${orderedExamples(s).map(({ e, at }) => exampleBlock(e, at)).join("")}`;
  return section(`${x.id}:sense:${i}`, false, rail, body, mark);
}

function detailsBody(x) {
  const models = [...new Set([
    ...x.senses.flatMap((s) => s.examples.map((e) => e.modelId)),
    x.imageModelId
  ].filter(Boolean))];
  const fact = (k, v) => `<div><dt>${k}</dt><dd>${v}</dd></div>`;
  return `
    <dl class="facts">
      ${fact("id", esc(x.id))}${fact("added", esc(x.createdAt))}${fact("edited", esc(x.editedAt))}${fact("rev", x.revision)}
      ${models.length ? `<div class="wide"><dt>made with</dt><dd>${models.map(esc).join(", ")}</dd></div>` : ""}
    </dl>
    ${x.study ? `
      <div class="stats">
        <div class="stat"><div class="label">Stability</div><div class="v">${x.study.stability}<small> d</small></div></div>
        <div class="stat"><div class="label">Difficulty</div><div class="v">${x.study.difficulty}<small>/10</small></div></div>
        <div class="stat"><div class="label">Retrievability</div><div class="v">${Math.round(x.study.retrievability * 100)}<small>%</small></div></div>
        <div class="stat"><div class="label">Reps · lapses</div><div class="v">${x.study.reps}<small> · ${x.study.lapses}</small></div></div>
        <div class="stat"><div class="label">Last review</div><div class="v" style="font-size:14px">${esc(x.study.lastReview)}</div></div>
      </div>` : ""}`;
}

const dictionaryBody = (x) =>
  `<p class="hint">Looked up in the dictionaries you have switched on, when this opens. Nothing is fetched in the prototype for «${esc(x.lemma)}».</p>`;

function notesList(x) {
  return `<ul class="notes">${x.notes.map((n, i) => {
    const mark = reviewMark("note", i);
    const glyph = mark.includes("mark-add") ? "+" : mark.includes("mark-cut") ? "−" : mark ? "~" : "";
    /* A reworded note is one change with the words that moved, not a delete beside an add. */
    const body = mark.includes("mark-change")
      ? `${n.replace(/\.$/, "")} <span class="wd-del">verb</span><span class="wd-ins">verbo</span>.`
      : n;
    return `<li class="${mark.replace(" mark ", "mark ").trim()}" data-note="${i}">${
      glyph ? `<span class="mark-glyph">${glyph}</span>` : ""}${body}</li>`;
  }).join("")}</ul>`;
}

function masthead(x) {
  const place = placeLine(x);
  return `
    <div class="masthead">
      <div class="head-row">
        <div class="emoji-plate">${x.emoji || "\u{1F4C4}"}</div>
        <div class="head-text">
          <h1 class="headword">${esc(x.headword)}</h1>
          ${x.reading ? `<div class="reading">${esc(x.reading)}</div>` : ""}
          <div class="pron-row">
            ${x.ipa ? `<span class="ipa">${esc(x.ipa)}</span>` : ""}
            <button class="play" data-say="${esc(x.headword)}">${ICON.play}Listen</button>
            <span class="gram">${esc(grammarWords(x))}</span>
          </div>
        </div>
      </div>
      ${place ? `<p class="place">${esc(place)}</p>` : ""}
    </div>`;
}

/* ── the ask dock ─────────────────────────────────────────────────────
   Design §06 §7. Pinned to the bottom of the article pane and growing upward into a sheet; one
   component and one set of states at every width, because a side pane would cut the 780 px article
   column to about 400 px on the tablet this is mostly read on.

   Painted here at whichever detent `state.ask` names, the way the editor pane is painted rather
   than run: the prototype has no bundler and nothing here talks to a server. The application's
   `AskDock.tsx` is the same surface with the same classes. */
function renderAsk(x) {
  const at = state.ask || "dock";
  const thread = at === "dock" ? "" : `
    <header class="ask-head">
      <button class="ask-grab" aria-label="Expand the conversation">${ICON.chevron}</button>
      ${at === "full" ? `<span class="ask-subject"><span class="ask-emoji">${x.emoji || "📄"}</span>${esc(x.headword)}</span>` : ""}
      <span class="spacer"></span>
      <button class="link-btn">Clear</button>
      <button class="icon-btn" aria-label="Close the conversation">${ICON.close}</button>
    </header>
    <div class="ask-thread">
      <div class="ask-turn you"><span class="ask-who">you</span><p>How is this different from «el traje»?</p></div>
      <div class="ask-turn acervo">
        <span class="ask-who">${ICON.ask}</span>
        <p>${"«el traje» is any outfit or suit — a business suit, a regional costume. «el disfraz» is worn to be taken for someone else: carnival, theatre, a party. You already have «el traje» under Appearance."}</p>
      </div>
      <div class="ask-card">
        <div class="ask-card-head"><span class="ask-card-mark">✎</span>Adds the contrast with «el traje» to the notes.</div>
        <div class="ask-card-foot">
          <span class="label">1 change · notes</span>
          <span class="spacer"></span>
          <button class="tb-btn primary">Review</button>
        </div>
      </div>
      <div class="ask-followups">
        <button class="ask-followup">One more example</button>
        <button class="ask-followup">How do I remember it?</button>
      </div>
    </div>`;
  return `
    <section class="ask ask-${at}" aria-label="Conversation about ${esc(x.headword)}">
      ${thread}
      ${state.askFocus ? `<div class="ask-chips">
        <button type="button" class="ask-chip">${esc(state.askFocus)}${ICON.close}</button>
      </div>` : ""}
      <form class="ask-bar" onsubmit="return false">
        <span class="ask-mark">${ICON.ask}</span>
        <textarea class="ask-input" rows="1" aria-label="Ask about ${esc(x.headword)}"
          placeholder="Ask about ${esc(x.headword)}…"></textarea>
        <button type="submit" class="ask-send" aria-label="Ask">${ICON.send}</button>
      </form>
    </section>`;
}

function renderArticle(x, opts) {
  const meta = !opts || opts.meta !== false;
  const review = meta && state.review ? `
    <div class="review-bar">
      <span class="review-mark">✎</span>
      <span class="label">3 changes<span class="review-long"> proposed</span></span>
      <div class="review-nav">
        <button aria-label="Previous change" disabled>${ICON.chevron}</button>
        <span class="review-at">1/3</span>
        <button aria-label="Next change"><span class="review-down">${ICON.chevron}</span></button>
      </div>
      <span class="spacer"></span>
      <button class="tb-btn" id="discardBtn">Discard</button>
      <button class="tb-btn primary" id="saveProposal">Save<span class="review-long"> changes</span></button>
    </div>` : "";
  const key = (part) => `${x.id}:${part}`;
  const met = looseAttestations(x);

  /* Notes, then where you met it, then the two things you open on purpose. */
  return `
    ${review}
    ${masthead(x)}
    ${x.senses.map((s, i) => senseSection(s, i, x)).join("")}
    ${x.notes.length ? section(key("notes"), false,
      '<span class="num">✎</span><span class="label">Notes</span>', notesList(x)) : ""}
    ${met.length ? section(key("met"), false,
      '<span class="num">✳</span><span class="label">Where you met it</span>', met.map(attestationBlock).join("")) : ""}
    ${meta ? section(key("dict"), true,
      '<span class="num">❡</span><span class="label">Other dictionaries</span>', dictionaryBody(x)) : ""}
    ${meta ? section(key("details"), true,
      '<span class="num">⋯</span><span class="label">Details</span>', detailsBody(x)) : ""}`;
}

/* ── Cards ───────────────────────────────────────────────────────────────
   One sense at a time, and inside a sense one sentence at a time. The definition and its gloss stay
   at the top of every card of their sense, because a sentence is only worth reading against the
   meaning it illustrates. The picture is the part that gives way when a card is short of room; if a
   card still cannot fit — a very long sentence — that card alone scrolls, and nothing forbids it. */

function cardExample(e) {
  return `
    <div class="card-ex${isOwn(e) ? " own" : ""}${isClip(e) ? " clip-ex" : ""}">
      <p class="t">${spoken(e.text, say(e.text))}</p>
      ${e.translation ? `<p class="tr">${spoken(e.translation, sayTranslation(e.translation))}</p>` : ""}
      ${isOwn(e) ? '<p class="own-hint">your sentence</p>' : ""}
      ${isClip(e) ? clipLine(e) : ""}
    </div>`;
}

function cardsFor(x) {
  const cards = [];
  x.senses.forEach((s, i) => {
    const items = orderedExamples(s);
    const picture = s.images[0] || null;
    const anchored = picture && Number.isInteger(picture.anchor) ? picture.anchor : null;
    /* Option A puts the picture with the sentence it was drawn from; option B always opens the
       sense on it. A picture drawn from the sense alone opens the sense either way. */
    const pictureOn = (c) => Boolean(picture) && (state.pictureAt === "first" || anchored === null
      ? c === 0
      : items[c] && items[c].at === anchored);
    const glossLines = s.glosses.map((g) => `<p class="card-gloss">${s.glosses.length > 1
      ? `<span class="lg">${esc(g.lang)}</span>` : ""}${g.terms.map(esc).join(" · ")}</p>`).join("");
    const count = Math.max(items.length, 1);
    for (let c = 0; c < count; c++) {
      const item = items[c];
      cards.push({
        group: `s${i}`,
        chip: senseName(s) ? esc(senseName(s)) : String(i + 1),
        html: `
          <div class="card-sense">
            <p class="card-def">${spoken(esc(s.definition), say(s.definition))}</p>
            ${glossLines}
          </div>
          <div class="card-main">
            ${pictureOn(c) ? `<button class="card-pic" data-picture aria-label="Open the picture"><img src="${picture.src}" alt=""></button>` : ""}
            ${item ? cardExample(item.e) : ""}
          </div>
          ${count > 1 ? `<span class="card-pos">${c + 1} / ${count}</span>` : ""}`
      });
    }
  });
  if (x.notes.length) cards.push({ group: "notes", chip: "✎ Notes",
    html: `<h2 class="card-title">Notes</h2><div class="card-main top">${notesList(x)}</div>` });
  const met = looseAttestations(x);
  if (met.length) cards.push({ group: "met", chip: "✳ Met it",
    html: `<h2 class="card-title">Where you met it</h2><div class="card-main top">${met.map(attestationBlock).join("")}</div>` });
  cards.push({ group: "dict", chip: "Dictionaries",
    html: `<h2 class="card-title">Other dictionaries</h2><div class="card-main top">${dictionaryBody(x)}</div>` });
  cards.push({ group: "details", chip: "Details",
    html: `<h2 class="card-title">Details</h2><div class="card-main top">${detailsBody(x)}</div>` });
  return cards;
}

function renderCards(x) {
  const cards = cardsFor(x);
  state.card = Math.max(0, Math.min(state.card, cards.length - 1));
  const groups = [...new Map(cards.map((c, i) => [c.group, { at: cards.findIndex((d) => d.group === c.group), chip: c.chip }])).entries()];
  const current = cards[state.card].group;
  return `
    <div class="cards">
      <header class="cards-head">
        <div class="cards-word">
          <span class="cw-emoji">${x.emoji || "\u{1F4C4}"}</span>
          <h1 class="cw-headword">${esc(x.headword)}</h1>
          ${say(x.headword, "always")}
          ${x.reading ? `<span class="reading">${esc(x.reading)}</span>` : ""}
          ${x.ipa ? `<span class="ipa">${esc(x.ipa)}</span>` : ""}
        </div>
        <nav class="cards-nav" aria-label="Senses and sections">
          ${groups.map(([group, g]) => `<button class="cards-chip${group === current ? " on" : ""}${group.startsWith("s") ? "" : " aside"}"
            data-go="${g.at}" data-group="${group}">${g.chip}</button>`).join("")}
        </nav>
      </header>
      <div class="cards-stage">
        <div class="cards-track" id="cardsTrack">
          ${cards.map((c, i) => `<article class="card" data-group="${c.group}" aria-label="Card ${i + 1} of ${cards.length}">${c.html}</article>`).join("")}
        </div>
        <button class="cards-edge prev" data-step="-1" aria-label="Previous card">${ICON.back}</button>
        <button class="cards-edge next" data-step="1" aria-label="Next card">${ICON.back}</button>
      </div>
    </div>`;
}

function wireCards() {
  const track = $("#cardsTrack");
  if (!track) return;
  track.scrollLeft = state.card * track.clientWidth;
  let frame = 0;
  track.addEventListener("scroll", () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => syncCard(track));
  });
  syncCard(track);
}

function syncCard(track) {
  const at = Math.round(track.scrollLeft / Math.max(track.clientWidth, 1));
  const card = track.children[at];
  if (!card) return;
  state.card = at;
  const nav = $(".cards-nav");
  nav.querySelectorAll(".cards-chip").forEach((chip) => {
    const on = chip.dataset.group === card.dataset.group;
    chip.classList.toggle("on", on);
    if (on) nav.scrollTo({ left: chip.offsetLeft - (nav.clientWidth - chip.offsetWidth) / 2, behavior: "smooth" });
  });
  $(".cards-edge.prev").disabled = at === 0;
  $(".cards-edge.next").disabled = at === track.children.length - 1;
}

function goCard(at) {
  const track = $("#cardsTrack");
  if (!track) return;
  const to = Math.max(0, Math.min(at, track.children.length - 1));
  track.scrollTo({ left: to * track.clientWidth, behavior: "smooth" });
}

/* Cards is the default where a word is glanced at — a phone, a tablet, anything without hover — and
   Page where there is a mouse. Settings will own this; here it follows the preview frame. */
function currentView() {
  if (state.view) return state.view;
  const touch = document.body.classList.contains("phone") || document.body.classList.contains("tablet")
    || window.matchMedia("(hover: none)").matches;
  return touch ? "cards" : "page";
}

/* ── YAML projection ─────────────────────────────────────────────────── */

function yamlFor(x) {
  const q = (v) => {
    if (v === null || v === undefined) return "null";
    const s = String(v);
    return /^[\w .,;:’'ºª/()-]+$/u.test(s) && !/^(true|false|null|yes|no)$/i.test(s) && !/^[\d.]+$/.test(s) && !s.includes(": ")
      ? s : JSON.stringify(s);
  };
  const L = [];
  L.push(`# ${x.headword} — ${langOf(x.language).name}`);
  L.push(`id: ${x.id}`);
  L.push(`language: ${x.language}`);
  L.push(`headword: ${q(x.headword)}`);
  L.push(`lemma: ${q(x.lemma)}`);
  if (x.reading) L.push(`reading: ${q(x.reading)}`);
  L.push(`pos: ${x.pos}`);
  if (x.gender) L.push(`gender: ${x.gender}`);
  L.push(`register: ${x.register || "null"}`);
  if (x.dialect) L.push(`dialect: ${x.dialect}`);
  L.push(`emoji: ${q(x.emoji)}`);
  L.push(`status: ${x.status}`);
  L.push(`topics: [${x.topics.join(", ")}]`);
  L.push(`shortGloss: ${x.shortGloss ? q(x.shortGloss) : "null            # null = derived from sense 1"}`);
  if (x.notes.length) {
    L.push("notes:");
    x.notes.forEach((n) => L.push(`  - ${q(strip(n))}`));
  } else L.push("notes: []");
  L.push("senses:");
  x.senses.forEach((s, i) => {
    L.push(`  - order: ${i}`);
    L.push(`    definition: ${q(s.definition)}`);
    L.push(`    definitionLang: ${s.definitionLang}`);
    if (s.domain) L.push(`    domain: ${s.domain}`);
    if (s.emoji) L.push(`    emoji: ${q(s.emoji)}`);
    L.push("    glosses:");
    s.glosses.forEach((g) => L.push(`      - { lang: ${g.lang}, terms: [${g.terms.map(q).join(", ")}] }`));
    L.push("    examples:");
    s.examples.forEach((e) => {
      L.push(`      - text: ${q(strip(e.text))}`);
      if (e.translation) L.push(`        translation: ${q(strip(e.translation))}`);
      L.push(`        origin: ${e.origin}`);
      if (e.modelId) L.push(`        modelId: ${e.modelId}`);
    });
  });
  if (x.attestations.length) {
    L.push("attestations:");
    x.attestations.forEach((a) => {
      L.push(`  - text: ${q(a.text)}          # verbatim, never rewritten`);
      if (a.translation) L.push(`    translation: ${q(a.translation)}`);
      L.push(`    sourceKind: ${a.sourceKind}`);
      if (a.sourceTitle) L.push(`    sourceTitle: ${q(a.sourceTitle)}`);
      if (a.sourceUrl) L.push(`    sourceUrl: ${a.sourceUrl}`);
      L.push(`    capturedAt: ${q(a.capturedAt)}`);
    });
  }
  return L.join("\n");
}

const YAML_TEMPLATE = `# New entry — fill in what you know, leave the rest.
language: es
headword: ""
lemma: ""
pos: noun            # noun verb adj adv phrase idiom expression
gender: null         # masculine feminine — Spanish nouns only
register: neutral    # neutral formal colloquial slang vulgar
emoji: ""
status: inbox
topics: []           # e.g. [food, travel]
shortGloss: null     # null = derived from the first gloss below
notes: []
senses:
  - order: 0
    definition: ""             # in the target language
    definitionLang: es
    glosses:
      - { lang: en, terms: [""] }
    examples:
      - text: ""
        translation: ""
        origin: manual
attestations: []     # the sentence you actually met it in, verbatim
`;

function highlight(yaml) {
  return esc(yaml)
    .replace(/(#.*)$/gm, '<span class="y-com">$1</span>')
    .replace(/^(\s*)(-?\s*)([A-Za-z_][\w]*)(:)/gm, '$1<span class="y-dash">$2</span><span class="y-key">$3</span>$4')
    .replace(/(:\s)(&quot;[^&]*?&quot;)/g, '$1<span class="y-str">$2</span>')
    .replace(/(:\s)(-?\d+(?:\.\d+)?)$/gm, '$1<span class="y-num">$2</span>');
}


function renderYaml(x) {
  const yaml = yamlFor(x);
  return `
    <div class="code-wrap">
      <div class="code-head">
        <span class="label">${esc(x.headword)}.yaml</span>
        <span class="spacer"></span>
        <span class="label">read-only — press Edit to change</span>
      </div>
      ${editorSurface("view", yaml)}
    </div>`;
}

/* Set in Settings in the application; here they are prototype switches so both looks can be seen.
   Wrapping is the default: these documents are mostly prose, and a definition running off the right
   edge could previously be neither read nor scrolled to. */
let editorWrap = true;
let editorNumbers = false;

/* The application edits with CodeMirror, which needs a bundler this prototype deliberately does not
   have. So this is a *picture* of that editor — the same palette, the same mono measure, the same
   gutter — and not an editable one. Typing is the one thing you cannot try here; everything the
   prototype exists to show, you can. */
function editorSurface(id, text) {
  const lines = text.split("\n");
  return `
    <div class="code-scroll${editorWrap ? " wrap" : ""}${editorNumbers ? " numbered" : ""}" id="${id}Surface">
      <div class="cm-mock">
        ${editorNumbers ? `<div class="cm-mock-gutter">${lines.map((_, i) => `<span>${i + 1}</span>`).join("")}</div>` : ""}
        <div class="cm-mock-content">${lines.map((line) => `<div class="cm-mock-line">${highlight(line) || "&nbsp;"}</div>`).join("")}</div>
      </div>
    </div>`;
}

/* keeps the gutter, the highlight layer and the textarea in lockstep */
/* Nothing to keep in step: the surface is a picture, so it reports its own text and no more. */
function wireSurface(id) {
  const surface = document.getElementById(`${id}Surface`);
  return { get value() { return [...surface.querySelectorAll(".cm-mock-line")].map((n) => n.textContent).join("\n"); } };
}

function renderEdit(x) {
  const yaml = yamlFor(x);
  return `
    <section class="composer" aria-label="Edit ${esc(x.headword)}">
      <div class="composer-head">
        <h2>${esc(x.headword)}</h2>
        <span class="label">${esc(x.headword)}.yaml</span>
        <span class="spacer"></span>
        <button class="icon-btn" id="closeEdit" aria-label="Close">${ICON.close}</button>
      </div>
      <div class="composer-body fill">
        <div class="code-wrap">${editorSurface("edit", yaml)}</div>
      </div>
      <div class="composer-actions">
        <div id="validation"></div>
        <div class="composer-buttons">
          <span class="spacer"></span>
          <button class="tb-btn" id="cancelEdit">Cancel</button>
          <button class="tb-btn primary" id="saveEdit">Save</button>
        </div>
      </div>
    </section>`;
}

/* ── validation stub ─────────────────────────────────────────────────── */

function validate(text) {
  const problems = [];
  const lines = text.split("\n");
  const has = (k) => new RegExp(`^${k}:`, "m").test(text);
  ["language", "headword", "pos", "senses"].forEach((k) => { if (!has(k)) problems.push({ line: null, msg: `required key <code>${k}</code> is missing` }); });
  const hw = text.match(/^headword:\s*(.*)$/m);
  if (hw && /^(""|''|null)?\s*(#.*)?$/.test(hw[1].trim())) problems.push({ line: lines.findIndex((l) => l.startsWith("headword:")) + 1, msg: "<code>headword</code> is empty" });
  const pos = text.match(/^pos:\s*([\w-]+)/m);
  if (pos && !["noun", "verb", "adj", "adv", "phrase", "idiom", "expression"].includes(pos[1]))
    problems.push({ line: lines.findIndex((l) => l.startsWith("pos:")) + 1, msg: `<code>${esc(pos[1])}</code> is not a valid part of speech` });
  lines.forEach((l, i) => { if (/\t/.test(l)) problems.push({ line: i + 1, msg: "tab character — YAML needs spaces" }); });
  const def = text.match(/definition:\s*(.*)$/m);
  if (def && /^(""|''|)\s*(#.*)?$/.test(def[1].trim())) problems.push({ line: lines.findIndex((l) => /definition:/.test(l)) + 1, msg: "the first sense has an empty <code>definition</code>" });
  return problems;
}

function showValidation(target, problems) {
  const box = $(target);
  if (!box) return;
  box.innerHTML = problems.length
    ? `<div class="validation bad"><b>${problems.length} problem${problems.length === 1 ? "" : "s"} — nothing was saved</b>
        <ul>${problems.map((p) => `<li>${p.line ? `line ${p.line}: ` : ""}${p.msg}</li>`).join("")}</ul></div>`
    : '<div class="validation ok"><b>Valid.</b> The entry matches the Acervo schema.</div>';
  return problems.length === 0;
}

/* ── add sheet ───────────────────────────────────────────────────────── */

let addTab = "capture";
/* What the last Process produced. Null until something has been proposed — the Article tab has
   nothing to render before that, and says so rather than showing an empty entry. */
let addDraft = null;

/* The server reports on health what it builds entries with, and whether it can. In the application
   that is a fetch; here it is `?capture=off`, so the refusal can be seen. Off is not a mode anyone
   chooses — it is a provider whose key is missing — and the point of drawing it is that the button
   is dead *with a reason* rather than live and failing when it is finally pressed. */
let captureBlocked = null;

function renderSheet() {
  const host = $("#composer");
  host.innerHTML = `
    <section class="composer" aria-label="Add a word">
      <div class="composer-head">
        <h2>Add a word</h2>
        <span class="spacer"></span>
        <div class="seg">
          <button data-tab="capture" class="${addTab === "capture" ? "on" : ""}">Capture</button>
          <button data-tab="article" class="${addTab === "article" ? "on" : ""}">Article</button>
          <button data-tab="yaml" class="${addTab === "yaml" ? "on" : ""}">YAML</button>
        </div>
        <button class="icon-btn" id="closeSheet" aria-label="Close">${ICON.close}</button>
      </div>
        ${addTab === "capture" ? `
      <div class="composer-body">
          <label class="label" for="captureText">Paste a word, or the sentence you met it in</label>
          <textarea class="capture-area" id="captureText" style="margin-top:8px" placeholder="Se pican las verduras en dados de un centímetro y se reservan."></textarea>

          <label class="label" for="captureWord" style="margin-top:14px">Which word? <span class="opt">optional</span></label>
          <input class="capture-word" id="captureWord" placeholder="picar">

          <p class="hint">Share the whole sentence — the word is picked out for you unless you name it above, and the sentence is kept as the place you met it. The entry is built for review and lands in <b>Inbox</b>. Nothing is generated in this prototype.</p>

          <details class="fold capture-fold">
            <summary><span class="caret">${ICON.caret}</span><span class="label">Where it came from, and what to ask for</span></summary>
            <div class="fold-body capture-details">
              <label class="label" for="captureUrl">Source link</label>
              <input id="captureUrl" placeholder="https://example.com/receta">
              <label class="label" for="captureTitle">Where it came from</label>
              <input id="captureTitle" placeholder="Receta — pisto manchego">
              <label class="label" for="captureNote">Anything to ask the generator</label>
              <input id="captureNote" placeholder="contrast it with picante">
            </div>
          </details>
      </div>
      <div class="composer-actions">
        ${captureBlocked ? `<div class="validation bad" role="alert">
          <b>This server cannot build entries right now.</b>
          <span>It is set to ${captureBlocked.provider} with the model ${captureBlocked.model},
            and ${captureBlocked.reason}. You can still write the entry yourself.</span>
        </div>` : ""}
        <div class="composer-buttons">
          <span class="spacer"></span>
          <button class="tb-btn" id="switchYaml">Write YAML instead</button>
          <button class="tb-btn primary" id="processBtn" ${captureBlocked ? "disabled" : ""}>Process</button>
        </div>
      </div>`
        : addTab === "article" ? `
      <div class="composer-body">
        ${addDraft
          ? `<div class="article-preview">${renderArticle(addDraft, { meta: false })}</div>`
          : `<p class="empty">Nothing to preview yet — process a capture, or write the document yourself.</p>`}
      </div>
      <div class="composer-actions">
        <div class="composer-buttons">
          <span class="spacer"></span>
          <button class="tb-btn" id="closeSheet2">Cancel</button>
          <button class="tb-btn" id="switchYaml">Edit YAML</button>
          <button class="tb-btn primary" id="saveDraft" ${addDraft ? "" : "disabled"}>Save</button>
        </div>
      </div>`
        : `
      <div class="composer-body fill">
        <div class="code-wrap">
          <div class="code-head"><span class="label">new-entry.yaml</span></div>
          ${editorSurface("new", YAML_TEMPLATE)}
        </div>
      </div>
      <div class="composer-actions">
        <div id="newValidation"></div>
        <div class="composer-buttons">
          <span class="spacer"></span>
          <button class="tb-btn" id="closeSheet2">Cancel</button>
          <button class="tb-btn primary" id="saveNew">Validate &amp; save</button>
        </div>
      </div>`}
    </section>`;
  wireSheet();
}

function openSheet(tab) { addTab = tab || "capture"; addDraft = null; state.add = true; render(); }
function closeSheet()   { state.add = false; $("#composer").innerHTML = ""; render(); }

/* ── toast ───────────────────────────────────────────────────────────── */

let toastTimer;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg; t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2200);
}

/* ── render ──────────────────────────────────────────────────────────── */

function render() {
  /* Reading a word on a phone or tablet does not need the topic strip, and it cost a whole row. */
  $(".app").classList.toggle("article-open", Boolean((state.openId || state.openExt) && !state.add));
  $("#main").classList.remove("cards-on");
  renderRail();
  renderLangButton();
  const main = $("#pane");
  const x = state.openId ? LEXEMES.find((y) => y.id === state.openId) : null;

  // A composer owns the height and scrolls itself, so the region around it must not also scroll.
  const composing = state.add || Boolean(x && state.mode === "edit");
  $("#main").classList.toggle("composing", composing);
  $("#paneWrap").style.display = composing ? "none" : "";
  $("#composer").style.display = composing ? "" : "none";
  if (state.add) { renderSheet(); document.title = "Add a word — Acervo"; return; }
  if (x && state.mode === "edit") {
    $("#composer").innerHTML = renderEdit(x);
    wireEditor();
    document.title = `${x.headword} — Acervo`;
    return;
  }
  $("#composer").innerHTML = "";

  const ext = state.openExt ? externalOf(state.openExt) : null;
  if (ext) {
    // An external entry replaces the list the way one of yours does, and reads in the same column.
    $("#artBar").style.display = "";
    $("#artBar").innerHTML = `<button class="icon-btn" id="backBtn" aria-label="Back to the list">${ICON.back}</button>`
      + '<span class="label">Other dictionaries</span><span class="spacer"></span>';
    main.innerHTML = renderExternalArticle(ext);
    document.title = `${ext.word} — Acervo`;
    return;
  }
  if (!x) {
    $("#artBar").style.display = "none";
    main.innerHTML = renderList();
  } else {
    const view = state.mode === "read" ? currentView() : null;
    $("#artBar").style.display = "";
    $("#artBar").innerHTML = `
      <button class="icon-btn" id="backBtn" aria-label="Back to the list">${ICON.back}</button>
      <span class="label art-where">${esc(state.topic === "all" ? "All words" : state.topic === "inbox" ? "Inbox" : topicOf(state.topic).name)}</span>
      <span class="spacer"></span>
      <div class="seg">
        <button data-view="page" class="${view === "page" ? "on" : ""}">Page</button>
        <button data-view="cards" class="${view === "cards" ? "on" : ""}">Cards</button>
        <button data-mode="yaml" class="${state.mode === "yaml" ? "on" : ""}">YAML</button>
      </div>
      <button class="icon-btn" id="editBtn" aria-label="Edit as YAML" title="Edit as YAML">${ICON.pencil}</button>
      <button class="icon-btn" id="delBtn" aria-label="Delete" title="Delete">${ICON.trash}</button>`;
    // Editing is a composer above, so only reading and the read-only projection get here.
    main.innerHTML = view === "cards" ? renderCards(x) : view === "page" ? renderArticle(x) : renderYaml(x);
    // The conversation belongs to Page: an edit that reorders senses needs every sense in view.
    $("#askSlot").innerHTML = view === "page" ? renderAsk(x) : "";
    $("#main").classList.toggle("cards-on", view === "cards");
    // At its largest the conversation takes the pane: the article is not drawn, rather than left as
    // a one-line strip above the sheet.
    $("#paneWrap").classList.toggle("ask-only", state.ask === "full" && view === "page");
    if (view === "cards") wireCards();
  }
  document.title = x ? `${x.headword} — Acervo` : "Acervo";
}

/* ── wiring ──────────────────────────────────────────────────────────── */

function wireEditor() {
  const area = wireSurface("edit");
  $("#closeEdit").onclick = () => { state.mode = "read"; render(); };
  $("#cancelEdit").onclick = () => { state.mode = "read"; render(); };
  $("#saveEdit").onclick = () => {
    const ok = showValidation("#validation", validate(area.value));
    if (ok) { toast("Saved — prototype only, nothing was written"); state.mode = "read"; setTimeout(render, 250); }
  };
}

function wireSheet() {
  $("#composer").querySelectorAll("[data-tab]").forEach((b) => { b.onclick = () => { addTab = b.dataset.tab; renderSheet(); }; });
  const close = () => closeSheet();
  const c1 = $("#closeSheet"), c2 = $("#closeSheet2");
  if (c1) c1.onclick = close;
  if (c2) c2.onclick = close;
  const sw = $("#switchYaml"); if (sw) sw.onclick = () => { addTab = "yaml"; renderSheet(); };
  const pb = $("#processBtn");
  // The real app calls the capture route and lands on the rendered proposal. Here there is nothing
  // to call, so a canned entry stands in for one — the point being the surface, not the generation.
  if (pb) pb.onclick = () => {
    addDraft = LEXEMES[0];
    addTab = "article";
    renderSheet();
    toast("Generation is not wired up in this prototype — showing a stand-in entry");
  };
  const sd = $("#saveDraft");
  if (sd) sd.onclick = () => { toast("Saved to Inbox — prototype only"); setTimeout(closeSheet, 500); };
  if ($("#newArea")) {
    const na = wireSurface("new");
    $("#saveNew").onclick = () => {
      if (showValidation("#newValidation", validate(na.value))) { toast("Saved to Inbox — prototype only"); setTimeout(closeSheet, 500); }
    };
  }
}

document.addEventListener("focusin", (ev) => {
  // Focusing the composer opens the sheet to the half detent, which is where a phone starts.
  if (ev.target.closest(".ask-input") && state.ask === "dock") { state.ask = "open"; render(); }
});

document.addEventListener("click", (ev) => {
  const t = ev.target;
  const hit = (sel) => t.closest(sel);

  const fold = hit(".sec-toggle");
  if (fold) {
    const sec = fold.closest(".sec");
    const shut = !sec.classList.contains("folded");
    sec.classList.toggle("folded", shut);
    fold.setAttribute("aria-expanded", String(!shut));
    folded.set(sec.dataset.fold, shut);
    return;
  }
  const viewBtn = hit("[data-view]");
  if (viewBtn) { state.mode = "read"; state.view = viewBtn.dataset.view; render(); $("#main").scrollTop = 0; return; }
  const goBtn = hit("[data-go]");
  if (goBtn) { goCard(Number(goBtn.dataset.go)); return; }
  const stepBtn = hit("[data-step]");
  if (stepBtn) { goCard(state.card + Number(stepBtn.dataset.step)); return; }
  if (hit("[data-picture]")) { toast("The picture dialog is out of scope for this spike"); return; }

  const topicBtn = hit("[data-topic]");
  if (topicBtn) { state.topic = topicBtn.dataset.topic; state.openId = null; state.query = ""; $("#q").value = ""; $("#search").classList.remove("searching"); render(); return; }

  const sortBtn = hit("[data-sort]");
  if (sortBtn) { state.sort = sortBtn.dataset.sort; render(); return; }

  const openBtn = hit("[data-open]");
  if (openBtn) { state.openId = openBtn.dataset.open; state.openExt = null; state.mode = "read"; state.card = 0; render(); $("#main").scrollTop = 0; return; }

  const extBtn = hit("[data-ext]");
  if (extBtn) { state.openExt = extBtn.dataset.ext; state.openId = null; render(); $("#main").scrollTop = 0; return; }

  /* The dock's three detents, so the design can actually be looked at at each of them. Focusing
     the composer opens it, the grabber steps it, and the close button returns it to a bar — the
     same transitions `AskDock.tsx` makes. Nothing here talks to a server. */
  if (hit(".ask-grab")) { state.ask = state.ask === "full" ? "open" : "full"; render(); return; }
  if (hit(".ask .icon-btn")) { state.ask = "dock"; render(); return; }
  if (hit(".ask-send")) { toast("One turn of conversation — not wired up in the prototype"); return; }
  if (hit("#discardBtn")) { state.review = false; render(); return; }
  if (hit("#saveProposal")) { state.review = false; toast("Saved to the server — not wired up in the prototype"); render(); return; }
  // The card's Review button is what puts the article into the marked state.
  if (hit(".ask-card .tb-btn")) { state.review = true; state.ask = "dock"; render(); $("#main").scrollTop = 0; return; }
  if (hit(".ask-chip")) { state.askFocus = null; render(); return; }
  if (hit(".ask-anchor")) {
    const section = t.closest(".sec");
    const number = section ? section.querySelector(".num")?.textContent?.trim() : null;
    state.askFocus = number ? `sense ${Number(number)}` : "this block";
    state.ask = "open";
    render();
    return;
  }

  const jump = hit("[data-jump]");
  if (jump) { const target = document.getElementById(jump.dataset.jump);
              if (target) target.scrollIntoView({ behavior: "smooth", block: "start" }); return; }

  if (hit("#extAdd")) { toast("Builds the entry from what you are reading — not wired up in the prototype"); return; }
  if (hit("#onlineBtn")) { state.onlineDone = true; render(); return; }

  if (hit("#scopeBtn")) { $("#scopeMenu").classList.toggle("open"); return; }
  const scopeItem = hit("[data-scope]");
  if (scopeItem) {
    state.scope[scopeItem.dataset.scope] = scopeItem.checked;
    scopeItem.closest("label").classList.toggle("on", scopeItem.checked);
    $("#scopeBtn").textContent = `yours +${Object.values(state.scope).filter(Boolean).length}`;
    render(); return;
  }
  if (!hit("#scopeMenu")) $("#scopeMenu").classList.remove("open");

  if (hit("#backBtn")) { state.openId = null; state.openExt = null; render(); return; }

  const modeBtn = hit("[data-mode]");
  if (modeBtn) { state.mode = modeBtn.dataset.mode; render(); return; }

  if (hit("#editBtn")) { state.mode = "edit"; render(); return; }
  if (hit("#delBtn"))  { toast("Delete writes a tombstone — not wired up in the prototype"); return; }

  const say = hit("[data-say]");
  if (say) {
    say.classList.add("playing");
    setTimeout(() => say.classList.remove("playing"), 1100);
    toast(`♪ ${say.dataset.say}`);
    return;
  }
  if (hit("[data-clip]")) { toast("Opens the clip dialog — removing a clip moves there"); return; }

  if (hit("#addBtn")) { openSheet("capture"); return; }

  if (hit("#langBtn")) { $("#langMenu").classList.toggle("open"); return; }
  const langItem = hit("[data-lang]");
  if (langItem) {
    state.lang = langItem.dataset.lang; state.topic = "all"; state.openId = null;
    $("#langMenu").classList.remove("open"); render(); return;
  }
  $("#langMenu").classList.remove("open");
});

$("#q").addEventListener("input", (ev) => {
  state.query = ev.target.value;
  state.openId = null;
  state.openExt = null;
  // ⏎ is the only thing that reaches an online source, so typing always puts that back.
  state.onlineDone = false;
  $("#search").classList.toggle("searching", state.query.trim().length > 0);
  
render();
});

document.addEventListener("keydown", (ev) => {
  if ((ev.metaKey || ev.ctrlKey) && ev.key === "k") { ev.preventDefault(); $("#q").focus(); $("#q").select(); }
  const typing = ev.target.closest && ev.target.closest("input, textarea, [contenteditable]");
  const reading = state.openId && !state.add && state.mode === "read";
  /* Select all selects the word, not the application around it: copying an article somewhere else
     is worth keeping, and the top bar, the Add button and the dock are not part of it. */
  if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "a" && reading && !typing) {
    ev.preventDefault();
    const target = currentView() === "cards" ? $("#cardsTrack").children[state.card] : $("#pane");
    const range = document.createRange();
    range.selectNodeContents(target);
    getSelection().removeAllRanges();
    getSelection().addRange(range);
    return;
  }
  if ((ev.key === "ArrowLeft" || ev.key === "ArrowRight") && reading && !typing && currentView() === "cards") {
    ev.preventDefault();
    goCard(state.card + (ev.key === "ArrowRight" ? 1 : -1));
    return;
  }
  // Innermost first: leave what you are composing before leaving the entry it belongs to.
  if (ev.key === "Escape") {
    if (state.add) closeSheet();
    else if (state.mode === "edit") { state.mode = "read"; render(); }
    else if (state.openExt) { state.openExt = null; render(); }
    else if (state.openId) { state.openId = null; render(); }
  }
});

/* ── device preview harness (prototype only) ─────────────────────────── */
function setTheme(mode) {
  if (mode === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = mode;
  $("#themeBtn").textContent = mode === "auto" ? "Theme" : mode === "dark" ? "Dark" : "Light";
  $("#themeBtn").classList.toggle("on", mode !== "auto");
}

function paintSwitches() {
  $("#viewBtn").textContent = `View: ${state.view || "auto"}`;
  $("#viewBtn").classList.toggle("on", Boolean(state.view));
  $("#picBtn").textContent = state.pictureAt === "first" ? "Picture: first" : "Picture: its sentence";
  $("#trBtn").classList.toggle("on", state.sayTranslations);
}

$("#harness").addEventListener("click", (ev) => {
  const b = ev.target.closest("button"); if (!b) return;
  if (b.id === "themeBtn") {
    const now = document.documentElement.dataset.theme;
    setTheme(now === "dark" ? "light" : now === "light" ? "auto" : "dark");
    return;
  }
  /* Stand-ins for Settings ▸ default article view, and the two open questions of the spike. */
  if (b.id === "viewBtn") { state.view = state.view === null ? "page" : state.view === "page" ? "cards" : null; }
  else if (b.id === "picBtn") { state.pictureAt = state.pictureAt === "first" ? "anchor" : "first"; }
  else if (b.id === "trBtn") { state.sayTranslations = !state.sayTranslations; }
  else if (b.dataset.frame) {
    document.body.className = b.dataset.frame === "desktop" ? "" : `framed ${b.dataset.frame}`;
    $("#harness").querySelectorAll("button[data-frame]").forEach((x) => x.classList.toggle("on", x === b));
  }
  paintSwitches();
  render();
});

/* Listen to whatever is selected, in the language the article is in. A floating button above the
   selection, because a play button on every phrase would be noise and a selection is already the
   gesture for "this bit". */
const selectionSay = el(`<button class="sel-say" aria-label="Listen to the selection">${ICON.play}<span>Listen</span></button>`);
selectionSay.hidden = true;
document.body.appendChild(selectionSay);
// Pressing it must not collapse the selection it is about to read.
selectionSay.addEventListener("mousedown", (ev) => ev.preventDefault());
document.addEventListener("selectionchange", () => {
  const selection = getSelection();
  const text = selection && !selection.isCollapsed ? selection.toString().trim() : "";
  if (!text || !state.openId || state.mode !== "read" || !$("#pane").contains(selection.anchorNode)) {
    selectionSay.hidden = true;
    return;
  }
  const box = selection.getRangeAt(0).getBoundingClientRect();
  selectionSay.hidden = false;
  selectionSay.style.left = `${Math.min(Math.max(box.left + box.width / 2, 60), innerWidth - 60)}px`;
  selectionSay.style.top = `${Math.max(box.top, 70)}px`;
  selectionSay.dataset.say = text.length > 160 ? `${text.slice(0, 160)}…` : text;
});

/* deep link — ?open=<id|headword>&mode=read|yaml keeps screenshots reproducible */
const params = new URLSearchParams(location.search);
if (params.get("open")) {
  const want = params.get("open").toLowerCase();
  const hit = LEXEMES.find((x) => x.id === want || x.headword.toLowerCase() === want || x.lemma.toLowerCase() === want);
  const mode = params.get("mode");
  if (hit) { state.openId = hit.id; state.lang = hit.language; state.mode = mode === "yaml" || mode === "edit" ? mode : "read"; }
  // `ask=half|full` and `review=1` make the conversation and a proposal under review reachable for
  // a screenshot, the way `mode` already does for the editor.
  const ask = params.get("ask");
  // `half` is the old name for `open`, kept because deep links to it exist in the design notes.
  if (ask === "open" || ask === "half") state.ask = "open";
  if (ask === "full") state.ask = "full";
  if (params.get("focus")) state.askFocus = params.get("focus");
  if (params.get("review") === "1") state.review = true;
}
if (params.get("topic")) state.topic = params.get("topic");
if (params.get("view") === "page" || params.get("view") === "cards") state.view = params.get("view");
if (params.get("card")) state.card = Number(params.get("card")) || 0;
if (params.get("pic") === "first") state.pictureAt = "first";
if (params.get("tr") === "on") state.sayTranslations = true;
if (params.get("capture") === "off") {
  captureBlocked = { provider: "vertex", model: "gemini-3.7-flash", reason: "VERTEX_API_KEY is not set" };
}
if (params.get("wrap") === "off") editorWrap = false;
if (params.get("numbers") === "on") editorNumbers = true;
if (params.get("theme")) setTheme(params.get("theme"));
if (params.get("add")) openSheet(params.get("add"));
if (params.get("frame") === "phone" || params.get("frame") === "tablet") {
  const f = params.get("frame");
  document.body.className = `framed ${f}`;
  document.querySelectorAll("#harness button[data-frame]").forEach((b) => b.classList.toggle("on", b.dataset.frame === f));
}
/* `size=375x667` resizes the preview frame, so a small phone can be looked at too. */
const size = (params.get("size") || "").match(/^(\d+)x(\d+)$/);
if (size) Object.assign($(".viewport").style, { width: `${size[1]}px`, height: `${size[2]}px` });

paintSwitches();
render();
