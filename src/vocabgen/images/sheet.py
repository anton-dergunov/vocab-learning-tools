"""A contact sheet: one self-contained HTML page, opened locally, read on a tablet.

The review surface for the iteration loop. It shows what the picture was *for* — the word, the
sense, the anchor sentence, the style, the brief — because judging a mnemonic without knowing what
it was supposed to make you recall is judging a picture, which is the wrong question.

Rejecting is deleting: tick what you disliked, paste the command it builds, run the tool again.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from .run import Store

PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Acervo sense images</title>
<style>
  :root { color-scheme: light dark; --ink:#1b1a17; --dim:#6b6659; --line:#dcd6c8; --bg:#faf7f0; --card:#fff; }
  @media (prefers-color-scheme: dark) {
    :root { --ink:#ece7dc; --dim:#9c968a; --line:#35322c; --bg:#16150f; --card:#1e1c16; }
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  header { position:sticky; top:0; z-index:2; background:var(--bg); border-bottom:1px solid var(--line);
           padding:14px 20px; display:flex; gap:16px; align-items:baseline; flex-wrap:wrap; }
  h1 { font-size:19px; margin:0; font-weight:650; }
  .meta { color:var(--dim); font-size:14px; }
  main { display:grid; gap:20px; padding:20px;
         grid-template-columns:repeat(auto-fill, minmax(330px, 1fr)); }
  figure { margin:0; background:var(--card); border:1px solid var(--line); border-radius:14px;
           overflow:hidden; display:flex; flex-direction:column; }
  figure.out { opacity:.38; }
  img { width:100%; aspect-ratio:1; object-fit:cover; display:block; cursor:pointer; }
  .body { padding:13px 15px 15px; display:flex; flex-direction:column; gap:7px; }
  .hw { font-size:18px; font-weight:650; }
  .hw span { font-weight:400; color:var(--dim); font-size:14px; margin-left:7px; }
  .gl { font-size:14px; }
  .df { font-size:13px; color:var(--dim); }
  .ex { font-size:13px; border-left:2px solid var(--line); padding-left:9px; }
  .ex i { color:var(--dim); font-style:normal; display:block; }
  .br { font-size:12.5px; color:var(--dim); }
  .sb { font-size:12px; text-transform:uppercase; letter-spacing:.06em; font-weight:650; }
  .si { font-size:12.5px; }
  .pr { font-size:12px; color:var(--dim); }
  .pr summary { cursor:pointer; }
  .pr p { margin:7px 0 0; font:11.5px/1.55 ui-monospace, Menlo, monospace; }
  .st { font-size:11px; text-transform:uppercase; letter-spacing:.08em; color:var(--dim); }
  .row { display:flex; justify-content:space-between; align-items:center; gap:10px; margin-top:2px; }
  label { font-size:13px; display:flex; gap:7px; align-items:center; cursor:pointer; user-select:none; }
  textarea { width:100%; height:150px; font:12px/1.5 ui-monospace, Menlo, monospace;
             background:var(--card); color:var(--ink); border:1px solid var(--line);
             border-radius:10px; padding:11px; margin:0 20px 24px; width:calc(100% - 40px); }
  button { font:inherit; padding:6px 14px; border-radius:9px; border:1px solid var(--line);
           background:var(--card); color:var(--ink); cursor:pointer; }
</style>
<header>
  <h1>Sense images</h1>
  <span class="meta">__COUNT__ drawn · __REFUSED__ refused · __VERSION__</span>
  <button onclick="build()">Build delete list</button>
</header>
<main>__CARDS__</main>
<textarea id="out" placeholder="Tick the pictures you do not want, then press Build delete list, paste the result into a terminal, and run the tool again to redraw them."></textarea>
<script>
const ROOT = __ROOT__;
function toggle(el, id) {
  const box = document.getElementById('c-' + id);
  box.checked = !box.checked;
  box.closest('figure').classList.toggle('out', box.checked);
}
function build() {
  const ids = [...document.querySelectorAll('input:checked')].map(b => b.value);
  document.getElementById('out').value = ids.length
    ? 'rm ' + ids.map(i => JSON.stringify(ROOT + '/images/' + i + '.webp')).join(' \\\\\\n   ')
    : '';
}
</script>
"""

CARD = """<figure>
  <img src="images/{id}.webp" alt="" loading="lazy" onclick="toggle(this,'{id}')">
  <div class="body">
    <div class="hw">{headword}<span>{pos}{topics}</span></div>
    <div class="gl">{gloss}</div>
    <div class="df">{definition}</div>
    {example}
    <div class="sb">{subject}</div>
    <div class="si">{situation}</div>
    <div class="br">{brief}</div>
    <details class="pr"><summary>prompt sent to the image model</summary><p>{prompt}</p></details>
    <div class="row">
      <span class="st">{style} · {seconds}s · {kib} KiB</span>
      <label><input type="checkbox" id="c-{id}" value="{id}" onchange="this.closest('figure').classList.toggle('out', this.checked)">reject</label>
    </div>
  </div>
</figure>"""


def _gloss(glosses: list[dict]) -> str:
    for gloss in glosses or []:
        terms = gloss.get("terms") or []
        if terms:
            return ", ".join(terms)
    return ""


def write_sheet(store: Store, output: Path | None = None) -> Path:
    records = []
    for path in sorted(store.records.glob("*.json")):
        record = store.read(path)
        if record and record.get("imageRef") and store.is_drawn(record["id"]):
            records.append(record)
    records.sort(key=lambda record: (record["run"]["headword"].lower(), record["run"]["senseOrder"]))

    cards = []
    for record in records:
        run = record["run"]
        anchor = run.get("anchorExample")
        example = ""
        if anchor:
            example = (
                f'<div class="ex">{html.escape(anchor.get("text") or "")}'
                f'<i>{html.escape(anchor.get("translation") or "")}</i></div>'
            )
        topics = f" · {html.escape(', '.join(run.get('topics') or []))}" if run.get("topics") else ""
        cards.append(CARD.format(
            id=record["id"],
            headword=html.escape(run["headword"]),
            pos=html.escape(run.get("language", "")),
            topics=topics,
            gloss=html.escape(_gloss(run.get("glosses") or [])),
            definition=html.escape(run.get("definition") or ""),
            example=example,
            brief=html.escape(record.get("prompt") or ""),
            subject=html.escape(run.get("subject") or ""),
            situation=html.escape(run.get("situation") or ""),
            prompt=html.escape(run.get("composedPrompt") or ""),
            style=html.escape(record.get("styleId") or ""),
            seconds=run.get("seconds", 0),
            kib=int(run.get("bytes", 0)) // 1024,
        ))

    refused = len(list(store.refusals.glob("*.json")))
    version = records[0]["promptVersion"] if records else ""
    page = (PAGE
            .replace("__CARDS__", "\n".join(cards))
            .replace("__COUNT__", str(len(records)))
            .replace("__REFUSED__", str(refused))
            .replace("__VERSION__", html.escape(version))
            .replace("__ROOT__", json.dumps(str(store.root.resolve()))))

    target = output or (store.root / "sheet.html")
    target.write_text(page, encoding="utf-8")
    return target
