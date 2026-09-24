"""Redraw a story's later pictures with its earlier pictures as references, to be compared blind.

The question is in the README. This file is the apparatus: `probe` checks the call path on one
synthetic picture, `fetch` copies the owner's stories and their stored pictures down, `draw` makes
the conditioned sets, and `report` unblinds the labels `review.py` collected.

    export ACERVO_VERTEX_PROJECT=…
    .venv/bin/python experiments/story-picture-reference/run.py probe
    .venv/bin/python experiments/story-picture-reference/run.py fetch --server-url … --email …
    .venv/bin/python experiments/story-picture-reference/run.py draw
    .venv/bin/python experiments/story-picture-reference/run.py report

Part 1 is never redrawn: it is the stored picture in every set, so the sets differ only in what
conditioning did to the parts after it. Nothing here writes to the server.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import io
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from acervo.client import AcervoClient, AcervoError
from acervo.images.render import encode_master
from acervo.images.styles import load_styles
from acervo.models import call, load_catalogue
from acervo.models.catalogue import reason as unmet
from acervo.models.errors import ProviderRefused, ProviderUnavailable
from acervo.stories.illustrate import compose

HERE = Path(__file__).resolve().parent
# Overridable so the page can be tried on made-up stories without touching a real run.
OUT = Path(os.environ.get("STORY_PICTURES_OUT") or HERE / "out")
PREAMBLE = (HERE / "reference_preamble.md").read_text(encoding="utf-8").strip()

PROVIDER = "vertex"
MODEL = "vertex_ai/gemini-3.1-flash-lite-image"
# Sent as a generation setting rather than as `size`: on the chat path LiteLLM copies any
# `GenerationConfig` field it is given into `generationConfig`, and this is the one that carries the
# resolution. `probe` is what checks it arrived.
IMAGE_CONFIG = {"imageSize": "1K", "aspectRatio": "1:1"}
TIMEOUT = 180

MAIN_ARM = "first+prev"
VARIANT_ARMS = ("prev", "first")
ARMS = (MAIN_ARM, *VARIANT_ARMS)
RECENT = 5
# The rests `src/acervo/work/` uses for the same three conditions: 30 s, doubling, ten minutes.
FIRST_REST, LONGEST_REST = 30.0, 600.0


# ── the call ────────────────────────────────────────────────────────────────


def references_for(arm: str, index: int) -> list[tuple[str, int]]:
    """Which earlier pictures part `index` (0-based, ≥ 1) is drawn from, as (set, index) pairs.

    Part 0 is `original` in every set. `first+prev` sends part 0 and the new picture before this
    one, which for part 1 is part 0 itself — sent once, not twice.
    """
    previous = ("original" if index - 1 == 0 else arm, index - 1)
    if arm == "first":
        return [("original", 0)]
    if arm == "prev":
        return [previous]
    if arm == MAIN_ARM:
        return [("original", 0)] if index == 1 else [("original", 0), previous]
    raise ValueError(f"unknown arm {arm!r}")


def attached_sentence(arm: str, index: int) -> str:
    if index == 1:
        return ("The picture attached is an earlier illustration from the same illustrated story: "
                "its opening picture, which is also the one immediately before this moment.")
    if arm == "first":
        return ("The picture attached is an earlier illustration from the same illustrated story: "
                "its opening picture.")
    if arm == "prev":
        return ("The picture attached is an earlier illustration from the same illustrated story: "
                "the one immediately before this moment.")
    return ("The two pictures attached are earlier illustrations from the same illustrated story: "
            "the first is its opening picture, the second is the one immediately before this moment.")


def prompt_for(arm: str, index: int, picture: str) -> str:
    return PREAMBLE.replace("{attached}", attached_sentence(arm, index)).replace("{picture}", picture)


def draw_with_references(prompt: str, references: list[bytes]) -> tuple[bytes, dict[str, Any]]:
    """One picture from one prompt and some reference images, through LiteLLM's chat path.

    `call.image` is text-only — LiteLLM's `image_generation` for Vertex Gemini takes no image — so
    this is the path an integration would use, and part of what the spike checks. Errors are
    classified by `call._raise`, which raises `ProviderUnavailable` or `ProviderRefused`.
    """
    row = load_catalogue().find(PROVIDER)
    content: list[dict[str, Any]] = [
        {"type": "image_url",
         "image_url": {"url": f"data:{_mime(data)};base64,{base64.b64encode(data).decode()}"}}
        for data in references
    ]
    content.append({"type": "text", "text": prompt})
    request = {
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "modalities": ["image", "text"],
        "imageConfig": IMAGE_CONFIG,
        "timeout": row.timeout_for("image", TIMEOUT),
        "vertex_location": row.params_for("image").get("vertex_location", "global"),
        **call._transport(row),
    }
    started = time.monotonic()
    try:
        response = call.completion(**request)
    except Exception as error:  # noqa: BLE001
        call._raise(row, MODEL, error)
        raise
    seconds = time.monotonic() - started
    message = response.choices[0].message
    images = getattr(message, "images", None) or []
    if not images:
        said = (getattr(message, "content", None) or "").strip()[:300]
        raise ProviderRefused("refused", f"no image came back{': ' + said if said else ''}",
                              provider_id=row.id, model=MODEL)
    url = images[0]["image_url"]["url"]
    raw = base64.b64decode(url.split(",", 1)[1])
    with Image.open(io.BytesIO(raw)) as drawn:
        size = drawn.size
    usage = getattr(response, "usage", None)
    return raw, {
        "seconds": round(seconds, 2),
        "costUsd": call._cost(response),
        "drawnSize": list(size),
        "promptTokens": getattr(usage, "prompt_tokens", None),
        "completionTokens": getattr(usage, "completion_tokens", None),
    }


def _mime(data: bytes) -> str:
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return "image/jpeg"


def _login_expired(error: Exception) -> bool:
    """LiteLLM reports an expired Google login as a connection error, which would otherwise rest."""
    return "Reauthentication is needed" in str(error) or "RefreshError" in str(error)


LOGIN_HINT = ("The Google login has expired. Run `gcloud auth application-default login` with the "
              "account that should pay, then rerun.")


def _ready() -> None:
    problem = unmet(load_catalogue().find(PROVIDER))
    if problem:
        sys.exit(f"Vertex cannot be called from this machine: {problem}.")


# ── probe ───────────────────────────────────────────────────────────────────


def probe(_: argparse.Namespace) -> None:
    """One picture from a synthetic reference, to see the path work before an hour is spent on it."""
    _ready()
    sheet = Image.new("RGB", (1024, 1024), (236, 226, 204))
    pen = ImageDraw.Draw(sheet)
    pen.ellipse((380, 180, 640, 440), fill=(214, 170, 130))              # a head
    pen.rectangle((360, 440, 660, 860), fill=(46, 110, 70))              # a green jacket
    pen.ellipse((430, 270, 480, 320), outline=(20, 20, 20), width=8)     # round glasses
    pen.ellipse((540, 270, 590, 320), outline=(20, 20, 20), width=8)
    buffer = io.BytesIO()
    sheet.save(buffer, format="WEBP", quality=88)

    picture = ("A man of about thirty in a green jacket and round glasses sits on a park bench "
               "feeding pigeons, seen from the side. Soft afternoon light. A single illustration, "
               "fully rendered. Absolutely no text anywhere in the image.")
    try:
        raw, facts = draw_with_references(prompt_for("first", 2, picture), [buffer.getvalue()])
    except (ProviderUnavailable, ProviderRefused) as error:
        sys.exit(LOGIN_HINT if _login_expired(error) else f"{error.reason}: {error}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "probe-reference.webp").write_bytes(buffer.getvalue())
    (OUT / "probe.webp").write_bytes(encode_master(raw))
    print(json.dumps({**facts, "mime": _mime(raw), "bytes": len(raw)}, indent=2))
    print(f"wrote {OUT / 'probe.webp'} (reference: {OUT / 'probe-reference.webp'})")
    if facts["drawnSize"] != [1024, 1024]:
        print(f"note: drawn at {facts['drawnSize']}, not 1024×1024 — imageConfig did not arrive")


# ── fetch ───────────────────────────────────────────────────────────────────


def fetch(args: argparse.Namespace) -> None:
    password = getpass.getpass(f"Password for {args.email}: ")
    with AcervoClient(args.server_url) as client:
        try:
            client.sign_in(args.email, password)
            changes = client.pull_graph(0)["changes"]
        except AcervoError as error:
            sys.exit(str(error))

        parts_of: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for part in changes.get("storyParts", []):
            if not part.get("deleted"):
                parts_of[part["storyId"]].append(part)

        kept, skipped = [], []
        for story in changes.get("stories", []):
            if story.get("deleted"):
                continue
            parts = sorted(parts_of.get(story["id"], []), key=lambda part: part.get("position", 0))
            label = f"{story.get('createdAt', '')[:10]} {story.get('title') or story['id']}"
            if len(parts) < 2:
                skipped.append((label, f"{len(parts)} part(s)"))
                continue
            undrawn = [index + 1 for index, part in enumerate(parts) if not part.get("imageRef")]
            if undrawn:
                skipped.append((label, f"part(s) {undrawn} have no picture yet"))
                continue
            unbriefed = [index + 1 for index, part in enumerate(parts)
                         if not (part.get("imagePrompt") or "").strip()]
            if unbriefed:
                skipped.append((label, f"part(s) {unbriefed} have no brief"))
                continue

            folder = OUT / story["id"] / "original"
            folder.mkdir(parents=True, exist_ok=True)
            for index, part in enumerate(parts):
                target = folder / f"part-{index + 1}.webp"
                if target.exists():
                    continue
                response = client.fetch("GET", f"/api/acervo/media/{part['imageRef']}")
                if response.status_code != 200:
                    sys.exit(f"{label}: picture {index + 1} answered {response.status_code}")
                target.write_bytes(response.content)
            kept.append({
                "id": story["id"],
                "title": story.get("title") or "",
                "titleTranslation": story.get("titleTranslation") or "",
                "emoji": story.get("emoji") or "",
                "language": story.get("language") or "",
                "createdAt": story.get("createdAt") or "",
                "styleId": story.get("styleId") or "",
                "parts": [{
                    "heading": part.get("heading") or "",
                    "text": part.get("text") or "",
                    "translation": part.get("translation") or "",
                    "imagePrompt": part.get("imagePrompt") or "",
                    "imageModelId": part.get("imageModelId") or "",
                } for part in parts],
            })

    kept.sort(key=lambda story: story["createdAt"])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "stories.json").write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
    for story in kept:
        models = sorted({part["imageModelId"] for part in story["parts"]})
        print(f"  {story['createdAt'][:16]}  {len(story['parts'])} parts  "
              f"{story['styleId']:<24} {', '.join(models)}  {story['title']}")
    for label, why in skipped:
        print(f"  skipped: {label} — {why}")
    pictures = sum(len(story["parts"]) - 1 for story in kept)
    print(f"{len(kept)} stories kept; the main set is {pictures} pictures, "
          f"about ${pictures * 0.0342:.2f}")


# ── draw ────────────────────────────────────────────────────────────────────


def _stories() -> list[dict[str, Any]]:
    path = OUT / "stories.json"
    if not path.exists():
        sys.exit("No stories yet: run `fetch` first.")
    return json.loads(path.read_text(encoding="utf-8"))


def _picture(story_id: str, arm: str, index: int) -> Path:
    return OUT / story_id / arm / f"part-{index + 1}.webp"


def _log(entry: dict[str, Any]) -> None:
    with (OUT / "draws.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(entry, ensure_ascii=False) + "\n")


def draw(args: argparse.Namespace) -> None:
    _ready()
    stories = _stories()
    styles = load_styles()
    variants_story = args.variants_story or (stories[-1]["id"] if stories else "")
    if variants_story and variants_story not in {story["id"] for story in stories}:
        sys.exit(f"--variants-story {variants_story} is not in stories.json")

    plan: list[tuple[dict[str, Any], str]] = [(story, MAIN_ARM) for story in stories]
    if not args.no_variants:
        plan += [(story, arm) for story in stories if story["id"] == variants_story
                 for arm in VARIANT_ARMS]
    total = sum(len(story["parts"]) - 1 for story, _arm in plan)
    done = sum(1 for story, arm in plan for index in range(1, len(story["parts"]))
               if _picture(story["id"], arm, index).exists())
    print(f"{done} of {total} pictures already drawn; variants on {variants_story or 'no story'}")

    spent, drawn_now = 0.0, 0
    for story, arm in plan:
        if story["styleId"] not in styles:
            print(f"skip {story['title']}: style {story['styleId']!r} is not in this checkout")
            continue
        style = styles[story["styleId"]]
        for index in range(1, len(story["parts"])):
            target = _picture(story["id"], arm, index)
            if target.exists():
                continue
            if args.limit is not None and drawn_now >= args.limit:
                print(f"stopped at --limit {args.limit}; ${spent:.2f} spent this run")
                return
            wanted = references_for(arm, index)
            missing = [f"{set_}/{i + 1}" for set_, i in wanted
                       if not _picture(story["id"], set_, i).exists()]
            if missing:
                print(f"skip {story['title']} [{arm}] part {index + 1}: no reference {missing}")
                break
            references = [_picture(story["id"], set_, i).read_bytes() for set_, i in wanted]
            prompt = prompt_for(arm, index, compose(story["parts"][index]["imagePrompt"], style))

            rest = FIRST_REST
            while True:
                entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "story": story["id"],
                         "arm": arm, "part": index + 1,
                         "references": [f"{set_}/part-{i + 1}" for set_, i in wanted]}
                try:
                    raw, facts = draw_with_references(prompt, references)
                except ProviderUnavailable as waiting:
                    if _login_expired(waiting):
                        sys.exit(LOGIN_HINT)
                    _log({**entry, "error": waiting.reason, "message": str(waiting)[:300]})
                    print(f"  {waiting.reason}: resting {rest:.0f} s ({str(waiting)[:120]})")
                    time.sleep(rest)
                    rest = min(rest * 2, LONGEST_REST)
                    continue
                except ProviderRefused as refused:
                    _log({**entry, "error": refused.reason, "message": str(refused)[:300]})
                    print(f"  refused: {story['title']} [{arm}] part {index + 1}: {refused}")
                    if refused.reason in ("authentication", "configuration"):
                        sys.exit("That is a setup problem, not this picture — fix it and rerun.")
                    break
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(encode_master(raw))
                _log({**entry, **facts})
                spent += facts["costUsd"] or 0.0
                drawn_now += 1
                done += 1
                print(f"  {done}/{total}  {story['createdAt'][:10]} {story['title'][:40]:<40} "
                      f"[{arm}] part {index + 1}  {facts['seconds']:.0f} s  "
                      f"${facts['costUsd'] or 0:.4f}  (run ${spent:.2f})")
                break
            if not target.exists():
                break  # refused: later parts would chain from a picture that does not exist
    print(f"done: {drawn_now} drawn this run, ${spent:.2f}")


# ── report ──────────────────────────────────────────────────────────────────


def report(_: argparse.Namespace) -> None:
    stories = {story["id"]: story for story in _stories()}
    key = json.loads((OUT / "key.json").read_text(encoding="utf-8"))
    ratings = json.loads((OUT / "ratings.json").read_text(encoding="utf-8"))
    order = sorted(stories, key=lambda story_id: stories[story_id]["createdAt"])
    recent = set(order[-RECENT:])

    best: dict[str, Counter] = {"recent": Counter(), "older": Counter()}
    flags: dict[str, Counter] = defaultdict(Counter)
    rated = 0
    for story_id in order:
        rating = ratings.get(story_id)
        if not rating or story_id not in key:
            continue
        labels = key[story_id]
        group = "recent" if story_id in recent else "older"
        choice = rating.get("best") or ""
        if choice:
            rated += 1
            best[group][labels.get(choice, "no difference")] += 1
        for label, marks in (rating.get("flags") or {}).items():
            for mark, on in marks.items():
                if on:
                    flags[labels[label]][mark] += 1
        unblinded = {label: arm for label, arm in labels.items()}
        print(f"{stories[story_id]['createdAt'][:10]}  {stories[story_id]['title'][:44]:<44} "
              f"best: {unblinded.get(choice, choice or '—'):<14} "
              f"{'  note: ' + rating['note'] if rating.get('note') else ''}")

    print(f"\n{rated} stories with a preference")
    for group in ("recent", "older"):
        print(f"  {group:<7} " + ", ".join(f"{arm} {count}" for arm, count in best[group].most_common()))
    print("flags (sets marked):")
    for arm, marks in sorted(flags.items()):
        print(f"  {arm:<12} " + ", ".join(f"{mark} {count}" for mark, count in marks.items()))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("probe", help="one picture from a synthetic reference (~$0.03)")
    fetching = commands.add_parser("fetch", help="copy the stories and their pictures down")
    fetching.add_argument("--server-url", required=True)
    fetching.add_argument("--email", required=True)
    drawing = commands.add_parser("draw", help="draw the conditioned sets; safe to stop and rerun")
    drawing.add_argument("--variants-story", help="story id for the two extra sets (default: newest)")
    drawing.add_argument("--no-variants", action="store_true", help="the main set only")
    drawing.add_argument("--limit", type=int, help="stop after this many pictures")
    commands.add_parser("report", help="unblind the labels")
    args = parser.parse_args(argv)
    {"probe": probe, "fetch": fetch, "draw": draw, "report": report}[args.command](args)


if __name__ == "__main__":
    main()
