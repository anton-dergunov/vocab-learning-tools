from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Iterable, Mapping, Any

from .config import BenchmarkConfig, CandidateConfig, PromptConfig, StyleConfig


@dataclass(frozen=True)
class BenchmarkJob:
    id: str
    stage: str
    candidate_id: str
    prompt_id: str
    term: str
    gloss: str
    prompt: str
    style_id: str
    seed: int
    scene: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _job_id(
    *,
    stage: str,
    candidate: CandidateConfig,
    prompt: PromptConfig,
    style: StyleConfig,
    seed: int,
    rendered_prompt: str,
) -> str:
    identity = {
        "stage": stage,
        "candidate": candidate.id,
        "provider": candidate.provider,
        "model": candidate.model,
        "revision": candidate.revision,
        "settings": candidate.settings,
        "prompt": prompt.id,
        "brief": prompt.brief,
        "rendered_prompt": rendered_prompt,
        "style": style.id,
        "suffix": style.suffix,
        "seed": seed,
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]
    return f"{prompt.id}--{style.id}--s{seed}--{candidate.id}--{digest}"


def select_candidates(
    config: BenchmarkConfig,
    requested: Iterable[str] | None,
) -> tuple[CandidateConfig, ...]:
    requested_ids = tuple(requested or ())
    if requested_ids:
        missing = set(requested_ids) - set(config.candidates)
        if missing:
            raise ValueError(f"Unknown candidates: {', '.join(sorted(missing))}")
        return tuple(config.candidates[item] for item in requested_ids)
    return tuple(candidate for candidate in config.candidates.values() if candidate.enabled)


def expand_jobs(
    config: BenchmarkConfig,
    stage_id: str,
    candidate_ids: Iterable[str] | None = None,
) -> tuple[BenchmarkJob, ...]:
    if stage_id not in config.stages:
        raise ValueError(f"Unknown stage {stage_id!r}")
    stage = config.stages[stage_id]
    selected_ids = stage.candidates if candidate_ids is None and stage.candidates else candidate_ids
    candidates = select_candidates(config, selected_ids)
    prompts = tuple(
        prompt for prompt in config.prompts.values() if stage.prompt_stage in prompt.stages
    )
    if not prompts:
        raise ValueError(f"Stage {stage_id!r} selects no prompts")

    jobs: list[BenchmarkJob] = []
    for candidate in candidates:
        for prompt in prompts:
            for style_id in stage.styles:
                style = config.styles[style_id]
                full_prompt = f"{prompt.brief.rstrip('.')}. {style.suffix}".strip()
                for seed in stage.seeds:
                    jobs.append(
                        BenchmarkJob(
                            id=_job_id(
                                stage=stage_id,
                                candidate=candidate,
                                prompt=prompt,
                                style=style,
                                seed=seed,
                                rendered_prompt=full_prompt,
                            ),
                            stage=stage_id,
                            candidate_id=candidate.id,
                            prompt_id=prompt.id,
                            term=prompt.term,
                            gloss=prompt.gloss,
                            prompt=full_prompt,
                            style_id=style.id,
                            seed=seed,
                            scene=prompt.scene,
                        )
                    )
    return tuple(jobs)
