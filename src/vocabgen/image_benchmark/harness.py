from __future__ import annotations

import json
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .config import BenchmarkConfig, CandidateConfig
from .jobs import BenchmarkJob, expand_jobs, select_candidates
from .media import normalize_image


@dataclass(frozen=True)
class RunSummary:
    total: int
    succeeded: int
    failed: int
    skipped: int
    projected_cost_usd: float
    manifests: tuple[Path, ...]


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def projected_cost(jobs: Iterable[BenchmarkJob], config: BenchmarkConfig) -> float:
    return sum(config.candidates[job.candidate_id].estimated_cost_usd for job in jobs)


def validate_remote_authorization(
    jobs: Iterable[BenchmarkJob],
    config: BenchmarkConfig,
    *,
    execute_remote: bool,
    max_cost_usd: float | None,
) -> float:
    jobs = tuple(jobs)
    remote_jobs = [job for job in jobs if config.candidates[job.candidate_id].remote]
    cost = projected_cost(remote_jobs, config)
    if not remote_jobs:
        return 0.0
    if not execute_remote:
        names = sorted({job.candidate_id for job in remote_jobs})
        raise ValueError(
            "Remote candidates require --execute-remote: " + ", ".join(names)
        )
    if max_cost_usd is None:
        raise ValueError("Remote candidates require --max-cost-usd")
    if max_cost_usd < 0:
        raise ValueError("--max-cost-usd cannot be negative")
    if cost > max_cost_usd + 1e-12:
        raise ValueError(
            f"Projected remote cost ${cost:.4f} exceeds ceiling ${max_cost_usd:.4f}"
        )
    return cost


def _format_command(
    command: tuple[str, ...],
    *,
    repo_root: Path,
    request_path: Path | None = None,
    result_path: Path | None = None,
) -> list[str]:
    values = {
        "python": sys.executable,
        "repo_root": str(repo_root),
        "request": str(request_path or ""),
        "result": str(result_path or ""),
    }
    return [part.format(**values) for part in command]


def _parse_peak_rss(path: Path) -> int | None:
    if not path.is_file():
        return None
    match = re.search(
        r"(\d+)\s+maximum resident set size", path.read_text(encoding="utf-8")
    )
    return int(match.group(1)) if match else None


def _execute_command(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    metrics_path: Path,
) -> tuple[subprocess.CompletedProcess[str], float, int | None]:
    measured_command = command
    using_time = False
    if platform.system() == "Darwin" and Path("/usr/bin/time").is_file():
        measured_command = ["/usr/bin/time", "-l", "-o", str(metrics_path), *command]
        using_time = True
    started = time.perf_counter()
    completed = subprocess.run(
        measured_command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_seconds,
        check=False,
    )
    # Some sandboxed macOS environments deny the sysctl used by /usr/bin/time.
    # Resource measurement is optional; generation itself should still run.
    if using_time and completed.returncode and "sysctl kern.clockrate" in completed.stderr:
        metrics_path.unlink(missing_ok=True)
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    return completed, time.perf_counter() - started, _parse_peak_rss(metrics_path)


def _job_paths(config: BenchmarkConfig, job: BenchmarkJob) -> dict[str, Path]:
    candidate = config.candidates[job.candidate_id]
    directory = config.output_dir / job.stage / job.id
    normalized_extension = "jpg" if config.normalized_format == "jpeg" else config.normalized_format
    return {
        "directory": directory,
        "request": directory / "request.json",
        "runner_result": directory / "runner-result.json",
        "manifest": directory / "manifest.json",
        "native": directory / f"native.{candidate.output_extension}",
        "sanitized_svg": directory / "native.sanitized.svg",
        "svg_raster": directory / "native.sanitized.png",
        "normalized": directory / f"normalized.{normalized_extension}",
        "metrics": directory / "resource-usage.txt",
    }


def _request(
    config: BenchmarkConfig,
    candidate: CandidateConfig,
    job: BenchmarkJob,
    native_path: Path,
) -> dict[str, Any]:
    return {
        "contract_version": 1,
        "job": job.to_dict(),
        "candidate": {
            "id": candidate.id,
            "label": candidate.label,
            "provider": candidate.provider,
            "model": candidate.model,
            "revision": candidate.revision,
            "settings": dict(candidate.settings),
        },
        "output": {
            "native_path": str(native_path.resolve()),
            "normalized_width": config.normalized_width,
            "normalized_height": config.normalized_height,
        },
    }


def _existing_success(paths: Mapping[str, Path]) -> bool:
    try:
        manifest = read_json(paths["manifest"])
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return (
        manifest.get("status") == "success"
        and paths["native"].is_file()
        and paths["normalized"].is_file()
    )


def run_benchmark(
    config: BenchmarkConfig,
    *,
    repo_root: Path,
    stage: str,
    candidate_ids: Iterable[str] | None = None,
    execute_remote: bool = False,
    max_cost_usd: float | None = None,
    resume: bool = False,
) -> RunSummary:
    jobs = expand_jobs(config, stage, candidate_ids)
    cost = validate_remote_authorization(
        jobs,
        config,
        execute_remote=execute_remote,
        max_cost_usd=max_cost_usd,
    )
    succeeded = failed = skipped = 0
    manifests: list[Path] = []

    for index, job in enumerate(jobs, start=1):
        candidate = config.candidates[job.candidate_id]
        paths = _job_paths(config, job)
        paths["directory"].mkdir(parents=True, exist_ok=True)
        manifests.append(paths["manifest"])
        if resume and _existing_success(paths):
            skipped += 1
            print(f"[{index}/{len(jobs)}] skip {job.id}")
            continue

        for stale_key in (
            "native",
            "normalized",
            "sanitized_svg",
            "svg_raster",
            "metrics",
        ):
            paths[stale_key].unlink(missing_ok=True)
        request = _request(config, candidate, job, paths["native"])
        write_json(paths["request"], request)
        paths["runner_result"].unlink(missing_ok=True)
        command = _format_command(
            candidate.command,
            repo_root=repo_root,
            request_path=paths["request"],
            result_path=paths["runner_result"],
        )
        print(f"[{index}/{len(jobs)}] run {job.id}")
        started_at = time.time()
        try:
            completed, duration, peak_rss = _execute_command(
                command,
                cwd=repo_root,
                timeout_seconds=float(candidate.settings.get("timeout_seconds", 3600)),
                metrics_path=paths["metrics"],
            )
            runner_result = (
                read_json(paths["runner_result"])
                if paths["runner_result"].is_file()
                else {}
            )
            if completed.returncode != 0:
                error = runner_result.get("error") or completed.stderr.strip() or completed.stdout.strip()
                raise RuntimeError(error or f"Runner exited {completed.returncode}")
            if runner_result.get("status") != "success":
                raise RuntimeError(str(runner_result.get("error", "Runner did not report success")))
            if not paths["native"].is_file():
                raise RuntimeError(f"Runner did not create {paths['native']}")

            normalize_image(
                paths["native"],
                paths["normalized"],
                width=config.normalized_width,
                height=config.normalized_height,
                image_format=config.normalized_format,
                quality=config.normalized_quality,
                sanitized_svg_path=paths["sanitized_svg"],
            )
            native_bytes = paths["native"].stat().st_size
            normalized_bytes = paths["normalized"].stat().st_size
            manifest = {
                "contract_version": 1,
                "status": "success",
                "job": job.to_dict(),
                "candidate": request["candidate"],
                "command": command,
                "started_at_unix": started_at,
                "duration_seconds": duration,
                "peak_process_rss_bytes": peak_rss,
                "estimated_cost_usd": candidate.estimated_cost_usd,
                "native": {
                    "path": str(paths["native"]),
                    "bytes": native_bytes,
                    "generation_width": candidate.settings.get("width"),
                    "generation_height": candidate.settings.get("height"),
                },
                "normalized": {
                    "path": str(paths["normalized"]),
                    "bytes": normalized_bytes,
                    "width": config.normalized_width,
                    "height": config.normalized_height,
                    "format": config.normalized_format,
                },
                "runner": runner_result,
                "stdout": completed.stdout[-8000:],
                "stderr": completed.stderr[-8000:],
            }
            write_json(paths["manifest"], manifest)
            succeeded += 1
        except Exception as exc:  # One backend must not abort the benchmark matrix.
            manifest = {
                "contract_version": 1,
                "status": "error",
                "job": job.to_dict(),
                "candidate": request["candidate"],
                "command": command,
                "started_at_unix": started_at,
                "estimated_cost_usd": candidate.estimated_cost_usd,
                "error": f"{type(exc).__name__}: {exc}",
            }
            write_json(paths["manifest"], manifest)
            failed += 1
            print(f"  error: {manifest['error']}", file=sys.stderr)

    return RunSummary(
        total=len(jobs),
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        projected_cost_usd=cost,
        manifests=tuple(manifests),
    )


def prepare_candidates(
    config: BenchmarkConfig,
    *,
    repo_root: Path,
    candidate_ids: Iterable[str],
) -> int:
    requested_ids = tuple(candidate_ids)
    if not requested_ids:
        raise ValueError("prepare requires at least one explicit --model")
    candidates = select_candidates(config, requested_ids)
    failures = 0
    for candidate in candidates:
        if candidate.remote:
            print(f"skip {candidate.id}: remote candidate has nothing to prepare")
            continue
        prepare_command = candidate.prepare_command
        if not prepare_command and candidate.provider in {"diffusers", "transformers"}:
            prepare_command = (
                "uv",
                "run",
                "--no-project",
                "--python",
                "3.12",
                "--with",
                "huggingface-hub>=0.30,<2",
                "python",
                str(repo_root / "scripts" / "image_benchmark_runner.py"),
                "prepare",
                "--model-id",
                candidate.model,
            )
        if not prepare_command:
            print(f"skip {candidate.id}: no prepare command")
            continue
        command = _format_command(prepare_command, repo_root=repo_root)
        print(f"prepare {candidate.id}")
        completed = subprocess.run(command, cwd=repo_root, check=False)
        if completed.returncode:
            failures += 1
    return failures
