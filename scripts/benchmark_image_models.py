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
from vocabgen.image_benchmark.ratings import RatingsError, write_ratings_report
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
    for stage_id, stage in config.stages.items():
        jobs = expand_jobs(config, stage_id)
        selection = (
            f"{len(stage.candidates)} configured candidates"
            if stage.candidates
            else "enabled candidates"
        )
        print(f"  {stage_id:18} {len(jobs)} jobs with {selection}")
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


def aggregate_ratings_command(args: argparse.Namespace) -> int:
    config = _config(args)
    default_name = f"{args.ratings[0].stem}-aggregate.html"
    output = args.output or config.output_dir / "ratings" / default_name
    report, html_path, json_path = write_ratings_report(
        args.ratings,
        html_path=output,
        json_path=args.json_output,
        candidate_metadata={
            candidate_id: {
                "label": candidate.label,
                "provider": candidate.provider,
                "model": candidate.model,
                "remote": candidate.remote,
                "estimated_cost_usd": candidate.estimated_cost_usd,
            }
            for candidate_id, candidate in config.candidates.items()
        },
        benchmark_output_dir=config.output_dir,
    )

    def score(value):
        return f"{value:.2f}" if value is not None else "—"

    def duration(value):
        return f"{value:.1f}s" if value is not None else "—"

    def memory(value):
        return f"{value / 2**30:.2f}G" if value is not None else "—"

    print("Rejected-as-zero ranking")
    print("Rank  Usable  Rejects  Runtime  RSS/process  Cost/image  Coverage  Model")
    for candidate in report["candidates"]:
        resources = candidate["resources"]
        rss = "hosted" if candidate["remote"] else memory(
            resources["mean_peak_process_rss_bytes"]
        )
        cost = f"${candidate['estimated_cost_usd']:.6f}"
        print(
            f"{candidate['rank']:>4}  {score(candidate['usable_score']):>6}  "
            f"{candidate['rejected']:>3}/{candidate['items']:<3}  "
            f"{duration(resources['mean_duration_seconds']):>7}  {rss:>11}  "
            f"{cost:>10}  "
            f"{candidate['coverage']:>3}/{candidate['expected_coverage']:<3}  "
            f"{candidate['candidate_id']}"
        )
    print("\nAccepted-only ranking (rejected outputs excluded from averages)")
    print("Rank  Score   Accepted  Rejects  Model")
    accepted_candidates = sorted(
        report["candidates"], key=lambda item: item["accepted_rank"]
    )
    for candidate in accepted_candidates:
        print(
            f"{candidate['accepted_rank']:>4}  "
            f"{score(candidate['accepted_quality_score']):>6}  "
            f"{candidate['accepted_items']:>3}/{candidate['items']:<3}     "
            f"{candidate['rejected']:>3}/{candidate['items']:<3}  "
            f"{candidate['candidate_id']}"
        )
    print(f"HTML report written to {html_path}")
    print(f"Aggregate JSON written to {json_path}")
    return 0


def _add_run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--stage", required=True, help="Stage id from the benchmark YAML")
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
    review.add_argument("--stage", required=True, help="Stage id from the benchmark YAML")
    review.add_argument("--output", type=Path)
    review.set_defaults(handler=review_command)

    aggregate = commands.add_parser(
        "aggregate-ratings",
        help="Aggregate exported ratings into interactive HTML and JSON reports",
    )
    aggregate.add_argument("ratings", nargs="+", type=Path)
    aggregate.add_argument("--output", type=Path, help="HTML report destination")
    aggregate.add_argument(
        "--json-output", type=Path, help="Aggregate JSON destination"
    )
    aggregate.set_defaults(handler=aggregate_ratings_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (BenchmarkConfigError, RatingsError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
