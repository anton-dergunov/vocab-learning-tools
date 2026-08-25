#!/usr/bin/env python3
"""Run and review isolated image-generation benchmarks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parent.parent.resolve()
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from vocabgen.image_benchmark.config import BenchmarkConfigError, load_benchmark_config
from vocabgen.image_benchmark.harness import prepare_candidates, run_benchmark
from vocabgen.image_benchmark.jobs import expand_jobs
from vocabgen.image_benchmark.review import render_review


DEFAULT_CONFIG = _REPO_ROOT / "config" / "image-benchmark.yaml"


def _config(args: argparse.Namespace):
    return load_benchmark_config(args.config, repo_root=_REPO_ROOT)


def list_command(args: argparse.Namespace) -> int:
    config = _config(args)
    print("Candidates")
    for candidate in config.candidates.values():
        flags = ["remote" if candidate.remote else "local"]
        if not candidate.enabled:
            flags.append("disabled")
        print(
            f"  {candidate.id:24} {candidate.provider:14} "
            f"${candidate.estimated_cost_usd:.6f}/image  {', '.join(flags)}"
        )
        print(f"    {candidate.label} — {candidate.model}")
        if candidate.notes:
            print(f"    {candidate.notes}")
    print("\nStages")
    for stage in config.stages:
        jobs = expand_jobs(config, stage)
        print(f"  {stage:12} {len(jobs)} jobs with enabled candidates")
    print(f"\nOutput: {config.output_dir}")
    return 0


def prepare_command(args: argparse.Namespace) -> int:
    config = _config(args)
    return prepare_candidates(
        config,
        repo_root=_REPO_ROOT,
        candidate_ids=args.models,
    )


def _run(args: argparse.Namespace, *, resume: bool) -> int:
    config = _config(args)
    summary = run_benchmark(
        config,
        repo_root=_REPO_ROOT,
        stage=args.stage,
        candidate_ids=args.models,
        execute_remote=args.execute_remote,
        max_cost_usd=args.max_cost_usd,
        resume=resume,
    )
    print(
        f"Completed {summary.total} jobs: {summary.succeeded} succeeded, "
        f"{summary.failed} failed, {summary.skipped} skipped; "
        f"projected remote cost ${summary.projected_cost_usd:.4f}"
    )
    return 1 if summary.failed else 0


def run_command(args: argparse.Namespace) -> int:
    return _run(args, resume=False)


def resume_command(args: argparse.Namespace) -> int:
    return _run(args, resume=True)


def review_command(args: argparse.Namespace) -> int:
    config = _config(args)
    output = args.output or config.output_dir / args.stage / "review.html"
    result = render_review(config, args.stage, output)
    print(f"Review gallery written to {result}")
    return 0


def _add_run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--stage", choices=("smoke", "finalist"), required=True)
    parser.add_argument(
        "--models",
        nargs="+",
        help="Candidate ids; defaults to enabled candidates",
    )
    parser.add_argument(
        "--execute-remote",
        action="store_true",
        help="Authorize configured remote candidates for this invocation",
    )
    parser.add_argument(
        "--max-cost-usd",
        type=float,
        help="Required upper bound when any remote candidate is selected",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    commands = parser.add_subparsers(dest="command", required=True)

    listing = commands.add_parser("list", help="List configured candidates and stages")
    listing.set_defaults(handler=list_command)

    prepare = commands.add_parser(
        "prepare", help="Explicitly download assets for selected local candidates"
    )
    prepare.add_argument("--models", nargs="+", required=True)
    prepare.set_defaults(handler=prepare_command)

    run = commands.add_parser("run", help="Run jobs even if matching output exists")
    _add_run_options(run)
    run.set_defaults(handler=run_command)

    resume = commands.add_parser("resume", help="Skip completed jobs and retry the rest")
    _add_run_options(resume)
    resume.set_defaults(handler=resume_command)

    review = commands.add_parser("render-review", help="Build a self-contained blind review gallery")
    review.add_argument("--stage", choices=("smoke", "finalist"), required=True)
    review.add_argument("--output", type=Path)
    review.set_defaults(handler=review_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (BenchmarkConfigError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
