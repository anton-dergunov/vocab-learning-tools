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
     `card` is which card Cards is showing; and `sayTranslations` puts listen buttons after
     translations too. */
  view: null,
  card: 0,
  sayTranslations: false,
  /* Loops. `loops` is whether the surface is open — it replaces the list, the way an article does —
     and `loopLayout` is the shape it takes, which is the thing being chosen between. Which loop is
     loaded and where it has got to belong to `player`, not here: they survive leaving the surface,
     because a loop keeps playing while you read a word. */
  loops: false,
  /* Which loop the surface is showing. What is *playing* is `player`'s, not this: a loop goes on
     playing while you read a word, which is most of the point of having one. */
  loopOpen: null
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
  /* File it: the Inbox tray with an arrow leaving it, so it reads as the opposite of how the word
     got there. */
  file:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 13h4l1.5 3h7l1.5-3h4"/><path d="M3 13l3-7h12l3 7v5H3z"/><path d="M12 10V2M9 5l3-3 3 3"/></svg>',
  close:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  book:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H18v14H5.5A1.5 1.5 0 0 0 4 19.5z"/><path d="M4 19.5A1.5 1.5 0 0 1 5.5 18H20v2.5H5.5"/><path d="M8 8h6"/></svg>',
  globe:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17"/><path d="M12 3.5c2.2 2.3 3.3 5.2 3.3 8.5S14.2 18.2 12 20.5c-2.2-2.3-3.3-5.2-3.3-8.5S9.8 5.8 12 3.5z"/></svg>',
  /* Asking about a word — deliberately not `✳`, which is already "where you met it". */
  ask:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 14.5A2.5 2.5 0 0 1 17.5 17H12l-4.5 3.5V17H6.5A2.5 2.5 0 0 1 4 14.5v-8A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5z"/><path d="M10.2 8.6a1.9 1.9 0 1 1 2.6 1.8c-.5.2-.8.7-.8 1.2v.3"/><path d="M12 14.2v.1"/></svg>',
  chevron:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 15l7-7 7 7"/></svg>',
  /* A clip, drawn as a strip of film: a play triangle alone reads as "audio". */
  film:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="5" width="17" height="14" rx="2"/><path d="M3.5 9h17M3.5 15h17M7.5 5v4M12 5v4M16.5 5v4M7.5 15v4M12 15v4M16.5 15v4"/></svg>',
  /* The corner arrow that says a control opens something, drawn as plainly as it can be: the pill
     it sits in is already carrying a film strip and a line of text. */
  open:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17L17 7"/><path d="M9 7h8v8"/></svg>',
  info:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5"/><path d="M12 7.6v.1"/></svg>',
  picture:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="5" width="17" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M4 16.5l4.5-4 3.5 3 3-2.5 5 4"/></svg>',
  /* The printer's ivy leaf, pointing right (❧); mirrored in CSS for ☙. Drawn, not typed, because
     Literata has no such glyph and every platform's fallback draws a different one. */
  /* U+2767 from EB Garamond (Georg Duffner, Octavio Pardo), SIL Open Font License 1.1. */
  more:   '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="5.5" cy="12" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="18.5" cy="12" r="1.7"/></svg>',
  hedera: '<svg viewBox="0 0 910 508" aria-hidden="true"><path fill="currentColor" d="M135 508Q107 508 86 489Q66 470 51 447Q35 447 18 443Q0 439 0 414Q0 382 16 350Q33 319 58 296Q83 272 107 266Q100 258 98 248Q96 239 96 229Q96 215 110 202Q124 189 146 179Q167 169 190 163Q214 157 232 157Q244 157 256 158Q269 158 281 160Q281 138 272 117Q262 96 248 82Q233 68 218 68Q206 68 200 74Q193 79 187 86Q180 94 171 101Q162 108 144 108Q113 108 92 86Q70 63 70 32Q70 18 80 9Q89 0 102 0Q110 0 114 6Q117 12 120 18Q123 24 126 28Q129 33 134 33Q139 33 142 28Q146 24 150 18Q154 12 158 7Q163 2 170 2Q212 2 246 22Q279 43 298 77Q318 111 318 150Q318 154 318 158Q317 162 317 166Q348 173 371 188Q394 202 410 216Q414 220 419 218Q424 216 420 214Q410 206 398 189Q387 172 387 153Q387 127 400 106Q412 86 433 74Q454 62 480 62Q519 62 547 78Q575 93 598 118Q620 142 640 168Q668 203 696 232Q725 260 766 260Q790 260 813 252Q836 245 851 230Q866 214 866 190Q866 157 844 134Q839 135 834 136Q830 136 826 136Q804 137 794 126Q785 114 785 96Q785 75 802 64Q819 54 840 54Q865 54 880 72Q895 91 902 118Q910 146 910 172Q910 224 886 268Q861 311 819 345Q777 379 726 403Q675 427 622 440Q568 452 520 452Q480 452 438 436Q397 421 370 391Q342 361 342 318Q342 292 358 276Q373 259 396 248Q404 244 404 242Q404 240 396 236Q377 225 356 218Q336 210 312 206Q305 238 290 266Q275 294 254 312Q234 329 208 329Q195 329 184 326Q174 323 165 319Q157 317 149 314Q141 312 133 312Q108 312 93 333Q78 354 78 380Q78 408 92 433Q107 458 130 458Q138 458 144 455Q149 452 153 448Q158 443 164 440Q170 436 178 436Q187 436 192 444Q196 453 196 462Q196 484 178 496Q159 508 135 508ZM190 286Q215 286 238 260Q260 234 272 202H254Q234 202 210 206Q186 211 169 220Q152 230 152 244Q152 260 163 273Q174 286 190 286Z"/></svg>',
  send:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12h14"/><path d="M13 6l6 6-6 6"/></svg>',
  /* The transport. Filled rather than stroked, because at 22 px a stroked triangle reads as an
     outline of a play button and every music player on the device draws a solid one. */
  pause:  '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="5.5" width="3.6" height="13" rx="1.1"/><rect x="13.4" y="5.5" width="3.6" height="13" rx="1.1"/></svg>',
  prev:   '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="5.5" y="6.5" width="2.4" height="11" rx="1"/><path d="M16.5 6.5v11L8 12z"/></svg>',
  next:   '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7.5 6.5v11L16 12z"/><rect x="16.1" y="6.5" width="2.4" height="11" rx="1"/></svg>',
  /* A loop's own mark: a beamed pair, which says music without saying "audio file". */
  note:   '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 4.2L9.2 6.4v9.05a2.9 2.9 0 1 0 1.5 2.55V9.1l6.8-1.5v5.6a2.9 2.9 0 1 0 1.5 2.55z"/></svg>',
  /* Play it again, and go on to the next one: the two glyphs every player uses, so neither needs a
     label to be understood. */
  repeat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M6 7h11a3 3 0 0 1 3 3v1"/><path d="M18 17H7a3 3 0 0 1-3-3v-1"/><path d="M8.5 4.5L6 7l2.5 2.5"/><path d="M15.5 19.5L18 17l-2.5-2.5"/></svg>',
  continue:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h11M4 12h8M4 17h8"/><path d="M16 11.5v7l5.5-3.5z" fill="currentColor" stroke-width="1"/></svg>',
  hourglass:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4h10M7 20h10"/><path d="M8 4c0 4 4 5 4 8s-4 4-4 8"/><path d="M16 4c0 4-4 5-4 8s4 4 4 8"/></svg>'
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

/**
 * Out of the Inbox and into its topics — one word, or the whole tab at once.
 *
 * The rail drops the Inbox tab once it is empty, so standing on it would leave you looking at a list
 * with no way back to itself; only the tab moves, and an open word stays open.
 */
function fileWords(ids) {
  const filing = LEXEMES.filter((x) => ids.includes(x.id) && x.status === "inbox");
  if (!filing.length) return;
  filing.forEach((x) => { x.status = "active"; });
  if (state.topic === "inbox" && !inboxCount()) state.topic = "all";
  render();
  toast(filing.length === 1 ? "Filed — it is in its topics now" : `Filed ${filing.length} words`);
}

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

  // Only the Inbox tab itself, never a search that happens to turn up unreviewed words: those rows
  // are an answer to a question, not a pile to be emptied.
  const fileable = !q && state.topic === "inbox" ? rows : [];

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
        ${fileable.length ? `<button class="sort-btn" id="fileAllBtn">File all ${fileable.length}</button>` : ""}
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
            ${fillingOf(x) ? '<span class="working-mark" role="img" aria-label="Still filling in" title="Still filling in"></span>' : ""}
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
    .replace(/[0-9#*]\u{FE0F}?\u{20E3}/gu, "")
    .replace(/\p{Extended_Pictographic}|\p{Regional_Indicator}|\p{Emoji_Presentation}|[\u{FE0F}\u{200D}\u{20E3}\u{E0020}-\u{E007F}\u{1F3FB}-\u{1F3FF}]/gu, "")
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
  /* Calm, but plainly a thing to press: an outlined pill with a film icon, in ink rather than teal.
     The channel leads — it says what kind of speech this is, which is why you would open it — and
     the video's own title follows, quieter, and is what truncation eats first. The corner arrow is
     the one mark that says this opens something rather than captioning the sentence above it. */
  const channel = e.clip.channel ? e.clip.channel.toLowerCase() : "";
  const title = quietTitle(e.clip.title);
  const parts = [];
  if (channel) parts.push(`<span class="ch">${esc(channel)}</span>`);
  if (channel && title) parts.push(" · ");
  if (title) parts.push(`<span class="ti">${esc(title)}</span>`);
  return `
    <button class="clip-line" data-clip="1" aria-label="Play the clip">
      <span class="film">${ICON.film}</span><span class="src">${parts.join("") || "clip"}</span><span class="go">${ICON.open}</span>
    </button>`;
}

/* ── the server's work on a word ──────────────────────────────────────
   A word still being filled in carries `filling`. The application reads the same states from its
   job stream; here they are a fixture, overridable with `?fill=searching|none|failed|off`. */
function fillingOf(x) {
  const asked = new URLSearchParams(location.search).get("fill");
  if (!x.filling || asked === "off") return null;
  return asked ? { ...x.filling, clips: asked } : x.filling;
}

function progressStrip(x) {
  const filling = fillingOf(x);
  if (!filling) return "";
  if (filling.clips === "failed") {
    return `<div class="progress-strip failed" role="status"><span>Couldn't search recorded speech</span>`
      + '<span class="sep">·</span><button class="strip-action">Try again</button>'
      + '<button class="strip-dismiss" aria-label="Dismiss">×</button></div>';
  }
  const phases = filling.phases.filter(([text]) => filling.clips === "searching" || !text.startsWith("Finding"));
  return `<div class="progress-strip" role="status">${phases.map(([text, now], i) =>
    `${i ? '<span class="sep">·</span>' : ""}<span${now ? ' class="now"' : ""}>${esc(text)}</span>`).join("")}</div>`;
}

function clipSlot(s, i, x) {
  const filling = fillingOf(x);
  if (!filling || s.examples.some(isClip)) return "";
  if (filling.clips === "searching") {
    return `<div class="clip-slot" role="status" aria-label="Looking for a recorded example">
      <span class="clip-slot-play"></span><span class="clip-slot-bars"><span></span><span></span><span></span></span></div>`;
  }
  if (filling.clips === "none") return '<p class="clip-none">No recorded example</p>';
  if (filling.clips === "failed" && i === 0) {
    return '<p class="clip-none failed">Couldn\'t search recorded speech <span class="sep">·</span> <button class="strip-action">Try again</button></p>';
  }
  return "";
}

function pictureFrame(im) {
  /* `drawing` stands in for a picture the queue is drawing right now: the frame holds its place and
     says so, the same on the page and on a card. */
  return im.drawing ? `
    <figure class="sense-image">
      <button class="sense-image-frame is-pending is-busy" data-picture><span class="sense-image-empty">Drawing…</span></button>
    </figure>` : `
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
        ${isOwn(e) ? '<span class="own-tag">your sentence</span>' : ""}
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
      ${s.images.length ? "" : `<button class="ask-anchor picture-anchor" data-add-picture aria-label="Add a picture" title="Add a picture">${ICON.picture}</button>`}
      <button class="ask-anchor" aria-label="Ask about this meaning">${ICON.ask}</button>
    </div>
    <div class="glosses">${s.glosses.map(glossLine).join("")}</div>
    ${s.images.map(pictureFrame).join("")}
    ${orderedExamples(s).map(({ e, at }) => exampleBlock(e, at)).join("")}
    ${clipSlot(s, i, x)}`;
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
  /* Two lines beside the plate: the word with its play button, then how it sounds and what it is.
     Where it is filed trails that second line in small mono — it says something about the word, so
     it stays in view, but it should not cost a line of its own. */
  return `
    <div class="masthead">
      <div class="head-row">
        <div class="emoji-plate">${x.emoji || "\u{1F4C4}"}</div>
        <div class="head-text">
          <div class="head-line"><h1 class="headword">${esc(x.headword)}</h1>${say(x.headword, "always head")}</div>
          ${x.reading ? `<div class="reading">${esc(x.reading)}</div>` : ""}
          <div class="pron-row">
            ${x.ipa ? `<span class="ipa">${esc(x.ipa)}</span>` : ""}
            <span class="gram">${esc(grammarWords(x))}</span>
            ${place ? `<span class="place">${esc(place)}</span>` : ""}
          </div>
        </div>
      </div>
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
      `<span class="num">${ICON.book}</span><span class="label">Other dictionaries</span>`, dictionaryBody(x)) : ""}
    ${meta ? section(key("details"), true,
      `<span class="num">${ICON.info}</span><span class="label">Details</span>`, detailsBody(x)) : ""}`;
}

/* ── Cards ───────────────────────────────────────────────────────────────
   One sense at a time, and inside a sense one sentence at a time. The definition and its gloss stay
   at the top of every card of their sense, because a sentence is only worth reading against the
   meaning it illustrates. The picture is the part that gives way when a card is short of room; if a
   card still cannot fit — a very long sentence — that card alone scrolls, and nothing forbids it. */

function cardExample(e, quoted = false) {
  return `
    <div class="card-ex${isOwn(e) ? " own" : ""}${isClip(e) ? " clip-ex" : ""}">
      <p class="t">${quoted ? '<span class="quote-mark" aria-hidden="true">“</span>' : ""}${spoken(e.text,
        (quoted ? '<span class="quote-mark" aria-hidden="true">”</span>' : "") + say(e.text))}</p>
      ${e.translation ? `<p class="tr">${spoken(e.translation, sayTranslation(e.translation))}</p>` : ""}
      ${isOwn(e) ? '<span class="own-tag">your sentence</span>' : ""}
      ${isClip(e) ? clipLine(e) : ""}
    </div>`;
}

function cardsFor(x) {
  const cards = [];
  x.senses.forEach((s, i) => {
    const items = orderedExamples(s);
    const picture = s.images[0] || null;
    const anchored = picture && Number.isInteger(picture.anchor) ? picture.anchor : null;
    /* A picture goes on the card of the sentence it was drawn from — a clip's included, so a clip
       and its picture share a card. A picture drawn from the sense alone opens the sense. */
    const spotOn = (c) => (anchored === null ? c === 0 : Boolean(items[c]) && items[c].at === anchored);
    /* A card is for reading: the picture if it exists, the page's frame while one is being drawn,
       and otherwise nothing — pictures are asked for on the page. */
    const visualAt = (c) => !spotOn(c) ? ""
      : picture && picture.drawing ? `<div class="card-frame">${pictureFrame(picture)}</div>`
      : picture ? `<div class="card-pic" role="img"><img src="${picture.src}" alt=""></div>`
      : "";
    const glossLines = s.glosses.map((g) =>
      `<p class="card-gloss"><span class="lg">${esc(g.lang)}</span>${g.terms.map(esc).join(" · ")}</p>`).join("");
    const count = Math.max(items.length, 1);
    for (let c = 0; c < count; c++) {
      const item = items[c];
      const visual = visualAt(c);
      /* Only words: an epigraph between two ivy leaves. No sentence either: the leaves alone. */
      const quoted = !visual && Boolean(item);
      const bare = !visual && !item;
      cards.push({
        group: `s${i}`,
        chip: senseName(s) ? esc(senseName(s)) : String(i + 1),
        html: `
          <div class="card-sense">
            <p class="card-def">${spoken(esc(s.definition), say(s.definition))}</p>
            ${glossLines}
          </div>
          <div class="card-main${quoted ? " quoted" : ""}${bare ? " bare" : ""}">
            ${visual}
            ${quoted ? `<span class="card-ornament above" aria-hidden="true">${ICON.hedera}</span>` : ""}
            ${item ? cardExample(item.e, quoted) : ""}
            ${quoted ? `<span class="card-ornament below" aria-hidden="true">${ICON.hedera}</span>` : ""}
            ${bare ? `<span class="card-ornament pair" aria-hidden="true">${ICON.hedera}${ICON.hedera}</span>` : ""}
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
          <div class="cw-line" data-length="${x.headword.length > 24 ? "long" : x.headword.length > 14 ? "mid" : "short"}"><h1 class="cw-headword">${esc(x.headword)}</h1>${say(x.headword, "always head")}</div>
          ${x.reading ? `<span class="reading">${esc(x.reading)}</span>` : ""}
        </div>
        <nav class="cards-nav" aria-label="Senses and sections">
          ${groups.map(([group, g], index) => `${!group.startsWith("s") && index > 0 && groups[index - 1][0].startsWith("s") ? '<span class="cards-sep" aria-hidden="true"></span>' : ""}<button class="cards-chip${group === current ? " on" : ""}${group.startsWith("s") ? "" : " aside"}"
            data-go="${g.at}" data-group="${group}">${g.chip}</button>`).join("")}
        </nav>
      </header>
      <div class="cards-stage">
        <div class="cards-track" id="cardsTrack">
          ${cards.map((c, i) => `<article class="card" data-group="${c.group}" aria-label="Card ${i + 1} of ${cards.length}">${c.html}</article>`).join("")}
        </div>
      </div>
      <div class="cards-edges">
        <button class="cards-edge prev" data-step="-1" aria-label="Previous card">${ICON.back}</button>
        <button class="cards-edge next" data-step="1" aria-label="Next card">${ICON.back}</button>
      </div>
    </div>`;
}

/* Arrows beside the column only where the margin really has room for them, measured against `.main`,
   which clips; otherwise a pair at the foot of the card. */
function placeEdges() {
  const cards = $(".cards"), main = $("#main");
  if (!cards || !main) return;
  const inner = cards.getBoundingClientRect(), outer = main.getBoundingClientRect();
  cards.classList.toggle("edges-beside", inner.left - outer.left >= 100 && outer.right - inner.right >= 100);
}
window.addEventListener("resize", placeEdges);

function wireCards() {
  const track = $("#cardsTrack");
  if (!track) return;
  placeEdges();
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

function openSheet(tab) { addTab = tab || "capture"; addDraft = null; state.loops = false; state.add = true; render(); }
function closeSheet()   { state.add = false; $("#composer").innerHTML = ""; render(); }

/* ── toast ───────────────────────────────────────────────────────────── */

let toastTimer;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg; t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2200);
}

/* ── loops ────────────────────────────────────────────────────────────────
   A loop is a rendered track over a handful of your words. The surface is an ordinary music
   player — a seekable line with a tick per word, elapsed and total, the three transport buttons,
   and two switches: play it again, and go on to the next one. The words stand where the artwork or
   the lyrics would.

   THE ONE RULE THAT IS NOT A MUSIC PLAYER'S: a translation is never drawn before it has been
   spoken. A word not yet reached shows its source and a short bar where its translation will be.
   The reveal is a pure function of the clock, so dragging backwards withholds it again — there is
   no latch to fall out of step with where the track actually is.

   The controls are a footer of a column that owns its height, never a sticky element inside a
   scroller: the words scroll and the player cannot move, so pause is always where you left it.

   There is no audio here and there will not be: the prototype has no bundler and no files. A fake
   clock stands in for the element, advanced by `requestAnimationFrame`, and everything is driven
   from it exactly as it is driven from `timeupdate` in the application. Which is the point of
   drawing this at all — how the reveal *feels* is not a question a still picture can answer.

   The application's counterparts are `LoopView.tsx`, `LoopPlayer.tsx`, `LoopBar.tsx` and
   `LoopDialog.tsx`, and `loopMomentAt` in `selectors.ts` is the derivation this repeats. */

const player = { loopId: null, at: 0, playing: false, speed: 1, frame: null, last: 0, scrubbing: false,
                 repeat: false, autoplay: false };

function loopsIn(lang) { return LOOPS.filter((l) => l.language === lang).sort((a, b) => a.position - b.position); }
function loopItemsOf(id) { return LOOP_ITEMS.filter((r) => r.loopId === id).sort((a, b) => a.position - b.position); }
const loopIsReady = (loop) => Boolean(loop.audioRef);
const loopOf = (id) => LOOPS.find((l) => l.id === id) || null;

/* A name derived from the words it teaches, because there is no title column: as many as fit, then
   a count of what is left, so two loops over the same words in a different order still read apart. */
function loopTitle(loop, limit = 3) {
  const rows = loopItemsOf(loop.id);
  if (!rows.length) return "Empty loop";
  const named = rows.slice(0, limit).map((r) => r.sourceText);
  const rest = rows.length - named.length;
  return rest > 0 ? `${named.join(", ")} +${rest}` : named.join(", ");
}

const clock = (s) => {
  const whole = Math.max(0, Math.floor(s || 0));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
};

/* When each of a word's utterances begins. A word is spoken, then its translation, then that pair
   again — `repeats` times in all, evenly `repeatSeconds` apart from the first translation. The gap
   from a word to its own translation is the recall gap and is deliberately longer, which is why it
   is stored rather than derived. `utteranceStarts` in `selectors.ts` is the same arithmetic. */
function utteranceStarts(item) {
  const known = item.repeats > 0 && item.repeatSeconds > 0 ? item.repeats * 2 : 2;
  const starts = [item.startSeconds, item.targetRevealSeconds];
  for (let index = 2; index < known; index += 1) {
    starts.push(item.targetRevealSeconds + (index - 1) * item.repeatSeconds);
  }
  return starts;
}

/* Everything the player draws at one instant. The gap after a word belongs to the word just heard,
   so a line does not go dark while its bed plays on; and `sounding` is the line most recently
   spoken rather than the one making sound this millisecond, because an utterance is about half a
   second long every four and a mark that blinked for half a second would be unreadable. */
function loopMomentAt(items, at) {
  let index = -1;
  items.forEach((item, position) => { if (at >= item.startSeconds) index = position; });
  const item = index >= 0 ? items[index] : null;
  if (!item) return { index, item: null, sounding: null, revealed: false };
  let spoken = -1;
  utteranceStarts(item).forEach((start, position) => { if (at >= start) spoken = position; });
  return {
    index, item,
    sounding: spoken < 0 ? null : spoken % 2 === 0 ? "source" : "target",
    revealed: at >= item.targetRevealSeconds
  };
}

/* ── the fake transport ── */
function loopLoad(id, { play = false, at = 0 } = {}) {
  player.loopId = id;
  player.at = at;
  if (play) loopPlay(); else loopPause();
}

function loopPlay() {
  const loop = loopOf(player.loopId);
  if (!loop || !loopIsReady(loop)) return;
  player.playing = true;
  player.last = performance.now();
  if (!player.frame) player.frame = requestAnimationFrame(loopFrame);
  paintLoops();
}

function loopPause() {
  player.playing = false;
  if (player.frame) { cancelAnimationFrame(player.frame); player.frame = null; }
  paintLoops();
}

function loopFrame(now) {
  const loop = loopOf(player.loopId);
  const total = loop ? loop.durationSeconds : 0;
  if (!player.scrubbing) player.at = Math.min(total, player.at + ((now - player.last) / 1000) * player.speed);
  player.last = now;
  paintLoops();
  if (player.at >= total) { loopEnded(); return; }
  player.frame = requestAnimationFrame(loopFrame);
}

/* What happens at the end, in this order: play it again, else play the next one, else stop. Both
   switches are off by default — a loop that ends is a loop that ends. */
function loopEnded() {
  if (player.repeat) { player.at = 0; player.last = performance.now(); player.frame = requestAnimationFrame(loopFrame); return; }
  if (player.autoplay) {
    const next = loopNeighbour(1);
    if (next) { loopLoad(next.id, { play: true }); render(); return; }
  }
  loopPause();
}

function loopNeighbour(by) {
  const queue = loopsIn(state.lang).filter(loopIsReady);
  const at = queue.findIndex((loop) => loop.id === player.loopId);
  return at < 0 ? null : queue[at + by] || null;
}

function loopSeek(seconds) {
  const loop = loopOf(player.loopId);
  if (!loop) return;
  player.at = Math.max(0, Math.min(loop.durationSeconds, seconds));
  paintLoops();
}

/* Previous behaves the way every player's does: back to the top of this word unless you press it
   just after one started, which means you meant the one before. */
function loopStep(by) {
  const loop = loopOf(player.loopId);
  if (!loop) return;
  const rows = loopItemsOf(loop.id);
  const index = loopMomentAt(rows, player.at).index;
  if (by < 0 && index >= 0 && player.at - rows[index].startSeconds > 3) { loopSeek(rows[index].startSeconds); return; }
  const want = index + by;
  if (want < 0) { loopSeek(0); return; }
  if (want >= rows.length) { loopSeek(loop.durationSeconds); return; }
  loopSeek(rows[want].startSeconds);
}

/* ── drawing ── */

function seekBar(loop, rows) {
  const ticks = rows.map((row) => `<span class="seek-tick" style="left:${(row.startSeconds / loop.durationSeconds) * 100}%"></span>`).join("");
  return `
    <div class="seek" id="seek" role="slider" aria-label="Where you are in the loop"
         aria-valuemin="0" aria-valuemax="${Math.round(loop.durationSeconds)}" tabindex="0">
      <span class="seek-track"></span>${ticks}
      <span class="seek-fill"></span><span class="seek-knob"></span>
    </div>
    <div class="seek-times"><span class="at">0:00</span><span>${clock(loop.durationSeconds)}</span></div>`;
}

function playerBlock(loop) {
  const rows = loopItemsOf(loop.id);
  return `<div class="player">
    ${seekBar(loop, rows)}
    <div class="transport">
      <button class="switch${player.repeat ? " on" : ""}" data-switch="repeat"
              aria-pressed="${player.repeat}" aria-label="Play this loop again when it ends">${ICON.repeat}</button>
      <button data-step="-1" aria-label="Previous word">${ICON.prev}</button>
      <button class="big" id="playPause" aria-label="Play">${ICON.play}</button>
      <button data-step="1" aria-label="Next word">${ICON.next}</button>
      <button class="switch${player.autoplay ? " on" : ""}" data-switch="autoplay"
              aria-pressed="${player.autoplay}" aria-label="Go on to the next loop when this one ends">${ICON.continue}</button>
    </div>
    <div class="player-bed label">${esc((loop.styleId || "no bed").replace(/-/g, " "))} · ${rows.length} words</div>
  </div>`;
}

/* One row per word. The row being taught *is* the big word — there is no second, larger copy of it
   above, so there is one thing to look at and one column to read down. */
function lyricBlock(loop) {
  return `<div class="lyric" id="lyric">${loopItemsOf(loop.id).map((row) => `
    <button class="lyric-row" data-seek="${row.startSeconds}"
            data-target="${esc(row.targetText)}">
      <span class="lyric-source">${esc(row.sourceText)}</span>
      <span class="lyric-target"><span class="lyric-held"></span></span>
    </button>`).join("")}</div>`;
}

function loopSub(loop) {
  if (!loopIsReady(loop)) return '<span class="doing">Being made…</span>';
  return `${loopItemsOf(loop.id).length} words · ${clock(loop.durationSeconds)}`;
}

function loopRow(loop) {
  const ready = loopIsReady(loop);
  const on = loop.id === player.loopId;
  return `<button class="loop-row${on ? " on" : ""}" data-loop="${loop.id}"${ready ? "" : " disabled"}>
    <span class="loop-go${ready ? "" : " pending"}">${ready ? (on && player.playing ? ICON.pause : ICON.play) : ICON.hourglass}</span>
    <span class="loop-main">
      <span class="loop-title">${esc(loopTitle(loop))}</span>
      <span class="loop-sub">${loopSub(loop)}</span>
    </span>
  </button>`;
}

function renderLoops() {
  const loops = loopsIn(state.lang);
  const open = state.loopOpen ? loopOf(state.loopOpen) : null;
  if (open) {
    return `<section class="loops">
      <div class="loops-back">
        <button class="icon-btn" id="loopBack" aria-label="Back to the loops">${ICON.back}</button>
        <span class="label">Loops</span><span class="spacer"></span>
      </div>
      <div class="loop-play">${lyricBlock(open)}${playerBlock(open)}</div>
    </section>`;
  }
  return `<section class="loops">
    <div class="loops-back">
      <button class="icon-btn" id="loopsClose" aria-label="Back to the list">${ICON.back}</button>
      <span class="label">Your words</span><span class="spacer"></span>
    </div>
    <div class="loops-head"><h2>Loops</h2><span class="spacer"></span>
      <button class="tb-btn primary" id="makeLoop">${ICON.plus}<span>Make a loop</span></button></div>
    <div class="loops-list">${loops.map(loopRow).join("")}</div>
  </section>`;
}

/* The bar at the foot for a phone or a tablet, and the chip in the top bar for a desktop. Two skins
   of one thing, so what they say can never disagree; `acervo.css` picks which is drawn. */
function renderLoopBar() {
  const loops = loopsIn(state.lang);
  const loop = player.loopId ? loopOf(player.loopId) : null;
  if (!loop) {
    return `<span class="loopbar-note">${ICON.note}</span>
      <button class="loopbar-main" id="openLoops">
        <span class="loopbar-title">Loops</span>
        <span class="loopbar-sub">${loops.length} · ${esc(state.lang.toUpperCase())}</span>
      </button>
      <button class="tb-btn loopbar-make" id="makeLoopBar">${ICON.plus}<span class="wide-only">Make a loop</span></button>`;
  }
  return `<span class="loopbar-line" style="width:0"></span>
    <button class="loopbar-play" id="barPlay" aria-label="Play">${ICON.play}</button>
    <button class="loopbar-main" id="openLoops">
      <span class="loopbar-title"></span>
      <span class="loopbar-sub"></span>
    </button>`;
}

function renderLoopChip() {
  const loops = loopsIn(state.lang);
  const loop = player.loopId ? loopOf(player.loopId) : null;
  if (!loop) return `<button class="tb-btn loop-chip" id="chipOpen" aria-label="Loops" title="Loops">
    ${ICON.note}${loops.length ? `<span class="wide-only">${loops.length}</span>` : ""}</button>`;
  return `<span class="tb-btn loop-chip playing">
    <button class="loop-chip-play" id="chipPlay" aria-label="Play">${ICON.play}</button>
    <button class="loop-chip-what" id="chipOpen">
      <span class="loop-chip-word"></span><span class="loop-chip-at"></span>
    </button></span>`;
}

/* Everything that moves with the clock, and nothing else: re-rendering the surface sixty times a
   second would lose the scroll position, the focus and the animation all at once. Each write is
   guarded by a comparison, so a frame in which nothing changed touches no DOM. */
function paintLoops() {
  const loop = player.loopId ? loopOf(player.loopId) : null;
  const glyph = player.playing ? ICON.pause : ICON.play;
  ["#playPause", "#barPlay", "#chipPlay"].forEach((id) => {
    const button = $(id);
    if (button && button.dataset.glyph !== String(player.playing)) {
      button.dataset.glyph = String(player.playing);
      button.innerHTML = glyph;
      button.setAttribute("aria-label", player.playing ? "Pause" : "Play");
    }
  });
  if (!loop) return;

  const fraction = loop.durationSeconds ? player.at / loop.durationSeconds : 0;
  const percent = `${Math.max(0, Math.min(1, fraction)) * 100}%`;
  const fill = $(".seek-fill"); if (fill) fill.style.width = percent;
  const knob = $(".seek-knob"); if (knob) knob.style.left = percent;
  const at = $(".seek-times .at"); if (at && at.textContent !== clock(player.at)) at.textContent = clock(player.at);
  const line = $(".loopbar-line"); if (line) line.style.width = percent;

  const rows = loopItemsOf(loop.id);
  const moment = loopMomentAt(rows, player.at);
  document.querySelectorAll(".lyric-row").forEach((element, i) => {
    const want = i === moment.index ? "now" : i < moment.index ? "past" : "next";
    if (element.dataset.state !== want) {
      element.dataset.state = want;
      element.classList.toggle("now", want === "now");
      element.classList.toggle("past", want === "past");
      if (want === "now") element.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    /* Said or not said, asked of the clock every frame — which is what makes a backwards drag put
       the answer away again rather than leaving it up because it was once shown. */
    const said = i < moment.index || (i === moment.index && moment.revealed);
    if (element.dataset.said !== String(said)) {
      element.dataset.said = String(said);
      element.querySelector(".lyric-target").innerHTML = said
        ? `<span class="lyric-said">${esc(element.dataset.target)}</span>`
        : '<span class="lyric-held"></span>';
    }
    /* Which of the pair is sounding: colour, and nothing else. No weight, no size, no offset — so a
       screen left running for four minutes never reflows under the eye that glances at it. */
    const saying = i === moment.index ? moment.sounding : null;
    element.querySelector(".lyric-source").classList.toggle("saying", saying === "source");
    element.querySelector(".lyric-target").classList.toggle("saying", saying === "target");
  });

  const word = moment.item ? moment.item.sourceText : loopTitle(loop, 2);
  [".loopbar-title", ".loop-chip-word"].forEach((sel) => {
    const node = $(sel); if (node && node.textContent !== word) node.textContent = word;
  });
  const sub = $(".loopbar-sub");
  if (sub) {
    const text = `${clock(player.at)} / ${clock(loop.durationSeconds)}`;
    if (sub.textContent !== text) sub.textContent = text;
  }
  const chipAt = $(".loop-chip-at");
  if (chipAt && chipAt.textContent !== clock(player.at)) chipAt.textContent = clock(player.at);
}

/* ── make a loop ── */
function loopEligible() {
  return LEXEMES.filter((x) => x.language === state.lang && x.status !== "inbox" && x.primaryGloss
    && (state.topic === "all" || x.topics.includes(state.topic))).length;
}

function renderLoopDialog() {
  const eligible = loopEligible();
  const where = state.topic === "all" ? langOf(state.lang).name : `${langOf(state.lang).name} · ${topicOf(state.topic).name}`;
  const count = Math.min(12, Math.max(1, eligible));
  return `<div class="modal-backdrop" id="loopBackdrop">
    <section class="settings loop-dialog" role="dialog" aria-modal="true" aria-labelledby="loop-dialog-title">
      <header><h2 id="loop-dialog-title">Make a loop</h2>
        <button class="close" id="loopClose" aria-label="Close">×</button></header>
      <div class="settings-body">
        <p class="config-help">Words are drawn from what you are looking at, and set to music with
          their translations.</p>
        <div class="loop-scope">${ICON.book}<span><b>${esc(where)}</b> · ${eligible} words can be in a loop</span></div>
        <label class="config-field"><span>How many words</span>
          <span class="loop-count">
            <input type="range" id="loopCount" min="4" max="${Math.max(4, Math.min(24, eligible))}" value="${count}">
            <output for="loopCount" id="loopCountOut">${count} words</output>
          </span></label>
        <label class="config-field"><span>Music</span>
          <select id="loopFamily">
            <option value="auto">Surprise me</option>
            ${LOOP_SCHEMA.families.map((f) => `<option value="${esc(f)}">${esc(f)}</option>`).join("")}
          </select></label>
        <p class="config-help">A word with no single term to say is not eligible: a loop has to
          choose one meaning, and <i>espolvorear</i> has none written down yet.</p>
        <div class="loop-engine">engine ${esc(LOOP_SCHEMA.engineVersion)} · ${
          LOOP_SCHEMA.productionBundle ? "sample pack installed" : "no sample pack — beds will be synthesised"}</div>
        <div class="loop-actions">
          <button class="tb-btn" id="loopCancel">Cancel</button>
          <button class="tb-btn primary" id="loopGo">Make the loop</button>
        </div>
      </div>
    </section>
  </div>`;
}

function openLoopDialog() {
  const node = el(renderLoopDialog());
  document.body.appendChild(node);
  const shut = () => node.remove();
  $("#loopClose", node).onclick = shut;
  $("#loopCancel", node).onclick = shut;
  node.onmousedown = (ev) => { if (ev.target === node) shut(); };
  const onKey = (ev) => { if (ev.key === "Escape") { shut(); document.removeEventListener("keydown", onKey); } };
  document.addEventListener("keydown", onKey);
  const range = $("#loopCount", node);
  range.oninput = () => { $("#loopCountOut", node).textContent = `${range.value} words`; };
  $("#loopGo", node).onclick = () => { shut(); toast("Asked for a loop — prototype only, nothing was made"); };
}

/* ── wiring ──
   Delegated from the pane, the bar and the top bar, so a re-render never leaves a dead handler. */
function wireLoops() {
  const seek = $("#seek");
  if (seek) {
    const to = (ev) => {
      const loop = loopOf(player.loopId);
      const box = seek.getBoundingClientRect();
      const x = (ev.touches ? ev.touches[0].clientX : ev.clientX) - box.left;
      loopSeek((Math.max(0, Math.min(1, x / box.width))) * loop.durationSeconds);
    };
    const move = (ev) => { ev.preventDefault(); to(ev); };
    const up = () => {
      player.scrubbing = false;
      removeEventListener("pointermove", move); removeEventListener("pointerup", up);
    };
    seek.onpointerdown = (ev) => {
      player.scrubbing = true; to(ev);
      addEventListener("pointermove", move); addEventListener("pointerup", up);
    };
    seek.onkeydown = (ev) => {
      if (ev.key === "ArrowRight") loopSeek(player.at + 5);
      else if (ev.key === "ArrowLeft") loopSeek(player.at - 5);
    };
  }
  paintLoops();
}

function openLoops() {
  state.loops = true; state.openId = null; state.openExt = null; state.add = false;
  render();
}

$("#main").addEventListener("click", (ev) => {
  const row = ev.target.closest(".lyric-row");
  if (row) { loopSeek(Number(row.dataset.seek)); if (!player.playing) loopPlay(); return; }
  const step = ev.target.closest("[data-step]");
  if (step) { loopStep(Number(step.dataset.step)); return; }
  const flip = ev.target.closest("[data-switch]");
  if (flip) {
    player[flip.dataset.switch] = !player[flip.dataset.switch];
    flip.classList.toggle("on", player[flip.dataset.switch]);
    flip.setAttribute("aria-pressed", String(player[flip.dataset.switch]));
    return;
  }
  if (ev.target.closest("#playPause")) { player.playing ? loopPause() : loopPlay(); return; }
  const open = ev.target.closest("[data-loop]");
  if (open) {
    state.loopOpen = open.dataset.loop;
    if (open.dataset.loop !== player.loopId) loopLoad(open.dataset.loop, { play: true });
    else if (!player.playing) loopPlay();
    render();
    return;
  }
  if (ev.target.closest("#makeLoop")) { openLoopDialog(); return; }
  if (ev.target.closest("#loopBack")) { state.loopOpen = null; render(); return; }
  if (ev.target.closest("#loopsClose")) { state.loops = false; state.loopOpen = null; render(); }
});

function wireLoopControls(root) {
  root.addEventListener("click", (ev) => {
    if (ev.target.closest("#barPlay") || ev.target.closest("#chipPlay")) {
      player.playing ? loopPause() : loopPlay();
      return;
    }
    if (ev.target.closest("#makeLoopBar")) { openLoopDialog(); return; }
    if (ev.target.closest("#openLoops") || ev.target.closest("#chipOpen")) {
      state.loopOpen = player.loopId;
      openLoops();
    }
  });
}
wireLoopControls($("#loopbar"));
wireLoopControls($("#loopChip"));

/* ── render ──────────────────────────────────────────────────────────── */

function render() {
  /* Reading a word on a phone or tablet does not need the topic strip, and it cost a whole row. A
     loop does not need it either: a topic files a *word*, and nothing on that surface is filed. */
  $("#main").classList.remove("cards-on");
  renderRail();
  renderLangButton();
  const main = $("#pane");
  const x = state.openId ? LEXEMES.find((y) => y.id === state.openId) : null;

  // A composer owns the height and scrolls itself, so the region around it must not also scroll.
  // The loops surface is one of those: its controls are a footer that must not drift.
  const composing = state.add || state.loops || Boolean(x && state.mode === "edit");
  $("#main").classList.toggle("composing", composing);
  /* The loops bar is a row of `.app`, so `.app` is what carries whether it is wanted: over the list
     and nowhere else. `.main` keeps its own `composing` because it is the thing that stops scrolling. */
  $(".app").classList.toggle("composing", composing);
  // Not `&& !composing`: the loops surface *is* a composing surface — it owns its height so its
  // controls cannot drift — and excluding it here left the rail on screen behind the player.
  $(".app").classList.toggle("loops-open", state.loops);
  $(".app").classList.toggle("article-open", Boolean((state.openId || state.openExt) && !state.add));
  $("#loopbar").innerHTML = renderLoopBar();
  $("#loopChip").innerHTML = renderLoopChip();
  paintLoops();
  $("#paneWrap").style.display = composing ? "none" : "";
  $("#composer").style.display = composing ? "" : "none";
  if (state.loops) {
    // Its own surface rather than a sheet over the list: a player is a place you go to, and the
    // words it shows need the whole column.
    $("#composer").innerHTML = renderLoops();
    wireLoops();
    document.title = "Loops — Acervo";
    return;
  }
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
    // A word still filling in is read on the page, where the reserved slots keep it still.
    const filling = Boolean(fillingOf(x));
    const view = state.mode === "read" ? (filling ? "page" : currentView()) : null;
    const cardsOff = filling ? ' disabled title="Cards open when pictures and clips are ready"' : "";
    $("#artBar").style.display = "";
    $("#artBar").innerHTML = `
      <button class="icon-btn" id="backBtn" aria-label="Back to the list">${ICON.back}</button>
      <span class="label art-where">${esc(state.topic === "all" ? "All words" : state.topic === "inbox" ? "Inbox" : topicOf(state.topic).name)}</span>
      ${view === "cards" ? `<div class="art-title"><span class="art-title-word" data-length="${x.headword.length > 24 ? "long" : x.headword.length > 14 ? "mid" : "short"}">${esc(x.headword)}</span>${say(x.headword, "always head")}</div>` : ""}
      <span class="spacer"></span>
      <div class="seg art-views">
        <button data-view="page" class="${view === "page" ? "on" : ""}">Page</button>
        <button data-view="cards" class="${view === "cards" ? "on" : ""}"${cardsOff}>Cards</button>
        <button data-mode="yaml" class="${state.mode === "yaml" ? "on" : ""}">YAML</button>
      </div>
      ${state.mode === "yaml" ? `<button class="icon-btn" id="editBtn" aria-label="Edit as YAML" title="Edit as YAML">${ICON.pencil}</button>` : ""}
      ${x.status === "inbox" ? `<button class="icon-btn art-file" id="fileBtn" aria-label="File it" title="File it \u2014 out of the Inbox">${ICON.file}</button>` : ""}
      <button class="icon-btn art-delete" id="delBtn" aria-label="Delete" title="Delete">${ICON.trash}</button>
      <div class="art-more">
        <button class="icon-btn" id="moreBtn" aria-label="Article menu">${ICON.more}</button>
        <div class="menu" id="articleMenu">
          <button data-view="page" class="${view === "page" ? "on" : ""}">Page</button>
          <button data-view="cards" class="${view === "cards" ? "on" : ""}"${cardsOff}>Cards</button>
          <button data-mode="yaml" class="${state.mode === "yaml" ? "on" : ""}">YAML</button>
          <div class="menu-sep"></div>
          ${x.status === "inbox" ? '<button id="fileBtn2">File it</button>' : ""}
          <button id="delBtn2" class="danger">Delete this word</button>
        </div>
      </div>`;
    $("#artBar").classList.toggle("carding", view === "cards");
    // Editing is a composer above, so only reading and the read-only projection get here.
    main.innerHTML = view === "cards" ? renderCards(x)
      : view === "page" ? progressStrip(x) + renderArticle(x) : renderYaml(x);
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
  if (hit("#moreBtn")) { $("#articleMenu").classList.toggle("open"); return; }
  if (hit("#delBtn2")) { toast("Delete writes a tombstone — not wired up in the prototype"); return; }
  if (hit("#delBtn"))  { toast("Delete writes a tombstone — not wired up in the prototype"); return; }
  /* Filing is wired up for real, unlike Delete: it is one field, and what it does to the rail and
     the counts is the whole thing worth looking at. */
  if (hit("#fileBtn") || hit("#fileBtn2")) { fileWords([state.openId]); return; }
  if (hit("#fileAllBtn")) { fileWords(visible().map((x) => x.id)); return; }

  if (hit("[data-add-picture]")) { toast("Opens the picture dialog — brief, Draw, or your own picture"); return; }
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
  state.loops = false;
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
  $("#trBtn").classList.toggle("on", state.sayTranslations);
  $("#layoutBtn").classList.toggle("on", state.loops);
  $("#speedBtn").textContent = `${player.speed}×`;
  $("#speedBtn").classList.toggle("on", player.speed !== 1);
}

$("#harness").addEventListener("click", (ev) => {
  const b = ev.target.closest("button"); if (!b) return;
  if (b.id === "themeBtn") {
    const now = document.documentElement.dataset.theme;
    setTheme(now === "dark" ? "light" : now === "light" ? "auto" : "dark");
    return;
  }
  /* Stand-ins for Settings ▸ default article view, and for listening to translations. */
  if (b.id === "viewBtn") { state.view = state.view === null ? "page" : state.view === "page" ? "cards" : null; }
  else if (b.id === "trBtn") { state.sayTranslations = !state.sayTranslations; }
  else if (b.id === "layoutBtn") { if (state.loops) { state.loops = false; state.loopOpen = null; } else openLoops(); }
  /* A word takes twenty-two seconds in a real loop. Watching the reveal at that rate is the right
     test of the *rhythm* and a poor test of everything else, so the clock can be wound on. */
  else if (b.id === "speedBtn") { player.speed = player.speed === 1 ? 4 : player.speed === 4 ? 12 : 1; }
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
/* `loops=1` opens the surface, `layout=` picks the shape, `loop=` which one, and `t=` how far in —
   so "mid-word, one translation up and the next still withheld" is a link rather than a description.
   `speed=` is the harness's clock, for a recording that does not want to run four minutes. */
if (params.get("loops") === "1" || params.get("loop") || params.get("t")) {
  state.loops = true;
  const wanted = params.get("loop");
  const picked = wanted ? LOOPS.find((l) => l.id === wanted)
    : (params.get("t") || params.get("play")) ? loopsIn(state.lang).find(loopIsReady) : null;
  if (picked) {
    state.lang = picked.language;
    state.loopOpen = picked.id;
    loopLoad(picked.id, { at: Number(params.get("t")) || 0 });
  }
  if (params.get("speed")) player.speed = Number(params.get("speed")) || 1;
  if (params.get("play") === "1") loopPlay();
}
if (params.get("make") === "1") { state.loops = true; setTimeout(openLoopDialog, 0); }
if (params.get("topic")) state.topic = params.get("topic");
if (params.get("view") === "page" || params.get("view") === "cards") state.view = params.get("view");
if (params.get("card")) state.card = Number(params.get("card")) || 0;
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
