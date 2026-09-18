#!/usr/bin/env python3
"""Layer 3: twenty-five screens, and what they are worth.

The human is not the measurement here — the judge is, over all 180 pairs. These screens are the
**calibration set** that says how much the judge's verdict can be trusted, as a number (Cohen's κ)
that every later prompt experiment inherits.

Stratified, because sampling uniformly spends most of the attention on pairs nobody disagrees about:
the judge's confident calls, the ones where it flipped between orderings, the ones where it
disagrees with the counts, a random anchor — and four **controls** that are two repeats of the same
arm. A declared winner on a control is a false positive, and that rate is the reader's own noise
floor. Without it there is no way to know how much of any signal is real, so nothing on screen says
which four they are.
"""

from __future__ import annotations

import argparse
import json
import difflib
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import dataset
import render

from acervo.errors import ApiError
from acervo.services.capture.draft import draft_from

HERE = Path(__file__).resolve().parent
SEED = 20260918
WANTED = {"confident": 8, "flipped": 5, "disagrees": 5, "random": 3, "control": 4}


def records_of(run_dir: Path) -> dict[tuple, dict[str, Any]]:
    out: dict[tuple, dict[str, Any]] = {}
    for path in sorted(run_dir.rglob("*.json")):
        if path.name in ("manifest.json", "summary.json", "review-key.json", "ratings.json") \
                or "judged" in path.parts:
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        if "wordId" in record and "arm" in record:
            out[(record["arm"], record["provider"], record["model"], record["wordId"], record["repeat"])] = record
    return out


def judgements(run_dir: Path) -> dict[tuple, dict[str, str | None]]:
    """Per comparison: the arm each ordering chose, so a flip is visible."""
    out: dict[tuple, dict[str, str | None]] = defaultdict(dict)
    for path in sorted((run_dir / "judged").rglob("*.json")) if (run_dir / "judged").exists() else []:
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("ok"):
            key = (record["provider"], record["model"], record["wordId"], record["repeat"])
            out[key][record["order"]] = record.get("winnerArm")
    return out


def consensus(votes: dict[str, str | None]) -> tuple[str, bool]:
    """The judge's answer for one comparison, and whether the two orderings disagreed."""
    values = [v for v in votes.values() if v]
    if len(values) < 2:
        return (values[0] if values else "same", False)
    if values[0] != values[1]:
        return ("same", True)
    return (values[0], False)


def diff_rows(left: str, right: str) -> tuple[list, list]:
    """Two aligned line lists, VS Code style: same, changed, only-left, only-right.

    Both sides are shown whole and unedited — the highlighting says which rows differ, it does not
    replace reading them. Filler rows keep the two columns aligned, which is the only reason a
    side-by-side diff is easier than two files.
    """
    a, b = left.splitlines(), right.splitlines()
    out_a: list[list] = []
    out_b: list[list] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag == "equal":
            out_a += [["eq", line] for line in a[i1:i2]]
            out_b += [["eq", line] for line in b[j1:j2]]
            continue
        chunk_a = [["chg" if tag == "replace" else "del", line] for line in a[i1:i2]]
        chunk_b = [["chg" if tag == "replace" else "ins", line] for line in b[j1:j2]]
        while len(chunk_a) < len(chunk_b):
            chunk_a.append(["pad", ""])
        while len(chunk_b) < len(chunk_a):
            chunk_b.append(["pad", ""])
        out_a += chunk_a
        out_b += chunk_b
    return out_a, out_b


def draft_for(record: dict[str, Any], word: dict[str, Any]) -> dict[str, Any] | None:
    if not record.get("parsedJson") or not isinstance(record.get("reply"), dict):
        return None
    try:
        return draft_from(record["reply"], dataset.resolution_for(word), dataset.request_for(word),
                          dataset.vocabulary_for(word), dataset.topics(), record["model"])
    except ApiError:
        return None


def build(run_dir: Path) -> int:
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    rows = {(r["arm"], r["provider"], r["model"], r["wordId"], r["repeat"]): r for r in summary["rows"]}
    records = records_of(run_dir)
    votes = judgements(run_dir)
    by_id = {word["id"]: word for word in dataset.words()}
    rng = random.Random(SEED)

    pools: dict[str, list[tuple]] = defaultdict(list)
    for key, vote in votes.items():
        arm_winner, flipped = consensus(vote)
        before = rows.get(("before", key[0], key[1], key[2], key[3]))
        after = rows.get(("after", key[0], key[1], key[2], key[3]))
        if not before or not after or not before.get("draftBuilt") or not after.get("draftBuilt"):
            continue
        counts_favour = "same"
        if after["senses"] > before["senses"] or after["noteChars"] > before["noteChars"] * 1.25:
            counts_favour = "after"
        elif after["senses"] < before["senses"] or after["noteChars"] * 1.25 < before["noteChars"]:
            counts_favour = "before"
        if flipped:
            pools["flipped"].append(key)
        elif arm_winner != "same" and counts_favour not in ("same", arm_winner):
            pools["disagrees"].append(key)
        elif arm_winner != "same":
            pools["confident"].append(key)
        pools["random"].append(key)

    screens: list[dict[str, Any]] = []
    taken: set[tuple] = set()
    for stratum in ("confident", "flipped", "disagrees", "random"):
        candidates = [k for k in pools[stratum] if k not in taken]
        rng.shuffle(candidates)
        for key in candidates[:WANTED[stratum]]:
            taken.add(key)
            provider, model, word_id, repeat = key
            left_arm, right_arm = ("before", "after") if rng.random() < 0.5 else ("after", "before")
            screens.append({
                "kind": "real", "stratum": stratum, "wordId": word_id, "repeat": repeat,
                "provider": provider, "model": model, "leftArm": left_arm, "rightArm": right_arm,
                "judge": consensus(votes[key])[0], "flipped": consensus(votes[key])[1],
            })

    # Controls: two repeats of the SAME arm, shown exactly like a real pair.
    controls: list[tuple] = []
    for (arm, provider, model, word_id, repeat), row in rows.items():
        if arm != "before" or not row.get("draftBuilt") or repeat != 0:
            continue
        other = rows.get((arm, provider, model, word_id, 1))
        if other and other.get("draftBuilt"):
            controls.append((provider, model, word_id))
    rng.shuffle(controls)
    for provider, model, word_id in controls[:WANTED["control"]]:
        screens.append({
            "kind": "control", "stratum": "control", "wordId": word_id,
            "provider": provider, "model": model, "leftRepeat": 0, "rightRepeat": 1, "arm": "before",
        })

    rng.shuffle(screens)
    pages = []
    for index, screen in enumerate(screens, start=1):
        word = by_id[screen["wordId"]]
        if screen["kind"] == "real":
            left = records[(screen["leftArm"], screen["provider"], screen["model"], screen["wordId"], screen["repeat"])]
            right = records[(screen["rightArm"], screen["provider"], screen["model"], screen["wordId"], screen["repeat"])]
        else:
            left = records[(screen["arm"], screen["provider"], screen["model"], screen["wordId"], 0)]
            right = records[(screen["arm"], screen["provider"], screen["model"], screen["wordId"], 1)]
        drafts = (draft_for(left, word), draft_for(right, word))
        if not all(drafts):
            continue
        screen["id"] = f"s{index:02d}"
        rows_a, rows_b = diff_rows(render.as_yaml(drafts[0], left.get("reply"), blind=True),
                                   render.as_yaml(drafts[1], right.get("reply"), blind=True))
        pages.append({
            "id": screen["id"], "headword": word["headword"], "language": word["language"],
            "left": rows_a, "right": rows_b,
        })

    out = run_dir / "review"
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page_html(pages), encoding="utf-8")
    (run_dir / "review-key.json").write_text(
        json.dumps({"seed": SEED, "screens": screens}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    counts = Counter(s["stratum"] for s in screens if "id" in s)
    print(f"{len(pages)} screen(s) in {out / 'index.html'}")
    print("  " + " · ".join(f"{name} {counts[name]}" for name in WANTED))
    print(f"  key written to {run_dir / 'review-key.json'} — not shown on the page")
    return 0


def page_html(pages: list[dict[str, Any]]) -> str:
    data = json.dumps(pages, ensure_ascii=False)
    return """<!doctype html>
<meta charset="utf-8">
<title>compose-lesson-line · blind review</title>
<style>
 :root { color-scheme: light dark; }
 body { margin: 0; font: 14px/1.5 ui-sans-serif, system-ui, sans-serif; }
 header { display: flex; gap: 16px; align-items: baseline; padding: 10px 16px;
          border-bottom: 1px solid #8884; position: sticky; top: 0; background: Canvas; }
 h1 { font-size: 15px; margin: 0; font-weight: 600; }
 .word { font-size: 18px; font-weight: 600; }
 .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0; }
 .col { padding: 12px 16px; min-width: 0; }
 .col + .col { border-left: 1px solid #8884; }
 .tag { font-size: 12px; letter-spacing: .08em; text-transform: uppercase; opacity: .55; }
 .rows { font: 12.5px/1.6 ui-monospace, monospace; margin: 6px 0 0; }
 .rows div { white-space: pre-wrap; word-break: break-word; padding: 0 6px;
             border-left: 3px solid transparent; }
 .del { background: rgba(240,90,90,.15); border-left-color: rgba(240,90,90,.7) !important; }
 .ins { background: rgba(70,190,120,.15); border-left-color: rgba(70,190,120,.7) !important; }
 .chg { background: rgba(110,160,255,.15); border-left-color: rgba(110,160,255,.7) !important; }
 .pad { background: rgba(128,128,128,.07); min-height: 1.6em; }
 .legend { font-size: 12px; opacity: .6; display: flex; gap: 12px; }
 .notes { padding: 10px 16px; border-top: 1px solid #8884; }
 .notes label { display: block; font-size: 12px; opacity: .6; margin-bottom: 5px; }
 .notes textarea { width: 100%; box-sizing: border-box; font: inherit; padding: 6px 8px;
                   border: 1px solid #8886; border-radius: 6px; background: transparent;
                   resize: vertical; }
 .legend span::before { content: "\2588\2009"; }
 .legend .c1::before { color: rgba(110,160,255,.8); }
 .legend .c2::before { color: rgba(70,190,120,.8); }
 .legend .c3::before { color: rgba(240,90,90,.8); }
 footer { position: sticky; bottom: 0; background: Canvas; border-top: 1px solid #8884;
          padding: 10px 16px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
 button { font: inherit; padding: 5px 12px; border: 1px solid #8886; border-radius: 6px;
          background: transparent; cursor: pointer; }
 button.on { background: #4884; }
 .spacer { flex: 1; }
 .done { padding: 40px 16px; font-size: 16px; }
 kbd { font: 12px ui-monospace, monospace; border: 1px solid #8886; border-radius: 4px;
       padding: 0 4px; }
</style>
<header>
 <h1>blind review</h1>
 <span class="word" id="word"></span>
 <span class="tag" id="lang"></span>
 <span class="spacer"></span>
 <span class="legend"><span class="c1">changed</span><span class="c2">only B</span><span class="c3">only A</span></span>
 <span class="tag" id="progress"></span>
</header>
<div id="body">
 <div class="grid">
  <div class="col"><span class="tag">A</span><div class="rows" id="left"></div></div>
  <div class="col"><span class="tag">B</span><div class="rows" id="right"></div></div>
 </div>
 <div class="notes">
  <label for="note">Anything worth saying about this pair — what differs, and whether it matters.
   Optional, and saved with the rating.</label>
  <textarea id="note" rows="2" placeholder="e.g. B adds a sense that is really the same meaning"></textarea>
 </div>
</div>
<footer>
 <button data-choice="left">&larr; A better</button>
 <button data-choice="right">B better &rarr;</button>
 <button data-choice="mixed"><kbd>m</kbd> both differ, neither better</button>
 <button data-choice="same"><kbd>=</kbd> no difference I can see</button>
 <span class="tag">how much</span>
 <button data-mag="1">1 slight</button>
 <button data-mag="2">2 clear</button>
 <button data-mag="3">3 large</button>
 <span class="spacer"></span>
 <button id="back">back</button>
 <button id="save"><b>download ratings.json</b></button>
</footer>
<script>
const PAGES = __DATA__;
const ratings = JSON.parse(localStorage.getItem("clr-ratings") || "{}");
let at = 0, magnitude = 2;
const $ = (id) => document.getElementById(id);
function paint(host, rows) {
  host.replaceChildren(...rows.map(([cls, text]) => {
    const line = document.createElement("div");
    line.className = cls;
    line.textContent = text || "\u00a0";
    return line;
  }));
}
function draw() {
  if (at >= PAGES.length) {
    $("body").innerHTML = '<div class="done">All ' + PAGES.length +
      ' done. Press <b>download ratings.json</b> and drop the file into the run directory.</div>';
    $("word").textContent = ""; $("lang").textContent = "";
    $("progress").textContent = PAGES.length + " / " + PAGES.length;
    return;
  }
  const page = PAGES[at];
  $("word").textContent = page.headword;
  $("lang").textContent = page.language;
  paint($("left"), page.left);
  paint($("right"), page.right);
  $("progress").textContent = (at + 1) + " / " + PAGES.length;
  for (const b of document.querySelectorAll("[data-mag]"))
    b.classList.toggle("on", Number(b.dataset.mag) === magnitude);
  $("note").value = (ratings[page.id] && ratings[page.id].note) || "";
}
function choose(choice) {
  if (at >= PAGES.length) return;
  const decided = choice === "left" || choice === "right";
  ratings[PAGES[at].id] = {
    choice,
    magnitude: decided ? magnitude : 0,
    note: $("note").value.trim(),
  };
  localStorage.setItem("clr-ratings", JSON.stringify(ratings));
  at += 1; draw();
}
for (const b of document.querySelectorAll("[data-choice]"))
  b.onclick = () => choose(b.dataset.choice);
for (const b of document.querySelectorAll("[data-mag]"))
  b.onclick = () => { magnitude = Number(b.dataset.mag); draw(); };
$("back").onclick = () => { at = Math.max(0, at - 1); draw(); };
$("save").onclick = () => {
  const blob = new Blob([JSON.stringify(ratings, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = "ratings.json"; a.click();
};
addEventListener("keydown", (e) => {
  // The note field takes the keyboard while it has focus, or typing "m" would rate the screen.
  if (e.target && e.target.tagName === "TEXTAREA") return;
  if (e.key === "ArrowLeft") choose("left");
  else if (e.key === "ArrowRight") choose("right");
  else if (e.key === "=" || e.key === " ") { e.preventDefault(); choose("same"); }
  else if (e.key === "m") choose("mixed");
  else if (["1", "2", "3"].includes(e.key)) { magnitude = Number(e.key); draw(); }
  else if (e.key === "Backspace") { e.preventDefault(); at = Math.max(0, at - 1); draw(); }
});
draw();
</script>
""".replace("__DATA__", data)


def kappa(one: list[str], two: list[str]) -> float | None:
    """Cohen's κ over the three-way label."""
    if not one:
        return None
    labels = sorted(set(one) | set(two))
    agree = sum(a == b for a, b in zip(one, two)) / len(one)
    expected = sum((one.count(k) / len(one)) * (two.count(k) / len(two)) for k in labels)
    return None if expected >= 1 else round((agree - expected) / (1 - expected), 3)


def score(run_dir: Path) -> int:
    key = json.loads((run_dir / "review-key.json").read_text(encoding="utf-8"))
    path = run_dir / "ratings.json"
    if not path.exists():
        raise SystemExit(f"no ratings.json in {run_dir} — download it from the page first")
    ratings = json.loads(path.read_text(encoding="utf-8"))
    screens = {s["id"]: s for s in key["screens"] if "id" in s}

    # A winner on a control is the false positive. `mixed` and `same` are both honest answers
    # there — two generations of one arm DO differ in wording, which is exactly why the option set
    # needed a fourth answer.
    decided = ("left", "right")
    controls = [s for s in screens.values() if s["kind"] == "control" and s["id"] in ratings]
    called = [s for s in controls if ratings[s["id"]]["choice"] in decided]
    print("\n### The controls — two articles from the same arm\n")
    print(f"{len(called)} of {len(controls)} control screens were given a winner. "
          f"That is the reader's false-positive rate: **{len(called) / len(controls) * 100:.0f}%**"
          if controls else "no control screens were rated")

    mine: list[str] = []
    theirs: list[str] = []
    for screen in screens.values():
        if screen["kind"] != "real" or screen["id"] not in ratings:
            continue
        choice = ratings[screen["id"]]["choice"]
        # `mixed` is not a preference, so it joins `same` for the win rate — but it was counted
        # separately above, because "I see changes that trade off" is a different observation from
        # "these look identical", and only the first says the reader perceived the change at all.
        mine.append("same" if choice in ("same", "mixed") else screen[f"{choice}Arm"])
        theirs.append(screen["judge"])
    # Side bias. Left and right were randomised against the arm per screen, so a lean here is a
    # fact about the reader rather than about the prompts — and a large one is evidence that the
    # screens were being read by position because there was no content signal to read.
    rated = [ratings[s["id"]] for s in screens.values() if s["id"] in ratings]
    sides = Counter(r["choice"] for r in rated)
    strength = Counter(r["magnitude"] for r in rated)
    print("\n### How the calls were made\n")
    print(f"By side: left {sides['left']} · right {sides['right']} · "
          f"both differ, neither better {sides['mixed']} · no difference {sides['same']}")
    print(f"By strength: slight {strength[1]} · clear {strength[2]} · large {strength[3]}")
    notes = [(s["id"], ratings[s["id"]].get("note", "")) for s in sorted(screens.values(), key=lambda s: s["id"])
             if s["id"] in ratings and ratings[s["id"]].get("note")]
    if notes:
        print("\n### What the reader wrote\n")
        for screen_id, note in notes:
            kind = screens[screen_id]["stratum"]
            print(f"- **{screen_id}** ({kind}) — {note}")

    print("\n### Against the judge\n")
    if mine:
        agree = sum(a == b for a, b in zip(mine, theirs)) / len(mine)
        print(f"| n | agreement | Cohen's κ | you said | the judge said |")
        print(f"| ---: | ---: | ---: | --- | --- |")
        print(f"| {len(mine)} | {agree * 100:.0f}% | {kappa(mine, theirs)} "
              f"| {dict(Counter(mine))} | {dict(Counter(theirs))} |")
    else:
        print("no real screens were rated")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "score"))
    parser.add_argument("run")
    args = parser.parse_args()
    run_dir = Path(args.run)
    if not run_dir.is_absolute() and not run_dir.exists():
        run_dir = HERE / args.run
    return build(run_dir) if args.action == "build" else score(run_dir)


if __name__ == "__main__":
    raise SystemExit(main())
