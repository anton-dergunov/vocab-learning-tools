"""The blind review page: every story's sets side by side, labelled by letter, saved as you tap.

    .venv/bin/python experiments/story-picture-reference/review.py --host 100.x.y.z --port 8765

Standard library only. On first start each story's sets are shuffled into letters with a fixed seed
and written to `out/key.json`; the page is never told which letter is which, and a picture's URL is
`/img/<story>/<letter>/<n>`, so nothing on screen or in the address bar gives it away. Part 1 is the
same stored picture in every set and says nothing either. Labels go to `out/ratings.json` on every
tap, so closing the tab loses nothing. `run.py report` unblinds them.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
# Overridable so the page can be tried on made-up stories without touching a real run.
OUT = Path(os.environ.get("STORY_PICTURES_OUT") or HERE / "out")
SEED = 20260924
RECENT = 5
SETS = ("original", "first+prev", "prev", "first")
LETTERS = "ABCD"
FLAGS = ("characters change", "too alike")

_lock = threading.Lock()


def _read(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write(path: Path, value: Any) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _complete(story: dict[str, Any], set_: str) -> bool:
    folder = OUT / story["id"] / set_
    first = 1 if set_ == "original" else 2
    return all((folder / f"part-{n}.webp").exists() for n in range(first, len(story["parts"]) + 1))


def build() -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    """The stories that can be reviewed, oldest first, and the letter → set key for each.

    A story is shown once its original and main sets are complete. The key is kept across restarts;
    a story whose available sets changed since (the variants finishing, say) is reshuffled only if
    nothing has been rated on it yet, so a label never silently comes to mean another set.
    """
    stories = sorted(_read(OUT / "stories.json", []), key=lambda story: story["createdAt"])
    key: dict[str, dict[str, str]] = _read(OUT / "key.json", {})
    ratings = _read(OUT / "ratings.json", {})
    shown = []
    for story in stories:
        sets = [set_ for set_ in SETS if _complete(story, set_)]
        if "original" not in sets or "first+prev" not in sets:
            continue
        held = key.get(story["id"])
        if held is None or (sorted(held.values()) != sorted(sets) and story["id"] not in ratings):
            order = sets[:]
            random.Random(f"{SEED}:{story['id']}").shuffle(order)
            key[story["id"]] = dict(zip(LETTERS, order))
        shown.append(story)
    _write(OUT / "key.json", key)
    recent = {story["id"] for story in stories[-RECENT:]}
    return [{
        "id": story["id"],
        "title": story["title"],
        "titleTranslation": story.get("titleTranslation") or "",
        "emoji": story.get("emoji") or "",
        "createdAt": story["createdAt"],
        "recent": story["id"] in recent,
        "parts": [{"heading": part["heading"], "text": part["text"],
                   "translation": part.get("translation") or ""} for part in story["parts"]],
        "labels": sorted(key[story["id"]]),
    } for story in shown], key


class Handler(BaseHTTPRequestHandler):
    stories: list[dict[str, Any]] = []
    key: dict[str, dict[str, str]] = {}

    def log_message(self, *_: Any) -> None:  # the terminal is for errors, not every picture
        pass

    def _send(self, status: int, body: bytes, kind: str, cache: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif self.path == "/data":
            body = {"stories": self.stories, "ratings": _read(OUT / "ratings.json", {}),
                    "flags": FLAGS}
            self._send(200, json.dumps(body, ensure_ascii=False).encode(), "application/json")
        elif self.path.startswith("/img/"):
            try:
                _, _, story_id, letter, number = self.path.split("/")
                set_ = self.key[story_id][letter]
                n = int(number)
            except (ValueError, KeyError):
                self._send(404, b"", "text/plain")
                return
            file = OUT / story_id / ("original" if n == 1 else set_) / f"part-{n}.webp"
            if not file.exists():
                self._send(404, b"", "text/plain")
                return
            self._send(200, file.read_bytes(), "image/webp", cache=True)
        else:
            self._send(404, b"", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/rate":
            self._send(404, b"", "text/plain")
            return
        try:
            update = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            story_id = update["story"]
            if story_id not in self.key:
                raise KeyError(story_id)
        except (ValueError, KeyError):
            self._send(HTTPStatus.BAD_REQUEST, b"", "text/plain")
            return
        with _lock:
            ratings = _read(OUT / "ratings.json", {})
            rating = ratings.setdefault(story_id, {"best": "", "flags": {}, "note": ""})
            if "best" in update:
                rating["best"] = update["best"]
            if "flag" in update:
                letter, flag, on = update["flag"]
                rating["flags"].setdefault(letter, {})[flag] = bool(on)
            if "note" in update:
                rating["note"] = str(update["note"])[:2000]
            _write(OUT / "ratings.json", ratings)
        self._send(200, b"{}", "application/json")


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Story pictures, blind</title>
<style>
:root {
  --bg: #f6f2ea; --card: #fffdf8; --ink: #2a2622; --muted: #7a7166; --rule: #e2dacd;
  --accent: #3f6b4f; --accent-soft: #dfeadf; --warn: #9a4b2f; --warn-soft: #f3e1d8;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1c1a17; --card: #25221e; --ink: #ece6dc; --muted: #a39a8d; --rule: #3a352f;
    --accent: #8fc09f; --accent-soft: #2c3b30; --warn: #e3a184; --warn-soft: #43302a;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 17px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
header.bar { position: sticky; top: 0; z-index: 5; background: var(--bg);
  border-bottom: 1px solid var(--rule); padding: 10px 16px; display: flex; gap: 12px;
  align-items: center; }
header.bar .count { font-weight: 600; }
header.bar button { margin-left: auto; }
main { max-width: 900px; margin: 0 auto; padding: 8px 16px 80px; }
section.story { background: var(--card); border: 1px solid var(--rule); border-radius: 14px;
  padding: 16px; margin: 18px 0; }
.meta { color: var(--muted); font-size: 14px; display: flex; gap: 8px; align-items: center; }
.badge { background: var(--accent-soft); color: var(--accent); border-radius: 999px;
  padding: 1px 9px; font-size: 13px; font-weight: 600; }
h2 { margin: 4px 0 2px; font-size: 22px; }
.translation { color: var(--muted); margin: 0 0 8px; }
details { margin: 6px 0 12px; }
summary { cursor: pointer; color: var(--accent); font-weight: 600; }
details p { margin: 6px 0; }
details .en { color: var(--muted); font-size: 15px; }
.set { margin: 18px 0 8px; }
.set-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.letter { font-size: 22px; font-weight: 700; width: 36px; height: 36px; border-radius: 50%;
  display: grid; place-items: center; background: var(--ink); color: var(--card); }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.grid figure { margin: 0; position: relative; }
.grid figcaption { position: absolute; left: 6px; top: 6px; background: rgba(0,0,0,.55);
  color: #fff; font-size: 13px; font-weight: 600; border-radius: 999px; padding: 0 8px;
  pointer-events: none; }
.grid img { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 6px; display: block;
  background: var(--rule); cursor: zoom-in; }
.chips { display: flex; gap: 8px; flex-wrap: wrap; margin-left: auto; }
button { font: inherit; border: 1px solid var(--rule); background: var(--card); color: var(--ink);
  border-radius: 999px; padding: 7px 14px; min-height: 40px; cursor: pointer; }
button.chip[aria-pressed="true"] { background: var(--warn-soft); border-color: var(--warn);
  color: var(--warn); }
.verdict { border-top: 1px solid var(--rule); margin-top: 16px; padding-top: 12px; }
.verdict .choices { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0; }
.verdict button[aria-pressed="true"] { background: var(--accent); border-color: var(--accent);
  color: var(--card); }
textarea { width: 100%; min-height: 56px; font: inherit; border: 1px solid var(--rule);
  border-radius: 8px; padding: 8px; background: var(--bg); color: var(--ink); }
.saved { color: var(--muted); font-size: 13px; min-height: 18px; }
#zoom { position: fixed; inset: 0; background: rgba(0,0,0,.92); display: none; z-index: 10;
  place-items: center; }
#zoom.open { display: grid; }
#zoom img { max-width: 100vw; max-height: 100vh; object-fit: contain; }
#zoom .where { position: absolute; top: 12px; left: 16px; color: #ddd; font-size: 15px; }
</style>
</head>
<body>
<header class="bar"><span class="count" id="count">Loading…</span>
  <button id="next">Next unrated ↓</button></header>
<main id="stories"></main>
<div id="zoom" role="dialog" aria-label="Picture"><span class="where"></span><img alt=""></div>
<script>
let DATA, RATINGS;
const $ = (tag, attrs = {}, ...kids) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v; else if (k.startsWith("on")) node[k] = v;
    else node.setAttribute(k, v);
  }
  for (const kid of kids) node.append(kid);
  return node;
};

async function save(story, change, status) {
  status.textContent = "Saving…";
  try {
    const response = await fetch("/rate", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ story, ...change }) });
    if (!response.ok) throw new Error(response.status);
    status.textContent = "Saved";
  } catch (error) { status.textContent = "Not saved — is the laptop awake? (" + error.message + ")"; }
  updateCount();
}

function rating(id) {
  return RATINGS[id] ??= { best: "", flags: {}, note: "" };
}

function updateCount() {
  const done = DATA.stories.filter(s => RATINGS[s.id]?.best).length;
  document.getElementById("count").textContent = `${done} of ${DATA.stories.length} rated`;
}

function zoom(src, where) {
  const box = document.getElementById("zoom");
  box.querySelector("img").src = src;
  box.querySelector(".where").textContent = where;
  box.classList.add("open");
}
document.getElementById("zoom").onclick = () => document.getElementById("zoom").classList.remove("open");

function render(story) {
  const r = rating(story.id);
  const status = $("div", { class: "saved" });
  const date = new Date(story.createdAt);
  const section = $("section", { class: "story", id: "s-" + story.id },
    $("div", { class: "meta" }, date.toLocaleString(undefined,
      { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }),
      story.recent ? $("span", { class: "badge" }, "recent") : ""),
    $("h2", {}, `${story.emoji ? story.emoji + " " : ""}${story.title}`),
    story.titleTranslation ? $("p", { class: "translation" }, story.titleTranslation) : "");

  const reading = $("details", {}, $("summary", {}, "Read the story"));
  story.parts.forEach((part, i) => {
    reading.append($("p", {}, $("strong", {}, `${i + 1}. ${part.heading || ""} `), part.text));
    if (part.translation) reading.append($("p", { class: "en" }, part.translation));
  });
  section.append(reading);

  for (const letter of story.labels) {
    const chips = $("div", { class: "chips" });
    for (const flag of DATA.flags) {
      const on = !!r.flags[letter]?.[flag];
      const chip = $("button", { class: "chip", "aria-pressed": String(on) }, flag);
      chip.onclick = () => {
        const next = chip.getAttribute("aria-pressed") !== "true";
        chip.setAttribute("aria-pressed", String(next));
        (r.flags[letter] ??= {})[flag] = next;
        save(story.id, { flag: [letter, flag, next] }, status);
      };
      chips.append(chip);
    }
    const grid = $("div", { class: "grid" });
    story.parts.forEach((_, i) => {
      const src = `/img/${story.id}/${letter}/${i + 1}`;
      grid.append($("figure", {}, $("img", { src, loading: "lazy", alt: `Set ${letter}, part ${i + 1}`,
        onclick: () => zoom(src, `${letter} · part ${i + 1}`) }), $("figcaption", {}, String(i + 1))));
    });
    section.append($("div", { class: "set" },
      $("div", { class: "set-head" }, $("span", { class: "letter" }, letter), chips), grid));
  }

  const choices = $("div", { class: "choices" });
  for (const choice of [...story.labels, "no difference"]) {
    const button = $("button", { "aria-pressed": String(r.best === choice) },
      choice.length === 1 ? `Set ${choice}` : choice);
    button.onclick = () => {
      r.best = choice;
      choices.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(b === button)));
      save(story.id, { best: choice }, status);
    };
    choices.append(button);
  }
  const note = $("textarea", { placeholder: "Note (optional)" });
  note.value = r.note || "";
  let timer;
  note.oninput = () => { clearTimeout(timer); timer = setTimeout(() => {
    r.note = note.value; save(story.id, { note: note.value }, status); }, 700); };
  section.append($("div", { class: "verdict" },
    $("strong", {}, "Which set reads best as one story?"), choices, note, status));
  return section;
}

document.getElementById("next").onclick = () => {
  const next = DATA.stories.find(s => !RATINGS[s.id]?.best);
  if (next) document.getElementById("s-" + next.id).scrollIntoView({ behavior: "smooth" });
};

fetch("/data").then(r => r.json()).then(data => {
  DATA = data; RATINGS = data.ratings || {};
  const list = document.getElementById("stories");
  if (!data.stories.length) list.append($("p", {}, "Nothing to review yet — run `run.py draw` first."));
  data.stories.forEach(story => list.append(render(story)));
  updateCount();
});
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--host", default="127.0.0.1",
                        help="address to listen on; the laptop's Tailscale IP to reach it from a tablet")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    if not (OUT / "stories.json").exists():
        raise SystemExit("No stories yet: run `run.py fetch` and `run.py draw` first.")
    Handler.stories, Handler.key = build()
    sets = sum(len(story["labels"]) for story in Handler.stories)
    print(f"{len(Handler.stories)} stories ready to review ({sets} sets)")
    print(f"open http://{args.host}:{args.port}/  — Ctrl-C to stop; labels are saved as you tap")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
