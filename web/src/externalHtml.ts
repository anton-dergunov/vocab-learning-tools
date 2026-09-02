/**
 * Turning an `html`-tier dictionary payload into something that reads like Acervo.
 *
 * §11.4 found that these payloads need *restyling*, not merely sanitising: the markup is either
 * presentational (FreeDict's `<font color="gray">` for IPA, whose inline colours fight the theme in
 * both light and dark) or structurally thin (a bare `<div>` meaning "part of speech" at one depth
 * and "translation" at another). Stripping the danger out and rendering what is left gives a page
 * that is safe and ugly, which is not the deliverable — a word read here should look like a word
 * read in `LexemeArticle.tsx`.
 *
 * So this is an allow-list *and* a mapper. It emits Acervo's own marks — `ext-gram`, `ext-tr`,
 * `ext-ex`, `ext-tag` — and `styles.css` gives them the type the rest of the article uses. What it
 * cannot recognise it leaves as ordinary prose rather than guessing.
 *
 * Three source shapes exist in practice, all three measured off the compiled artifacts rather than
 * assumed (`testFixtures/dictionaryHtml.json` holds real payloads of each):
 *
 *   1. WikDict / PyGlossary — clean but semantically thin. Position is the only signal.
 *   2. Yomitan-derived (`wty-*`) — carries a `content=` attribute naming what each node *is*.
 *      This is the good case and most of the mapping below is reading those names.
 *   3. ECDICT — a single list item of preformatted plain text with newlines in it.
 *
 * The output is safe to hand to `dangerouslySetInnerHTML`: nothing survives that is not on the
 * allow-list, and no attribute survives that is not named here.
 */

/** Everything else is unwrapped — its children are kept, the element itself is not. */
const ALLOWED = new Set([
  "p", "div", "span", "b", "strong", "i", "em", "u", "sub", "sup", "small",
  "ol", "ul", "li", "dl", "dt", "dd", "br", "hr", "a", "abbr", "q", "blockquote",
  "table", "thead", "tbody", "tr", "td", "th", "details", "summary", "h1", "h2", "h3", "h4"
]);

/** Removed with their contents, not unwrapped: what they contain is not text to read. */
const DISCARDED = new Set([
  "script", "style", "iframe", "object", "embed", "link", "meta", "form", "input",
  "button", "select", "textarea", "svg", "audio", "video", "canvas", "noscript", "head"
]);

/** Kept per tag. Everything else — `style`, `color`, `class`, `id`, every `on*` — is dropped. */
const KEEP_ATTRIBUTES: Record<string, Set<string>> = {
  a: new Set(["href", "title"]),
  abbr: new Set(["title"]),
  span: new Set(["title"]),
  td: new Set(["colspan", "rowspan"]),
  th: new Set(["colspan", "rowspan"])
};

/**
 * Part-of-speech words PyGlossary emits as a bare `<div>`.
 *
 * Deliberately a *recognition* list, not a mapping: an unrecognised word is rendered as the
 * translation it is more often than not, never bucketed into Acervo's enum. §11.3 — the enum is
 * for stored records, and an external entry keeps the source's own word.
 */
const POS_WORDS = new Set([
  "noun", "proper noun", "verb", "adjective", "adverb", "pronoun", "preposition", "conjunction",
  "interjection", "numeral", "number", "particle", "article", "determiner", "prefix", "suffix",
  "abbreviation", "phrase", "idiom", "expression", "character", "contraction", "postposition",
  "adposition", "classifier", "counter", "auxiliary", "participle", "infix", "letter", "symbol"
]);

/** The same caret `icons.tsx` draws, as markup, so a fold here matches a fold anywhere else. */
const CARET = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" '
  + 'stroke-linejoin="round" stroke-width="2.2" aria-hidden="true"><path d="M9 5l7 7-7 7"/></svg>';

const text = (node: Element): string => (node.textContent ?? "").trim();

function isSafeHref(value: string): boolean {
  try {
    const url = new URL(value, "https://acervo.invalid/");
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

/** Replaces `node` with its own children, in place. */
function unwrap(node: Element): void {
  const parent = node.parentNode;
  if (!parent) return;
  while (node.firstChild) parent.insertBefore(node.firstChild, node);
  parent.removeChild(node);
}

function rename(document: Document, node: Element, tag: string, className: string | null): Element {
  const replacement = document.createElement(tag);
  if (className) replacement.setAttribute("class", className);
  while (node.firstChild) replacement.appendChild(node.firstChild);
  for (const name of node.getAttributeNames()) {
    if (name === "title" && tag !== "details") replacement.setAttribute("title", node.getAttribute(name) ?? "");
  }
  node.parentNode?.replaceChild(replacement, node);
  return replacement;
}

/**
 * What a Yomitan `content=` attribute names, mapped onto Acervo's marks.
 *
 * `null` means "unwrap": a node that only exists to group something the layout already groups.
 */
const CONTENT_ROLES: Record<string, { tag: string; className: string } | null> = {
  "preamble": { tag: "div", className: "ext-preamble" },
  "glosses": { tag: "ol", className: "ext-senses" },
  "tags": { tag: "div", className: "ext-tags" },
  "tag": { tag: "span", className: "ext-tag" },
  "example-sentence": { tag: "div", className: "ext-ex" },
  "example-sentence-a": { tag: "p", className: "ext-t" },
  "example-sentence-b": { tag: "p", className: "ext-tr" },
  "bold-text": { tag: "b", className: "" },
  "backlink": { tag: "div", className: "ext-links" },
  "extra-info": null
};

function contentRole(value: string): { tag: string; className: string } | null | undefined {
  if (Object.prototype.hasOwnProperty.call(CONTENT_ROLES, value)) return CONTENT_ROLES[value];
  // `details-entry-Grammar`, `Grammar-content`, `details-entry-Etymology`, … — the part after the
  // fixed prefix is the source's own heading, which the fold's summary already says out loud.
  if (value.startsWith("details-entry-")) return { tag: "details", className: "fold ext-fold" };
  if (value.endsWith("-content")) return { tag: "div", className: "fold-body ext-note" };
  return undefined;
}

/**
 * A text-only `<div>` in a PyGlossary payload: the part of speech, or a translation?
 *
 * Position is all there is. A first child standing in front of a sense list is the part of speech
 * (`<div><div>verb</div><ol>…`); one following definition text is the translation
 * (`<li>Cortar en pedazos…<div>mince</div></li>`). The ambiguous case — first child of a list item
 * with no list beside it — is settled by whether the word is a part of speech at all, which is why
 * `POS_WORDS` exists.
 */
function positionalRole(node: Element): "gram" | "translation" | "content" {
  // A div that is the entire content of its list item is that item — Yomitan wraps every gloss this
  // way. Marking it as a translation put an arrow in front of half the definitions.
  const holder = node.parentElement;
  if (holder?.tagName.toLowerCase() === "li" && holder.childNodes.length === 1) return "content";
  const parent = node.parentElement;
  const first = parent?.firstElementChild === node && !(parent.firstChild?.nodeType === 3
    && (parent.firstChild.textContent ?? "").trim().length > 0);
  if (!first) return "translation";
  if (parent?.querySelector(":scope > ol, :scope > ul")) return "gram";
  return POS_WORDS.has(text(node).toLowerCase()) ? "gram" : "translation";
}

/** ECDICT stores a whole entry as one run of preformatted lines. Without this it renders as a wall. */
function splitPreformatted(document: Document, node: Element): boolean {
  if (node.children.length > 0) return false;
  const content = node.textContent ?? "";
  if (!content.includes("\n")) return false;
  const lines = content.split("\n").map((line) => line.trim()).filter(Boolean);
  if (lines.length < 2) return false;
  while (node.firstChild) node.removeChild(node.firstChild);
  for (const line of lines) {
    const paragraph = document.createElement("p");
    paragraph.setAttribute("class", "ext-line");
    paragraph.textContent = line;
    node.appendChild(paragraph);
  }
  return true;
}

/**
 * Sanitise and restyle one payload.
 *
 * `headword` lets the leading title be dropped: the masthead above already says the word, and
 * repeating it is the single most obvious way an external article would stop looking like an
 * Acervo one. A payload holding several — homographs, as `sencillo` does — keeps a rule between
 * them instead, because two parts of speech running together read as one entry.
 */
export function normaliseDictionaryHtml(html: string, headword = ""): string {
  if (!html.trim()) return "";
  const parsed = new DOMParser().parseFromString(`<body>${html}</body>`, "text/html");
  const document = parsed;
  const body = parsed.body;

  for (const node of [...body.querySelectorAll("*")]) {
    if (DISCARDED.has(node.tagName.toLowerCase())) node.remove();
  }

  // A live list would shift under renaming and unwrapping, so the walk is over a snapshot and each
  // node is checked for having been detached in the meantime.
  for (const node of [...body.querySelectorAll("*")]) {
    if (!node.isConnected) continue;
    const tag = node.tagName.toLowerCase();
    const role = node.hasAttribute("content") ? contentRole(node.getAttribute("content") ?? "") : undefined;

    for (const name of node.getAttributeNames()) {
      if ((KEEP_ATTRIBUTES[tag] ?? new Set<string>()).has(name)) continue;
      node.removeAttribute(name);
    }
    if (tag === "a") {
      const href = node.getAttribute("href") ?? "";
      if (isSafeHref(href)) {
        node.setAttribute("target", "_blank");
        node.setAttribute("rel", "noreferrer noopener");
      } else {
        node.removeAttribute("href");
      }
    }

    if (role === null) { unwrap(node); continue; }
    if (role) {
      const replacement = rename(document, node, role.tag, role.className || null);
      if (role.tag === "details") {
        // The summary carries the source's own heading — "Grammar", "Etymology", "3 examples" —
        // and it has to stay a `<summary>`, or the fold loses its label and the browser draws its
        // own. Wrapping the text is what makes it read like every other fold in the article.
        const summary = replacement.querySelector("summary");
        if (summary) {
          summary.innerHTML = `<span class="caret">${CARET}</span>`
            + `<span class="label">${(summary.textContent ?? "").trim()
                 .replace(/&/g, "&amp;").replace(/</g, "&lt;")}</span>`;
        }
      }
      continue;
    }

    if (!ALLOWED.has(tag)) { unwrap(node); continue; }
    if (tag === "li" && splitPreformatted(document, node)) continue;
    if (tag === "div" && node.children.length === 0 && text(node)) {
      const placement = positionalRole(node);
      if (placement === "content") unwrap(node);
      else rename(document, node, "p", placement === "gram" ? "ext-gram" : "ext-tr");
      continue;
    }
    if (tag === "ol" && node.parentElement === body) node.setAttribute("class", "ext-senses");
  }

  /* A list of one is a wrapper, not a list. Every source nests the whole entry inside `<ol><li>`
     before the senses begin, and numbering that wrapper puts a meaningless "1." in front of the
     word. Collapsing it also means a single-sense entry reads as a statement rather than as a list
     with one item in it, which is what it is. */
  for (const list of [...body.querySelectorAll("ol, ul")].reverse()) {
    const items = [...list.children].filter((child) => child.tagName.toLowerCase() === "li");
    if (items.length !== 1 || list.children.length !== 1) continue;
    unwrap(items[0]);
    unwrap(list);
  }

  // Titles last, after the attribute strip: the marks below are ours and must survive it. Several
  // titles in one payload mean homographs — `sencillo` is an adjective and a noun — so they get a
  // rule between them; a single one repeating the masthead just goes.
  const titles = [...body.querySelectorAll("h1")];
  const wanted = headword.trim().toLowerCase();
  titles.forEach((title, index) => {
    if (wanted && text(title).toLowerCase() !== wanted) {
      rename(document, title, "h2", "ext-title");
      return;
    }
    if (index === 0) { title.remove(); return; }
    const rule = document.createElement("div");
    rule.setAttribute("class", "ext-split");
    title.parentNode?.replaceChild(rule, title);
  });

  return body.innerHTML.trim();
}

/**
 * The same payload as plain text, for the capture reference.
 *
 * The model is grounded on what the reader saw, so this reads the *normalised* markup rather than
 * the source's, and keeps the line breaks the structure implies — a run of senses collapsed onto
 * one line is materially harder to write an article from.
 */
export function dictionaryHtmlToText(html: string, headword = ""): string {
  const parsed = new DOMParser().parseFromString(
    `<body>${normaliseDictionaryHtml(html, headword)}</body>`, "text/html");
  for (const node of parsed.body.querySelectorAll("li, p, div, tr, summary, br")) {
    node.parentNode?.insertBefore(parsed.createTextNode("\n"), node);
  }
  return (parsed.body.textContent ?? "")
    .split("\n").map((line) => line.replace(/\s+/g, " ").trim()).filter(Boolean).join("\n");
}
