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
  scope: { device: true, server: true, online: true }
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
  globe:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17"/><path d="M12 3.5c2.2 2.3 3.3 5.2 3.3 8.5S14.2 18.2 12 20.5c-2.2-2.3-3.3-5.2-3.3-8.5S9.8 5.8 12 3.5z"/></svg>'
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

/* ── article view ────────────────────────────────────────────────────── */

function gramLine(x) {
  const posName = { noun: "n.", verb: "v.", adj: "adj.", adv: "adv.", phrase: "phr.", idiom: "idiom", expression: "expr." }[x.pos] || x.pos;
  const bits = [posName];
  if (x.gender) bits.push(x.gender === "feminine" ? "f." : x.gender === "masculine" ? "m." : x.gender);
  bits.push(x.language);
  if (x.register && x.register !== "neutral") bits.push(x.register);
  if (x.dialect) bits.push(x.dialect);
  return bits.map((b) => `<span>${esc(b)}</span>`).join('<span class="sep">·</span>');
}

function exampleBlock(e) {
  const kind = { attestation: "own", subtitle: "corpus", tatoeba: "corpus", llm: "generated", wiktionary: "corpus", manual: "yours" }[e.origin] || e.origin;
  const cls = e.origin === "attestation" || e.origin === "manual" ? "own" : "";
  return `
    <div class="ex ${cls}">
      <p class="t">${e.text}</p>
      ${e.translation ? `<p class="tr">${e.translation}</p>` : ""}
      <div class="foot">
        <span class="prov ${cls}">${esc(e.origin)}</span>
        ${e.modelId ? `<span class="label">${esc(e.modelId)}</span>` : ""}
        ${e.approved === false ? '<span class="prov warnk">unapproved</span>' : ""}
        ${e.audio ? `<button class="play mini" data-say="${esc(strip(e.text))}">${ICON.play}Play</button>` : ""}
      </div>
      ${e.note ? `<p class="tr">✎ ${esc(e.note)}</p>` : ""}
      ${e.clip ? `
        <button class="clip" style="margin-top:10px" data-clip="1">
          <span class="pl">${ICON.play}</span>
          <span class="ti">${esc(e.clip.title)}<span>clip · starts at ${esc(e.clip.at)}</span></span>
        </button>` : ""}
    </div>`;
}

function senseSection(s, i, x) {
  const glossLine = (g) => `<div class="gloss-line"><span class="lg">${esc(g.lang)}</span><span class="tm">${g.terms.map((t) => `<b>${esc(t)}</b>`).join(" · ")}</span></div>`;
  return `
    <section class="sec">
      <div class="rail-l"><div class="inner">
        <span class="num">${String(i + 1).padStart(2, "0")}</span>
        <span class="label">Sense${s.domain ? `<br>${esc(s.domain)}` : ""}</span>
      </div></div>
      <div class="body">
        <p class="sense-def">${esc(s.definition)}</p>
        <div class="glosses">${s.glosses.map(glossLine).join("")}</div>
        ${s.examples.map(exampleBlock).join("")}
        ${s.images.length ? `
          <details class="fold">
            <summary><span class="caret">${ICON.caret}</span><span class="label">Images · ${s.images.length}</span></summary>
            <div class="fold-body">
              <div class="thumbs">
                ${s.images.map((im) => `
                  <figure class="thumb" style="margin:0">
                    <img src="${im.src}" alt="">
                    <figcaption class="cap"><span class="label">${esc(im.style)}</span></figcaption>
                  </figure>`).join("")}
              </div>
              <p class="hint" style="margin-top:11px">${esc(s.images[0].prompt)}</p>
            </div>
          </details>` : ""}
      </div>
    </section>`;
}

function renderArticle(x, opts) {
  const meta = !opts || opts.meta !== false;
  const attest = x.attestations.length ? `
    <section class="sec">
      <div class="rail-l"><div class="inner"><span class="num">✳</span><span class="label">Where you<br>met it</span></div></div>
      <div class="body">
        ${x.attestations.map((a) => `
          <div class="att">
            <p class="t">${esc(a.text)}</p>
            ${a.translation ? `<p class="tr">${esc(a.translation)}</p>` : ""}
            <div class="src">
              <span class="prov">${esc(a.sourceKind)}</span>
              ${a.sourceTitle ? (a.sourceUrl ? `<a href="${a.sourceUrl}">${esc(a.sourceTitle)}</a>` : `<span>${esc(a.sourceTitle)}</span>`) : ""}
              <span class="when">${esc(a.capturedAt)}</span>
            </div>
          </div>`).join("")}
      </div>
    </section>` : "";

  const notes = x.notes.length ? `
    <section class="sec">
      <div class="rail-l"><div class="inner"><span class="num">✎</span><span class="label">Notes</span></div></div>
      <div class="body"><ul class="notes">${x.notes.map((n) => `<li>${n}</li>`).join("")}</ul></div>
    </section>` : "";

  const study = x.study ? `
    <section class="sec">
      <div class="rail-l"><div class="inner"><span class="num">◷</span><span class="label">Study<br>${esc(x.study.system)}</span></div></div>
      <div class="body">
        <div class="stats">
          <div class="stat"><div class="label">Stability</div><div class="v">${x.study.stability}<small> d</small></div></div>
          <div class="stat"><div class="label">Difficulty</div><div class="v">${x.study.difficulty}<small>/10</small></div></div>
          <div class="stat"><div class="label">Retrievability</div><div class="v">${Math.round(x.study.retrievability * 100)}<small>%</small></div></div>
          <div class="stat"><div class="label">Reps · lapses</div><div class="v">${x.study.reps}<small> · ${x.study.lapses}</small></div></div>
          <div class="stat"><div class="label">Last review</div><div class="v" style="font-size:14px">${esc(x.study.lastReview)}</div></div>
        </div>
      </div>
    </section>` : "";

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
          </div>
          <p class="gram">${gramLine(x)}</p>
        </div>
      </div>
      <div class="chips">
        <span class="chip status ${x.status === "inbox" ? "inbox" : ""}">${esc(x.status)}</span>
        ${x.topics.map((k) => `<span class="chip">${topicOf(k).icon} ${esc(topicOf(k).name)}</span>`).join("")}
      </div>
    </div>
    ${x.senses.map((s, i) => senseSection(s, i, x)).join("")}
    ${attest}${notes}${study}
    ${meta ? `
    <div class="meta-foot">
      <span>id <b>${x.id}</b></span>
      <span>added <b>${x.createdAt}</b></span>
      <span>edited <b>${x.editedAt}</b></span>
      <span>rev <b>${x.revision}</b></span>
      <span>synced <b>yes</b></span>
    </div>` : ""}`;
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
    L.push("    glosses:");
    s.glosses.forEach((g) => L.push(`      - { lang: ${g.lang}, terms: [${g.terms.map(q).join(", ")}] }`));
    L.push("    examples:");
    s.examples.forEach((e) => {
      L.push(`      - text: ${q(strip(e.text))}`);
      if (e.translation) L.push(`        translation: ${q(strip(e.translation))}`);
      L.push(`        origin: ${e.origin}`);
      if (e.modelId) L.push(`        modelId: ${e.modelId}`);
      L.push(`        approved: ${e.approved}`);
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
        approved: true
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
    $("#artBar").style.display = "";
    $("#artBar").innerHTML = `
      <button class="icon-btn" id="backBtn" aria-label="Back to the list">${ICON.back}</button>
      <span class="label">${esc(state.topic === "all" ? "All words" : state.topic === "inbox" ? "Inbox" : topicOf(state.topic).name)}</span>
      <span class="spacer"></span>
      <div class="seg">
        <button data-mode="read" class="${state.mode === "read" ? "on" : ""}">Read</button>
        <button data-mode="yaml" class="${state.mode !== "read" ? "on" : ""}">YAML</button>
      </div>
      <button class="icon-btn" id="editBtn" aria-label="Edit as YAML" title="Edit as YAML">${ICON.pencil}</button>
      <button class="icon-btn" id="delBtn" aria-label="Delete" title="Delete">${ICON.trash}</button>`;
    // Editing is a composer above, so only reading and the read-only projection get here.
    main.innerHTML = state.mode === "read" ? renderArticle(x) : renderYaml(x);
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

document.addEventListener("click", (ev) => {
  const t = ev.target;
  const hit = (sel) => t.closest(sel);

  const topicBtn = hit("[data-topic]");
  if (topicBtn) { state.topic = topicBtn.dataset.topic; state.openId = null; state.query = ""; $("#q").value = ""; $("#search").classList.remove("searching"); render(); return; }

  const sortBtn = hit("[data-sort]");
  if (sortBtn) { state.sort = sortBtn.dataset.sort; render(); return; }

  const openBtn = hit("[data-open]");
  if (openBtn) { state.openId = openBtn.dataset.open; state.openExt = null; state.mode = "read"; render(); $("#main").scrollTop = 0; return; }

  const extBtn = hit("[data-ext]");
  if (extBtn) { state.openExt = extBtn.dataset.ext; state.openId = null; render(); $("#main").scrollTop = 0; return; }

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
  if (hit("[data-clip]")) { toast("Clip playback lands with the corpus"); return; }

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

$("#harness").addEventListener("click", (ev) => {
  const b = ev.target.closest("button"); if (!b) return;
  if (b.id === "themeBtn") {
    const now = document.documentElement.dataset.theme;
    setTheme(now === "dark" ? "light" : now === "light" ? "auto" : "dark");
    return;
  }
  document.body.className = b.dataset.frame === "desktop" ? "" : `framed ${b.dataset.frame}`;
  $("#harness").querySelectorAll("button[data-frame]").forEach((x) => x.classList.toggle("on", x === b));
});

/* deep link — ?open=<id|headword>&mode=read|yaml keeps screenshots reproducible */
const params = new URLSearchParams(location.search);
if (params.get("open")) {
  const want = params.get("open").toLowerCase();
  const hit = LEXEMES.find((x) => x.id === want || x.headword.toLowerCase() === want || x.lemma.toLowerCase() === want);
  const mode = params.get("mode");
  if (hit) { state.openId = hit.id; state.lang = hit.language; state.mode = mode === "yaml" || mode === "edit" ? mode : "read"; }
}
if (params.get("topic")) state.topic = params.get("topic");
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
  document.querySelectorAll("#harness button").forEach((b) => b.classList.toggle("on", b.dataset.frame === f));
}

render();
