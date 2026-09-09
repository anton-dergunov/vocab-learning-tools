#!/usr/bin/env python3
"""Draw one picture for each sense of each word, on this laptop.

Phase A of `docs/acervo-sense-images.md`. It reads the vocabulary graph from the server and writes
nothing back: the output is a local directory of JSON records and WebP masters that a later import
turns into `imagePrompt` rows. That separation is deliberate — the point of this phase is to iterate
on the prompt and spend the Vertex credits while they exist, not to change the database.

Resumable by looking at the filesystem. A sense whose picture is already there is skipped; delete
the picture and the next run writes a fresh brief and draws it again with a new seed. The graph is
re-read every run, so words ingested since last time are picked up with no extra step.

    # who is about to be billed
    scripts/generate_images.py check

    # what would be drawn
    scripts/generate_images.py plan --language es \
        --server-url https://acervo.example.com --owner-email learner@account.example.com

    # draw the first ten
    scripts/generate_images.py run --language es --limit 10 \
        --server-url https://acervo.example.com --owner-email learner@account.example.com

    # look at them
    scripts/generate_images.py sheet && open output/images/sheet.html
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
import webbrowser
from pathlib import Path

from acervo.jobs.images import preflight
from acervo.jobs.images.brief import BriefWriter
from acervo.jobs.images.compose import prompt_version
from acervo.client import AcervoClient, AcervoError
from acervo.jobs.images.graph import build_articles
from acervo.jobs.images.publish import BATCH, publish
from acervo.jobs.images.render import Renderer
from acervo.jobs.images.run import Runner, Store, plan
from acervo.jobs.images.sheet import write_sheet
from acervo.jobs.images.styles import load_styles
from acervo.jobs.images.verify import verify

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "output" / "images"
DEFAULT_STYLES = REPO_ROOT / "config" / "image-styles.yaml"
DEFAULT_TEMPLATE = REPO_ROOT / "prompts" / "acervo_image_brief.txt"
# The brief writer now reasons in two steps — commit to a concrete situation, then draw it — so it
# gets the strongest Flash this project can reach rather than the Lite the capture hook uses. Text
# calls are cheap and generously quota'd next to the images; the reasoning is what limits quality.
# `gemini-3.1-flash` is NOT available here — check `models.list()` before changing this.
BRIEF_MODEL = "gemini-3.8-flash"
# Flash Lite alone by default: the cheapest of the three at roughly half the price of Flash, and
# within a point of it in the finalist benchmark. Each image model has its own quota bucket, so
# passing several to `--image-models` multiplies the rate — about one image per minute per model —
# but it multiplies the bill too, and the budget is the binding constraint rather than the clock.
IMAGE_MODELS = ("gemini-3.1-flash-lite-image",)
IMAGE_COST_USD = {
    "gemini-3.1-flash-lite-image": 0.0336,
    "gemini-3.1-flash-image": 0.067,
    "gemini-3-pro-image": 0.134,
}


def confirm_account(assume_yes: bool) -> preflight.Identity:
    identity = preflight.resolve()
    print(f"Google account  {identity.account}")
    print(f"Project         {identity.project}")
    print(f"Configuration   {identity.configuration}")
    if assume_yes:
        return identity
    answer = input("Bill this account? [y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        raise SystemExit("Stopped without spending anything.")
    return identity


def load_graph(args: argparse.Namespace):
    password = os.environ.get("ACERVO_PASSWORD") or getpass.getpass("Acervo password: ")
    with AcervoClient(args.server_url) as client:
        client.sign_in(args.owner_email, password)
        # One pull, and nothing else: this stage reads the graph and writes only to the filesystem.
        return build_articles(client.pull_graph()["changes"], args.language)


def make_client(project: str, location: str):
    from google import genai
    from google.genai import types
    return genai.Client(
        vertexai=True,
        project=project,
        location=location,
        http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(
            attempts=4, initial_delay=10.0, max_delay=60.0, exp_base=2.0, jitter=1.0,
            http_status_codes=[408, 429, 500, 502, 503, 504],
        )),
    )


def command_check(args: argparse.Namespace) -> int:
    confirm_account(assume_yes=True)
    styles = load_styles(args.styles)
    print(f"Styles          {len(styles.styles)} ({styles.digest})")
    print(f"Prompt version  {prompt_version(args.template, styles.digest)}")
    print(f"Brief model     {BRIEF_MODEL}")
    for model in IMAGE_MODELS:
        print(f"Image model     {model}  (~${IMAGE_COST_USD.get(model, 0):.4f}/image)")
    return 0


def command_plan(args: argparse.Namespace) -> int:
    articles = load_graph(args)
    store = Store(args.output)
    jobs = plan(articles, store, redo=args.redo, only=args.only.split(','))
    senses = sum(len(article.senses) for article in articles)
    print(f"{len(articles)} words, {senses} senses in scope"
          + (f" (language {args.language})" if args.language else ""))
    print(f"{len(jobs)} senses have no picture yet")
    for job in jobs[: args.limit or 20]:
        anchor = job.sense.anchor
        line = anchor.get("text") if anchor else job.sense.definition
        print(f"  {job.article.headword:<28} {(line or '')[:70]}")
    if args.limit and len(jobs) > args.limit:
        print(f"  … and {len(jobs) - args.limit} more")
    return 0


def command_run(args: argparse.Namespace) -> int:
    identity = confirm_account(args.yes)
    project = args.project or identity.project
    if not project:
        raise SystemExit("No Google Cloud project is configured.")

    articles = load_graph(args)
    store = Store(args.output)
    jobs = plan(articles, store, redo=args.redo, only=args.only.split(','))
    if args.limit:
        jobs = jobs[: args.limit]
    if not jobs:
        print("Every sense in scope already has a picture.")
        return 0

    styles = load_styles(args.styles)
    models = tuple(m.strip() for m in args.image_models.split(",") if m.strip())
    client = make_client(project, args.location)
    runner = Runner(
        store=store,
        writer=BriefWriter(client, args.brief_model, args.template, styles),
        renderer=Renderer(client, models),
        styles=styles,
        template_path=args.template,
        workers=args.workers,
        rate_limit=args.rate_limit,
        attempts=args.attempts,
    )
    print(f"Drawing {len(jobs)} senses · {args.workers} workers · "
          f"{len(models)} model(s) × {args.rate_limit or '∞'}/min → {store.root}")
    result = runner.run(jobs)
    print(f"\n{result['drawn']} drawn, {result['refused']} refused, {result['failed']} failed "
          f"in {result['seconds']}s ({result['throttled']} quota waits)")
    print(f"Image output tokens: {result['imageTokens']:,}")
    spend = sum(IMAGE_COST_USD.get(model, 0) for model in result["byModel"].elements()) \
        if hasattr(result["byModel"], "elements") else 0
    for model, count in sorted(result["byModel"].items()):
        print(f"  {count:>4} × {model}  ≈ ${count * IMAGE_COST_USD.get(model, 0):.2f}")
    print(f"Estimated spend this run: ${spend:.2f}")

    sheet = write_sheet(store)
    print(f"Contact sheet: {sheet}")
    if args.open:
        webbrowser.open(sheet.as_uri())
    return 0


def command_verify(args: argparse.Namespace) -> int:
    store = Store(args.output)
    report = verify(store)
    print(f"{report.images} images · {report.records} records · {report.drawn} drawn · "
          f"{report.refused} refused by the writer · {report.blocked} blocked by the provider")
    for kind, subjects in sorted(report.problems.items()):
        print(f"  [FAIL] {kind}: {len(subjects)} -> {', '.join(subjects[:5])}")
    print("safe to import" if report.ok else "NOT safe to import")
    return 0 if report.ok else 1


def command_sheet(args: argparse.Namespace) -> int:
    sheet = write_sheet(Store(args.output), args.to, args.limit)
    print(sheet)
    if args.open:
        webbrowser.open(sheet.as_uri())
    return 0


def command_publish(args: argparse.Namespace) -> int:
    """Write the rows and copy the images. Verified first, and all-or-nothing about the checks."""
    password = os.environ.get("ACERVO_PASSWORD") or getpass.getpass("Acervo password: ")
    store = Store(args.output)
    with AcervoClient(args.server_url) as client:
        client.sign_in(args.owner_email, password)
        outcome = publish(
            store, client, media=args.media, device_id=args.device_id, batch=args.batch
        )
    if not outcome.ok:
        return 1
    print(
        f"Published {outcome.written} image prompts and {outcome.copied} files; "
        f"{outcome.held} already held, {outcome.undrawn} have no picture."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--styles", type=Path, default=DEFAULT_STYLES)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    sub = parser.add_subparsers(dest="command", required=True)

    def graph_arguments(target: argparse.ArgumentParser) -> None:
        target.add_argument("--server-url", default=os.environ.get("ACERVO_SERVER_URL", ""))
        target.add_argument("--owner-email", default=os.environ.get("ACERVO_OWNER_EMAIL", ""))
        target.add_argument("--language", default="es",
                            help="Only this vocabulary language. Empty string for all.")
        target.add_argument("--limit", type=int, default=0)
        target.add_argument("--redo", action="store_true",
                            help="Include senses that already have a picture.")
        target.add_argument("--only", default="",
                            help="Comma-separated headwords, sense ids or image ids to restrict to.")

    sub.add_parser("check", help="Say which Google account and prompt version a run would use")

    planner = sub.add_parser("plan", help="List the senses that have no picture yet")
    graph_arguments(planner)

    runner = sub.add_parser("run", help="Write briefs and draw pictures")
    graph_arguments(runner)
    runner.add_argument("--workers", type=int, default=3)
    runner.add_argument("--rate-limit", type=int, default=1,
                        help="Image calls per minute PER MODEL. Measured ceiling is 1. 0 removes it.")
    runner.add_argument("--brief-model", default=BRIEF_MODEL)
    runner.add_argument("--image-models", default=",".join(IMAGE_MODELS),
                        help="Comma-separated image models. Each has its own quota bucket.")
    runner.add_argument("--attempts", type=int, default=12,
                        help="Tries per sense when the project is over quota.")
    runner.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT", ""))
    runner.add_argument("--location", default=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"))
    runner.add_argument("--yes", action="store_true", help="Skip the billing confirmation")
    runner.add_argument("--open", action="store_true", help="Open the contact sheet when finished")

    sub.add_parser("verify", help="Check the run directory is internally consistent before import")

    publisher = sub.add_parser("publish", help="Write a verified run into the graph and the media directory")
    publisher.add_argument("--server-url", default=os.environ.get("ACERVO_SERVER_URL", ""))
    publisher.add_argument("--owner-email", default=os.environ.get("ACERVO_OWNER_EMAIL", ""))
    publisher.add_argument("--media", type=Path, required=True,
                           help="The media directory the server serves; images are fanned out under it.")
    publisher.add_argument("--device-id", default="imagepublish01")
    publisher.add_argument("--batch", type=int, default=BATCH,
                           help="Records per write. One stale record refuses a whole batch.")

    sheet = sub.add_parser("sheet", help="Rebuild the contact sheet from what is on disk")
    sheet.add_argument("--limit", type=int, default=0, help="Show only the newest N images.")
    sheet.add_argument("--to", type=Path, default=None, help="Write somewhere other than sheet.html.")
    sheet.add_argument("--open", action="store_true")

    args = parser.parse_args()
    handlers = {"check": command_check, "plan": command_plan, "run": command_run,
                "publish": command_publish, "sheet": command_sheet, "verify": command_verify}
    try:
        return handlers[args.command](args)
    except AcervoError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
