"""Redraw a story's pictures with the earlier pictures of the same people and places as references.

The question is in the README. This file is the apparatus:

- `probe` checks the call path on one synthetic picture;
- `fetch` copies the owner's stories and their stored pictures down;
- `prepare` asks a text model which characters and scene each picture shows, prints which earlier
  pictures every part would be given, and writes every prompt it would send to `out/prompts/` —
  all before anything is spent on a picture;
- `draw` makes the sets;
- `report` unblinds the labels `review.py` collected.

    .venv/bin/python experiments/story-picture-reference/run.py probe
    .venv/bin/python experiments/story-picture-reference/run.py fetch --server-url … --email …
    .venv/bin/python experiments/story-picture-reference/run.py prepare
    .venv/bin/python experiments/story-picture-reference/run.py draw
    .venv/bin/python experiments/story-picture-reference/run.py report

**References are chosen by identity, not by position.** Part k is given the last earlier picture of
each character it shows, and the last earlier picture of its scene if the scene recurs — so a story
that moves from one man in a laboratory to a different man in a church sends nothing at all, rather
than handing the second man the first man's face. A part with nothing to carry over is not redrawn;
the set keeps its base picture. Nothing here writes to the server.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import io
import json
import os
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from PIL import Image, ImageDraw

from acervo.client import AcervoClient, AcervoError
from acervo.images.render import encode_master
from acervo.images.styles import load_styles
from acervo.models import call, chain, load_catalogue
from acervo.models.catalogue import reason as unmet
from acervo.models.errors import ChainExhausted, ProviderRefused, ProviderUnavailable
from acervo.pronunciation.speak import language_name
from acervo.stories.illustrate import BRIEF_PARAMS, compose

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
# Overridable so the apparatus can be tried on made-up stories without touching a real run.
OUT = Path(os.environ.get("STORY_PICTURES_OUT") or HERE / "out")
PREAMBLE = (HERE / "reference_preamble.md").read_text(encoding="utf-8").strip()
LABEL_PROMPT = (HERE / "prompts" / "continuity.md").read_text(encoding="utf-8").strip()
BRIEF_V2_PROMPT = (HERE / "prompts" / "story_brief_v2.md").read_text(encoding="utf-8").strip()

# The pictures: the model the stored stories were drawn with, on Vertex.
IMAGE_PROVIDER = "vertex"
IMAGE_MODEL = "vertex_ai/gemini-3.1-flash-lite-image"
# Sent as a generation setting rather than as `size`: on the chat path LiteLLM copies any
# `GenerationConfig` field it is given into `generationConfig`, and this is the one that carries the
# resolution. `probe` is what checks it arrived.
IMAGE_CONFIG = {"imageSize": "1K", "aspectRatio": "1:1"}
IMAGE_TIMEOUT = 180
PICTURE_USD = 0.0342  # $0.0336 a picture and about two references at $0.00028

# The words: the free Gemini tier, from GEMINI_API_KEY in `.env`.
TEXT_CHAIN = ["gemini-free"]
LABEL_PARAMS = {"temperature": 0.2}

MAX_REFERENCES = 3
RECENT = 5
# The rests `src/acervo/work/` uses for the same three conditions: 30 s, doubling, ten minutes.
FIRST_REST, LONGEST_REST = 30.0, 600.0

# Every set folder holds part-1…n. A part the set has nothing to carry over into is copied from its
# base rather than drawn: drawing it again would be the stored process with fresh dice, which buys
# noise and costs money. `v2` has no base, so every part of it is drawn, text-only.
SETS: dict[str, dict[str, Any]] = {
    "continuity": {"briefs": "stored", "labels": "labels", "base": "original"},
    "v2": {"briefs": "v2", "labels": None, "base": None},
    "v2+continuity": {"briefs": "v2", "labels": "v2", "base": "v2"},
}
SLUG = re.compile(r"^[a-z0-9][a-z0-9_]*$")

load_dotenv(REPO / ".env", override=False)


# ── who and where ───────────────────────────────────────────────────────────


def parse_continuity(payload: Any, count: int) -> dict[str, Any]:
    """Characters, scenes and each part's membership, or ValueError saying what is wrong."""
    if not isinstance(payload, dict):
        raise ValueError("the reply was not a JSON object")
    characters = {}
    for entry in payload.get("characters") or []:
        identifier = str(entry.get("id") or "").strip()
        if not SLUG.match(identifier):
            raise ValueError(f"character id {identifier!r} is not a slug")
        characters[identifier] = str(entry.get("description") or "").strip()
    scenes = {}
    for entry in payload.get("scenes") or []:
        identifier = str(entry.get("id") or "").strip()
        if not SLUG.match(identifier):
            raise ValueError(f"scene id {identifier!r} is not a slug")
        scenes[identifier] = str(entry.get("description") or "").strip()
    raw = payload.get("parts")
    if not isinstance(raw, list) or len(raw) != count:
        raise ValueError(f"the story has {count} parts and the reply has "
                         f"{len(raw) if isinstance(raw, list) else 'none'}")
    parts = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"part {index + 1} is not an object")
        who = [str(one).strip() for one in entry.get("characters") or []]
        unknown = [one for one in who if one not in characters]
        if unknown:
            raise ValueError(f"part {index + 1} names undeclared characters {unknown}")
        scene = str(entry.get("scene") or "").strip()
        if scene not in scenes:
            raise ValueError(f"part {index + 1} names undeclared scene {scene!r}")
        parts.append({"characters": list(dict.fromkeys(who)), "scene": scene,
                      "change": str(entry.get("change") or "").strip()})
    return {"characters": characters, "scenes": scenes, "parts": parts}


def parse_brief_v2(payload: Any, count: int) -> dict[str, Any]:
    """The v2 brief reply: the continuity fields plus one brief per part."""
    continuity = parse_continuity(payload, count)
    briefs = []
    for index, entry in enumerate(payload["parts"]):
        brief = str(entry.get("brief") or "").strip()
        if not brief:
            raise ValueError(f"brief {index + 1} is empty")
        briefs.append(brief)
    return {**continuity, "briefs": briefs}


def plan_references(continuity: dict[str, Any], index: int) -> list[tuple[int, list[str]]]:
    """For part `index` (0-based): [(earlier part, [ids it is chosen for])], oldest first.

    Each id this part shares with an earlier one — its characters, and its scene — is served by the
    **last** earlier part containing it. Several ids served by one part send that picture once. More
    than `MAX_REFERENCES` pictures keeps the most recent; the ids that loses are carried by the brief
    alone, which is what every picture relied on before references existed.
    """
    part = continuity["parts"][index]
    wanted = [*part["characters"], f"scene:{part['scene']}"]
    chosen: dict[int, list[str]] = defaultdict(list)
    for identifier in wanted:
        for earlier in range(index - 1, -1, -1):
            other = continuity["parts"][earlier]
            if identifier == f"scene:{other['scene']}" or identifier in other["characters"]:
                chosen[earlier].append(identifier)
                break
    kept = sorted(chosen)[-MAX_REFERENCES:]
    return [(earlier, chosen[earlier]) for earlier in kept]


def _name(identifier: str) -> str:
    return identifier.replace("_", " ").upper()


def reference_lines(continuity: dict[str, Any], index: int,
                    plan: list[tuple[int, list[str]]]) -> str:
    """One paragraph per reference: who to keep, whether its place applies, who in it to leave out."""
    part = continuity["parts"][index]
    paragraphs = []
    for number, (earlier, ids) in enumerate(plan, start=1):
        other = continuity["parts"][earlier]
        people = [one for one in ids if not one.startswith("scene:")]
        sentences = [f"Reference {number} is the picture from part {earlier + 1}."]
        for person in people:
            sentences.append(
                f"It shows {_name(person)} — {continuity['characters'][person]}. Keep "
                f"{_name(person)} recognisably the same person: the same face, build and "
                f"features.")
        if any(one.startswith("scene:") for one in ids):
            scene = part["scene"]
            sentences.append(
                f"It shows the place {_name(scene)} as it was last seen — "
                f"{continuity['scenes'][scene]}. This moment is in the same place: keep its layout, "
                f"materials and light, and show it from a new viewpoint.")
        else:
            sentences.append("Its setting is not where this moment happens: do not reuse it.")
        others = [one for one in other["characters"] if one not in part["characters"]]
        if others:
            names = ", ".join(_name(one) for one in others)
            sentences.append(f"It also shows {names}, who {'is' if len(others) == 1 else 'are'} "
                             f"not in this moment: do not draw them.")
        paragraphs.append(" ".join(sentences))
    if part["change"]:
        paragraphs.append(f"What has changed since those pictures: {part['change']}. Where this "
                          f"differs from a reference, follow this and not the reference.")
    return "\n\n".join(paragraphs)


def prompt_with_references(continuity: dict[str, Any], index: int,
                           plan: list[tuple[int, list[str]]], picture: str) -> str:
    return (PREAMBLE.replace("{references}", reference_lines(continuity, index, plan))
            .replace("{picture}", picture))


def describe_plan(continuity: dict[str, Any], index: int, plan: list[tuple[int, list[str]]]) -> str:
    part = continuity["parts"][index]
    head = f"part {index + 1} [{', '.join(part['characters']) or 'nobody'} @ {part['scene']}]"
    if not plan:
        return f"{head}: no references"
    served = "; ".join(
        f"part {earlier + 1} ({', '.join(one.removeprefix('scene:') for one in ids)})"
        for earlier, ids in plan)
    return f"{head} ← {served}" + (f"  — change: {part['change']}" if part["change"] else "")


# ── the calls ───────────────────────────────────────────────────────────────


def text_prompt(template: str, request: dict[str, Any]) -> str:
    return f"{template}\n\n{json.dumps(request, ensure_ascii=False, indent=2)}\n"


def ask_json(prompt: str, parse: Callable[[Any], Any], params: dict[str, Any],
             caller: str) -> tuple[Any, str]:
    """One JSON answer on the free Gemini chain, falling through a reply that does not parse."""
    catalogue = load_catalogue()
    candidates = chain.resolve("text", TEXT_CHAIN, catalogue)
    if not candidates:
        sys.exit("No text model: GEMINI_API_KEY is not set (it is read from .env).")

    def ask(candidate: chain.Candidate) -> call.TextResult:
        result = call.text(prompt, row=candidate.row, model=candidate.model, as_json=True,
                           params=params)
        try:
            parse(result.parsed)
        except (ValueError, TypeError, AttributeError, KeyError) as error:
            raise ProviderUnavailable("unusable", f"the reply did not hold its shape: {error}",
                                      provider_id=candidate.row.id, model=candidate.model) from None
        return result

    answered = chain.walk("text", [c.named for c in candidates], catalogue, ask, chain.stamped,
                          caller=caller)
    return parse(answered.parsed), answered.answer.model


def draw_with_references(prompt: str, references: list[bytes]) -> tuple[bytes, dict[str, Any]]:
    """One picture from one prompt and any number of reference images, through LiteLLM's chat path.

    `call.image` is text-only — LiteLLM's `image_generation` for Vertex Gemini takes no image — so
    this is the path an integration would use, and part of what the spike checks. A part with no
    references goes through it too, so every picture this run draws took the same road.
    """
    row = load_catalogue().find(IMAGE_PROVIDER)
    content: list[dict[str, Any]] = [
        {"type": "image_url",
         "image_url": {"url": f"data:{_mime(data)};base64,{base64.b64encode(data).decode()}"}}
        for data in references
    ]
    content.append({"type": "text", "text": prompt})
    request = {
        "model": IMAGE_MODEL,
        "messages": [{"role": "user", "content": content}],
        "modalities": ["image", "text"],
        "imageConfig": IMAGE_CONFIG,
        "timeout": row.timeout_for("image", IMAGE_TIMEOUT),
        "vertex_location": row.params_for("image").get("vertex_location", "global"),
        **call._transport(row),
    }
    started = time.monotonic()
    try:
        response = call.completion(**request)
    except Exception as error:  # noqa: BLE001
        call._raise(row, IMAGE_MODEL, error)
        raise
    seconds = time.monotonic() - started
    message = response.choices[0].message
    images = getattr(message, "images", None) or []
    if not images:
        said = (getattr(message, "content", None) or "").strip()[:300]
        raise ProviderRefused("refused", f"no image came back{': ' + said if said else ''}",
                              provider_id=row.id, model=IMAGE_MODEL)
    raw = base64.b64decode(images[0]["image_url"]["url"].split(",", 1)[1])
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


def _vertex_ready() -> None:
    problem = unmet(load_catalogue().find(IMAGE_PROVIDER))
    if problem:
        sys.exit(f"Vertex cannot be called from this machine: {problem}.")


# ── probe ───────────────────────────────────────────────────────────────────


def probe(_: argparse.Namespace) -> None:
    """One picture from a synthetic reference, to see the path work before an hour is spent on it."""
    _vertex_ready()
    sheet = Image.new("RGB", (1024, 1024), (236, 226, 204))
    pen = ImageDraw.Draw(sheet)
    pen.ellipse((380, 180, 640, 440), fill=(214, 170, 130))              # a head
    pen.rectangle((360, 440, 660, 860), fill=(46, 110, 70))              # a green jacket
    pen.ellipse((430, 270, 480, 320), outline=(20, 20, 20), width=8)     # round glasses
    pen.ellipse((540, 270, 590, 320), outline=(20, 20, 20), width=8)
    buffer = io.BytesIO()
    sheet.save(buffer, format="WEBP", quality=88)

    continuity = {
        "characters": {"marcos": "a man of about thirty in a green jacket and round glasses"},
        "scenes": {"studio": "a plain studio", "park": "a city park"},
        "parts": [{"characters": ["marcos"], "scene": "studio", "change": ""},
                  {"characters": ["marcos"], "scene": "park", "change": ""}],
    }
    picture = ("A man of about thirty in a green jacket and round glasses sits on a park bench "
               "feeding pigeons, seen from the side. Soft afternoon light. A single illustration, "
               "fully rendered. Absolutely no text anywhere in the image.")
    plan = plan_references(continuity, 1)
    try:
        raw, facts = draw_with_references(
            prompt_with_references(continuity, 1, plan, picture), [buffer.getvalue()])
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
        print(f"  {story['id']}  {story['createdAt'][:16]}  {len(story['parts'])} parts  "
              f"{story['styleId']:<22} {', '.join(models)}  {story['title']}")
    for label, why in skipped:
        print(f"  skipped: {label} — {why}")
    print(f"{len(kept)} stories kept. Next: `prepare`, which spends nothing on pictures.")


# ── prepare ─────────────────────────────────────────────────────────────────


def _stories() -> list[dict[str, Any]]:
    path = OUT / "stories.json"
    if not path.exists():
        sys.exit("No stories yet: run `fetch` first.")
    return json.loads(path.read_text(encoding="utf-8"))


def _v2_story(stories: list[dict[str, Any]], chosen: str | None) -> str:
    """The story that gets the v2 brief: the one named, else the one named last time, else newest."""
    remembered = OUT / "v2-story.txt"
    story_id = (chosen or (remembered.read_text().strip() if remembered.exists() else "")
                or (stories[-1]["id"] if stories else ""))
    if story_id and story_id not in {story["id"] for story in stories}:
        sys.exit(f"--v2-story {story_id} is not in stories.json")
    if story_id:
        remembered.write_text(story_id)
    return story_id


def _labels_path(story_id: str) -> Path:
    return OUT / "labels" / f"{story_id}.json"


def _brief_v2_path(story_id: str) -> Path:
    return OUT / "briefs-v2" / f"{story_id}.json"


def _prompts_dir(story_id: str) -> Path:
    return OUT / "prompts" / story_id


def continuity_for(story_id: str, set_name: str) -> dict[str, Any] | None:
    source = SETS[set_name]["labels"]
    if source is None:
        return None
    path = _labels_path(story_id) if source == "labels" else _brief_v2_path(story_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def briefs_for(story: dict[str, Any], set_name: str) -> list[str] | None:
    if SETS[set_name]["briefs"] == "stored":
        return [part["imagePrompt"] for part in story["parts"]]
    path = _brief_v2_path(story["id"])
    return json.loads(path.read_text(encoding="utf-8"))["briefs"] if path.exists() else None


def _sets_of(story_id: str, v2_story: str) -> list[str]:
    return ["continuity", "v2", "v2+continuity"] if story_id == v2_story else ["continuity"]


def image_prompt(story: dict[str, Any], set_name: str, index: int, style: Any
                 ) -> tuple[str, list[tuple[int, list[str]]]] | None:
    """What part `index` of this set would be drawn from, or None when it keeps its base picture."""
    continuity = continuity_for(story["id"], set_name)
    briefs = briefs_for(story, set_name)
    plan = plan_references(continuity, index) if continuity else []
    if not plan and SETS[set_name]["base"] is not None:
        return None
    picture = compose(briefs[index], style)
    return (prompt_with_references(continuity, index, plan, picture) if plan else picture), plan


def prepare(args: argparse.Namespace) -> None:
    stories = _stories()
    styles = load_styles()
    v2_story = _v2_story(stories, args.v2_story)
    to_draw = 0
    for story in stories:
        count = len(story["parts"])
        folder = _prompts_dir(story["id"])
        folder.mkdir(parents=True, exist_ok=True)
        print(f"\n{story['createdAt'][:10]}  {story['title']}  ({story['id']})")

        request = {"title": story["title"], "parts": [
            {"heading": part["heading"], "text": part["text"], "brief": part["imagePrompt"]}
            for part in story["parts"]]}
        prompt = text_prompt(LABEL_PROMPT, request)
        (folder / "labels-request.md").write_text(prompt, encoding="utf-8")
        path = _labels_path(story["id"])
        if args.force or not path.exists():
            try:
                labels, model = ask_json(prompt, lambda p: parse_continuity(p, count),
                                         LABEL_PARAMS, "spike.story-continuity")
            except ChainExhausted as exhausted:
                print(f"  labels failed: {exhausted.last}")
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({**labels, "model": model}, ensure_ascii=False, indent=2),
                            encoding="utf-8")

        if story["id"] == v2_story:
            request = {"title": story["title"],
                       "language": language_name(story["language"] or "es"),
                       "parts": [{"heading": part["heading"], "text": part["text"]}
                                 for part in story["parts"]]}
            prompt = text_prompt(BRIEF_V2_PROMPT, request)
            (folder / "brief-v2-request.md").write_text(prompt, encoding="utf-8")
            v2_path = _brief_v2_path(story["id"])
            if args.force or not v2_path.exists():
                try:
                    briefed, model = ask_json(prompt, lambda p: parse_brief_v2(p, count),
                                              dict(BRIEF_PARAMS), "spike.story-brief-v2")
                    v2_path.parent.mkdir(parents=True, exist_ok=True)
                    v2_path.write_text(json.dumps({**briefed, "model": model}, ensure_ascii=False,
                                                  indent=2), encoding="utf-8")
                except ChainExhausted as exhausted:
                    print(f"  v2 brief failed: {exhausted.last}")

        style = styles[story["styleId"]] if story["styleId"] in styles else None
        for set_name in _sets_of(story["id"], v2_story):
            continuity = continuity_for(story["id"], set_name)
            if (SETS[set_name]["labels"] and continuity is None) \
                    or briefs_for(story, set_name) is None:
                print(f"  [{set_name}] not ready: its text call failed")
                continue
            print(f"  [{set_name}]")
            for index in range(count):
                if continuity:
                    line = describe_plan(continuity, index, plan_references(continuity, index))
                else:
                    line = f"part {index + 1}: drawn from the v2 brief, no references"
                drawn = image_prompt(story, set_name, index, style) if style else None
                if drawn is None:
                    line += f" → keeps the {SETS[set_name]['base']} picture"
                else:
                    (folder / f"{set_name}-part-{index + 1}.md").write_text(
                        drawn[0] + "\n", encoding="utf-8")
                    to_draw += not _picture(story["id"], set_name, index).exists()
                print(f"    {line}")
        if style is None:
            print(f"  style {story['styleId']!r} is not in this checkout, so `draw` will skip it")
    print(f"\nEvery prompt is in {OUT / 'prompts'}/<story id>/.")
    print(f"`draw` will make {to_draw} pictures, about ${to_draw * PICTURE_USD:.2f}"
          f" (v2 story: {v2_story or 'none'})")


# ── draw ────────────────────────────────────────────────────────────────────


def _picture(story_id: str, set_name: str, index: int) -> Path:
    return OUT / story_id / set_name / f"part-{index + 1}.webp"


def _log(entry: dict[str, Any]) -> None:
    with (OUT / "draws.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _draw_one(prompt: str, references: list[bytes],
              entry: dict[str, Any]) -> tuple[bytes, dict[str, Any]] | None:
    """Draw, resting on a busy provider. None when the provider refused this picture."""
    rest = FIRST_REST
    while True:
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
            if refused.reason in ("authentication", "configuration"):
                sys.exit(f"{refused} — a setup problem, not this picture. Fix it and rerun.")
            print(f"  refused: {refused}")
            return None
        _log({**entry, **facts})
        return raw, facts


def draw(args: argparse.Namespace) -> None:
    _vertex_ready()
    stories = _stories()
    styles = load_styles()
    v2_story = _v2_story(stories, None)
    spent, drawn_now = 0.0, 0

    for story in stories:
        if story["styleId"] not in styles:
            print(f"skip {story['title']}: style {story['styleId']!r} is not in this checkout")
            continue
        style = styles[story["styleId"]]
        for set_name in _sets_of(story["id"], v2_story):
            if (SETS[set_name]["labels"] and continuity_for(story["id"], set_name) is None) \
                    or briefs_for(story, set_name) is None:
                print(f"skip {story['title']} [{set_name}]: run `prepare` first")
                continue
            base = SETS[set_name]["base"]
            for index in range(len(story["parts"])):
                target = _picture(story["id"], set_name, index)
                if target.exists():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                drawn = image_prompt(story, set_name, index, style)
                if drawn is None:
                    source = _picture(story["id"], base, index)
                    if not source.exists():
                        print(f"skip {story['title']} [{set_name}]: {base} part {index + 1} missing")
                        break
                    shutil.copyfile(source, target)
                    continue
                if args.limit is not None and drawn_now >= args.limit:
                    print(f"stopped at --limit {args.limit}; ${spent:.2f} spent this run")
                    return
                prompt, plan = drawn
                references = [_picture(story["id"], set_name, earlier).read_bytes()
                              for earlier, _ids in plan]
                entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "story": story["id"],
                         "set": set_name, "part": index + 1,
                         "references": [earlier + 1 for earlier, _ids in plan]}
                result = _draw_one(prompt, references, entry)
                if result is None:
                    break  # later parts may chain from this one, so the set stops here
                raw, facts = result
                target.write_bytes(encode_master(raw))
                spent += facts["costUsd"] or 0.0
                drawn_now += 1
                print(f"  {story['createdAt'][:10]} {story['title'][:38]:<38} [{set_name}] "
                      f"part {index + 1} ← {[e + 1 for e, _ in plan] or 'none'}  "
                      f"{facts['seconds']:.0f} s  ${facts['costUsd'] or 0:.4f}  (run ${spent:.2f})")
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
        continuity = continuity_for(story_id, "continuity")
        redrawn = sum(1 for index in range(len(stories[story_id]["parts"]))
                      if continuity and plan_references(continuity, index))
        group = "recent" if story_id in recent else "older"
        choice = rating.get("best") or ""
        if choice:
            rated += 1
            best[group][labels.get(choice, "no difference")] += 1
        for label, marks in (rating.get("flags") or {}).items():
            for mark, on in marks.items():
                if on:
                    flags[labels[label]][mark] += 1
        print(f"{stories[story_id]['createdAt'][:10]}  {stories[story_id]['title'][:40]:<40} "
              f"{redrawn} redrawn  best: {labels.get(choice, choice or '—'):<14}"
              f"{'  note: ' + rating['note'] if rating.get('note') else ''}")

    print(f"\n{rated} stories with a preference")
    for group in ("recent", "older"):
        print(f"  {group:<7} " + ", ".join(f"{arm} {count}" for arm, count in best[group].most_common()))
    print("flags (sets marked):")
    for arm, marks in sorted(flags.items()):
        print(f"  {arm:<14} " + ", ".join(f"{mark} {count}" for mark, count in marks.items()))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("probe", help="one picture from a synthetic reference (~$0.03)")
    fetching = commands.add_parser("fetch", help="copy the stories and their pictures down")
    fetching.add_argument("--server-url", required=True)
    fetching.add_argument("--email", required=True)
    preparing = commands.add_parser(
        "prepare", help="label who and where each picture shows; print the plan; write the prompts")
    preparing.add_argument("--v2-story", help="story id for the v2 brief (default: the newest)")
    preparing.add_argument("--force", action="store_true", help="ask the text model again")
    drawing = commands.add_parser("draw", help="draw the sets; safe to stop and rerun")
    drawing.add_argument("--limit", type=int, help="stop after this many pictures")
    commands.add_parser("report", help="unblind the labels")
    args = parser.parse_args(argv)
    {"probe": probe, "fetch": fetch, "prepare": prepare, "draw": draw,
     "report": report}[args.command](args)


if __name__ == "__main__":
    main()
