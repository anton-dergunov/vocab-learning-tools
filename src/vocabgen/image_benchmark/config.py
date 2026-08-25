from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml


class BenchmarkConfigError(ValueError):
    """Raised when an image benchmark configuration is invalid."""


@dataclass(frozen=True)
class PromptConfig:
    id: str
    term: str
    gloss: str
    brief: str
    stages: tuple[str, ...]
    scene: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StyleConfig:
    id: str
    suffix: str


@dataclass(frozen=True)
class StageConfig:
    id: str
    prompt_stage: str
    styles: tuple[str, ...]
    seeds: tuple[int, ...]


@dataclass(frozen=True)
class CandidateConfig:
    id: str
    label: str
    provider: str
    model: str
    command: tuple[str, ...]
    output_extension: str
    revision: str | None = None
    remote: bool = False
    enabled: bool = True
    estimated_cost_usd: float = 0.0
    prepare_command: tuple[str, ...] | None = None
    settings: Mapping[str, Any] = field(default_factory=dict)
    notes: str = ""


@dataclass(frozen=True)
class BenchmarkConfig:
    source_path: Path
    output_dir: Path
    normalized_width: int
    normalized_height: int
    normalized_format: str
    normalized_quality: int
    prompts: Mapping[str, PromptConfig]
    styles: Mapping[str, StyleConfig]
    stages: Mapping[str, StageConfig]
    candidates: Mapping[str, CandidateConfig]
    review_blind_salt: str


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BenchmarkConfigError(f"{context} must be a mapping")
    return value


def _strings(value: Any, context: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise BenchmarkConfigError(f"{context} must be a list of strings")
    return tuple(value)


def _command(value: Any, context: str) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(shlex.split(value))
    return _strings(value, context)


def _positive_int(value: Any, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise BenchmarkConfigError(f"{context} must be a positive integer")
    return value


def _expand_path(value: str, *, config_path: Path, repo_root: Path) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(value))
    path = Path(expanded)
    if path.is_absolute():
        return path
    # Repository configs use repository-relative paths. A config elsewhere is
    # resolved beside itself so copied experiments remain self-contained.
    if config_path.parent.name == "config":
        return repo_root / path
    return config_path.parent / path


def load_benchmark_config(path: str | Path, *, repo_root: str | Path) -> BenchmarkConfig:
    config_path = Path(path).expanduser().resolve()
    root = Path(repo_root).resolve()
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    data = _mapping(raw, "configuration root")

    output = _mapping(data.get("output"), "output")
    normalized = _mapping(output.get("normalized"), "output.normalized")
    width = _positive_int(normalized.get("width"), "output.normalized.width")
    height = _positive_int(normalized.get("height"), "output.normalized.height")
    quality = _positive_int(normalized.get("quality", 88), "output.normalized.quality")
    if quality > 100:
        raise BenchmarkConfigError("output.normalized.quality must be at most 100")
    image_format = str(normalized.get("format", "webp")).lower()
    if image_format not in {"webp", "png", "jpeg"}:
        raise BenchmarkConfigError("output.normalized.format must be webp, png, or jpeg")

    prompts: dict[str, PromptConfig] = {}
    for item in data.get("prompts", []):
        prompt = _mapping(item, "prompt")
        prompt_id = str(prompt.get("id", "")).strip()
        if not prompt_id or prompt_id in prompts:
            raise BenchmarkConfigError(f"Prompt id is missing or duplicated: {prompt_id!r}")
        prompts[prompt_id] = PromptConfig(
            id=prompt_id,
            term=str(prompt.get("term", "")).strip(),
            gloss=str(prompt.get("gloss", "")).strip(),
            brief=str(prompt.get("brief", "")).strip(),
            stages=_strings(prompt.get("stages", []), f"prompt {prompt_id}.stages"),
            scene=_mapping(prompt.get("scene", {}), f"prompt {prompt_id}.scene"),
        )
        if not prompts[prompt_id].term or not prompts[prompt_id].brief:
            raise BenchmarkConfigError(f"Prompt {prompt_id!r} needs term and brief")

    styles: dict[str, StyleConfig] = {}
    for style_id, style_raw in _mapping(data.get("styles"), "styles").items():
        style = _mapping(style_raw, f"style {style_id}")
        styles[str(style_id)] = StyleConfig(
            id=str(style_id), suffix=str(style.get("suffix", "")).strip()
        )

    stages: dict[str, StageConfig] = {}
    for stage_id, stage_raw in _mapping(data.get("stages"), "stages").items():
        stage = _mapping(stage_raw, f"stage {stage_id}")
        style_ids = _strings(stage.get("styles"), f"stage {stage_id}.styles")
        missing_styles = set(style_ids) - set(styles)
        if missing_styles:
            raise BenchmarkConfigError(
                f"Stage {stage_id!r} references unknown styles: {sorted(missing_styles)}"
            )
        seeds_raw = stage.get("seeds")
        if not isinstance(seeds_raw, list) or not seeds_raw or not all(
            isinstance(seed, int) and not isinstance(seed, bool) for seed in seeds_raw
        ):
            raise BenchmarkConfigError(f"stage {stage_id}.seeds must be integers")
        stages[str(stage_id)] = StageConfig(
            id=str(stage_id),
            prompt_stage=str(stage.get("prompt_stage", stage_id)),
            styles=style_ids,
            seeds=tuple(seeds_raw),
        )

    candidates: dict[str, CandidateConfig] = {}
    for candidate_id, candidate_raw in _mapping(data.get("candidates"), "candidates").items():
        candidate = _mapping(candidate_raw, f"candidate {candidate_id}")
        candidate_id = str(candidate_id)
        command = _command(candidate.get("command"), f"candidate {candidate_id}.command")
        prepare_raw = candidate.get("prepare_command")
        prepare = (
            _command(prepare_raw, f"candidate {candidate_id}.prepare_command")
            if prepare_raw
            else None
        )
        extension = str(candidate.get("output_extension", "png")).lower().lstrip(".")
        if extension not in {"png", "jpg", "jpeg", "webp", "svg"}:
            raise BenchmarkConfigError(
                f"Candidate {candidate_id!r} has unsupported output extension {extension!r}"
            )
        candidates[candidate_id] = CandidateConfig(
            id=candidate_id,
            label=str(candidate.get("label", candidate_id)),
            provider=str(candidate.get("provider", "unknown")),
            model=str(candidate.get("model", "unknown")),
            command=command,
            prepare_command=prepare,
            output_extension=extension,
            revision=(
                str(candidate["revision"])
                if candidate.get("revision") is not None
                else None
            ),
            remote=bool(candidate.get("remote", False)),
            enabled=bool(candidate.get("enabled", True)),
            estimated_cost_usd=float(candidate.get("estimated_cost_usd", 0.0)),
            settings=_mapping(candidate.get("settings", {}), f"candidate {candidate_id}.settings"),
            notes=str(candidate.get("notes", "")),
        )

    if not prompts or not styles or not stages or not candidates:
        raise BenchmarkConfigError("prompts, styles, stages, and candidates cannot be empty")

    review = _mapping(data.get("review", {}), "review")
    return BenchmarkConfig(
        source_path=config_path,
        output_dir=_expand_path(str(output.get("directory", "output/image-benchmark")), config_path=config_path, repo_root=root),
        normalized_width=width,
        normalized_height=height,
        normalized_format=image_format,
        normalized_quality=quality,
        prompts=prompts,
        styles=styles,
        stages=stages,
        candidates=candidates,
        review_blind_salt=str(review.get("blind_salt", "vocabgen-image-benchmark-v1")),
    )
