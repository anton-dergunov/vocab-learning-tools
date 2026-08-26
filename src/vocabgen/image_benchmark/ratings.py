from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable, Mapping


METRIC_LABELS: dict[str, str] = {
    "relevance": "Mnemonic relevance",
    "legibility": "Small-size legibility",
    "appeal": "Visual appeal",
    "artifacts": "Artifact freedom",
}

# The report controls remain editable. These defaults reflect the intended Anki
# use: meaning and memorability matter most, while 384px cards make tiny-size
# legibility a comparatively small concern.
DEFAULT_WEIGHTS: dict[str, float] = {
    "relevance": 45.0,
    "legibility": 5.0,
    "appeal": 30.0,
    "artifacts": 20.0,
}


class RatingsError(ValueError):
    """Raised when an exported image-benchmark rating file is invalid."""


def _mean(values: Iterable[float]) -> float | None:
    collected = list(values)
    return fmean(collected) if collected else None


def _evaluation_key(item: Mapping[str, Any]) -> tuple[str, str, int]:
    return (
        str(item.get("prompt_id", "")),
        str(item.get("style", "")),
        int(item.get("seed", 0)),
    )


def _validated_rating(value: Any, *, context: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise RatingsError(f"{context}.rating must be an object or null")
    raw_scores = value.get("scores", {})
    if not isinstance(raw_scores, Mapping):
        raise RatingsError(f"{context}.rating.scores must be an object")
    scores: dict[str, float] = {}
    for metric, score in raw_scores.items():
        if metric not in METRIC_LABELS:
            continue
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise RatingsError(f"{context}.{metric} must be a number from 1 to 5")
        numeric = float(score)
        if not 1 <= numeric <= 5:
            raise RatingsError(f"{context}.{metric} must be from 1 to 5")
        scores[str(metric)] = numeric
    flags = value.get("flags", [])
    if not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags):
        raise RatingsError(f"{context}.rating.flags must be a list of strings")
    return {
        "scores": scores,
        "flags": sorted(set(flags)),
        "rejected": bool(value.get("rejected", False)),
    }


def load_rating_exports(paths: Iterable[str | Path]) -> dict[str, Any]:
    source_paths = [Path(path).expanduser().resolve() for path in paths]
    if not source_paths:
        raise RatingsError("At least one ratings JSON file is required")

    items_by_job: dict[str, dict[str, Any]] = {}
    stages: set[str] = set()
    input_item_count = 0
    repeated_job_exports = 0
    for source in source_paths:
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RatingsError(f"Could not read {source}: {exc}") from exc
        if not isinstance(payload, Mapping) or payload.get("schema_version") != 1:
            raise RatingsError(f"{source} is not a schema-version 1 ratings export")
        stage = str(payload.get("stage", "")).strip()
        if stage:
            stages.add(stage)
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raise RatingsError(f"{source}.items must be a list")
        for index, raw_item in enumerate(raw_items):
            context = f"{source}.items[{index}]"
            if not isinstance(raw_item, Mapping):
                raise RatingsError(f"{context} must be an object")
            candidate_id = str(raw_item.get("candidate_id", "")).strip()
            job_id = str(raw_item.get("job_id", "")).strip()
            prompt_id = str(raw_item.get("prompt_id", "")).strip()
            if not candidate_id or not job_id or not prompt_id:
                raise RatingsError(
                    f"{context} requires candidate_id, job_id, and prompt_id"
                )
            item = {
                "job_id": job_id,
                "candidate_id": candidate_id,
                "blind_label": str(raw_item.get("blind_label", "")),
                "prompt_id": prompt_id,
                "term": str(raw_item.get("term", "")),
                "gloss": str(raw_item.get("gloss", "")),
                "style": str(raw_item.get("style", "")),
                "seed": int(raw_item.get("seed", 0)),
                "rating": _validated_rating(raw_item.get("rating"), context=context),
                "source": str(source),
            }
            input_item_count += 1
            if job_id in items_by_job:
                repeated_job_exports += 1
            # Later exports win when the same job is present in several files.
            items_by_job[job_id] = item

    if len(stages) > 1:
        raise RatingsError(f"Ratings files contain different stages: {sorted(stages)}")
    return {
        "stage": next(iter(stages), "unknown"),
        "sources": [str(path) for path in source_paths],
        "input_item_count": input_item_count,
        "repeated_job_exports": repeated_job_exports,
        "items": list(items_by_job.values()),
    }


def _weighted_score(scores: Mapping[str, float], weights: Mapping[str, float]) -> float | None:
    available = [(scores[metric], weight) for metric, weight in weights.items() if metric in scores and weight > 0]
    total_weight = sum(weight for _, weight in available)
    if not total_weight:
        return None
    return sum(score * weight for score, weight in available) / total_weight


def aggregate_ratings(
    loaded: Mapping[str, Any],
    *,
    candidate_labels: Mapping[str, str] | None = None,
    weights: Mapping[str, float] = DEFAULT_WEIGHTS,
) -> dict[str, Any]:
    labels = candidate_labels or {}
    rated_items = [item for item in loaded["items"] if item["rating"] is not None]
    grouped: dict[str, dict[tuple[str, str, int], list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for item in rated_items:
        grouped[item["candidate_id"]][_evaluation_key(item)].append(item)

    expected_coverage = max((len(cells) for cells in grouped.values()), default=0)
    candidates: list[dict[str, Any]] = []
    for candidate_id, cell_map in sorted(grouped.items()):
        metric_cell_means: dict[str, list[float]] = defaultdict(list)
        cell_quality: list[float] = []
        cell_usable: list[float] = []
        cells: list[dict[str, Any]] = []
        flags: Counter[str] = Counter()
        rejected_count = 0
        item_count = 0
        for (prompt_id, style, seed), entries in sorted(cell_map.items()):
            ratings = [entry["rating"] for entry in entries]
            for metric in METRIC_LABELS:
                metric_mean = _mean(
                    rating["scores"][metric]
                    for rating in ratings
                    if metric in rating["scores"]
                )
                if metric_mean is not None:
                    metric_cell_means[metric].append(metric_mean)
            quality_values: list[float] = []
            usable_values: list[float] = []
            cell_ratings: list[dict[str, Any]] = []
            for entry, rating in zip(entries, ratings):
                quality = _weighted_score(rating["scores"], weights)
                if quality is not None:
                    quality_values.append(quality)
                    usable_values.append(0.0 if rating["rejected"] else quality)
                flags.update(rating["flags"])
                rejected_count += int(rating["rejected"])
                item_count += 1
                cell_ratings.append(
                    {
                        "job_id": entry["job_id"],
                        "scores": rating["scores"],
                        "flags": rating["flags"],
                        "rejected": rating["rejected"],
                    }
                )
            quality_mean = _mean(quality_values)
            usable_mean = _mean(usable_values)
            if quality_mean is not None:
                cell_quality.append(quality_mean)
            if usable_mean is not None:
                cell_usable.append(usable_mean)
            cells.append(
                {
                    "prompt_id": prompt_id,
                    "style": style,
                    "seed": seed,
                    "replicates": len(entries),
                    "ratings": cell_ratings,
                }
            )
        candidates.append(
            {
                "candidate_id": candidate_id,
                "label": labels.get(candidate_id, candidate_id),
                "items": item_count,
                "coverage": len(cell_map),
                "expected_coverage": expected_coverage,
                "duplicate_items": item_count - len(cell_map),
                "rejected": rejected_count,
                "reject_rate": rejected_count / item_count if item_count else 0.0,
                "flags": dict(sorted(flags.items())),
                "metrics": {
                    metric: _mean(metric_cell_means.get(metric, []))
                    for metric in METRIC_LABELS
                },
                "quality_score": _mean(cell_quality),
                "usable_score": _mean(cell_usable),
                "cells": cells,
            }
        )

    candidates.sort(
        key=lambda candidate: (
            candidate["usable_score"] is not None,
            candidate["usable_score"] or 0.0,
            candidate["coverage"],
        ),
        reverse=True,
    )
    for rank, candidate in enumerate(candidates, 1):
        candidate["rank"] = rank

    winners: dict[str, list[str]] = {}
    for metric in METRIC_LABELS:
        values = [candidate["metrics"][metric] for candidate in candidates]
        available = [value for value in values if value is not None]
        best = max(available) if available else None
        winners[metric] = [
            candidate["candidate_id"]
            for candidate in candidates
            if best is not None and candidate["metrics"][metric] == best
        ]

    unique_cells = {
        (item["candidate_id"], *_evaluation_key(item)) for item in rated_items
    }
    return {
        "schema_version": 1,
        "stage": loaded["stage"],
        "sources": loaded["sources"],
        "weights": dict(weights),
        "metric_labels": METRIC_LABELS,
        "summary": {
            "input_items": loaded["input_item_count"],
            "unique_jobs": len(loaded["items"]),
            "rated_items": len(rated_items),
            "unrated_items": len(loaded["items"]) - len(rated_items),
            "rejected_items": sum(
                int(item["rating"]["rejected"]) for item in rated_items
            ),
            "flagged_items": sum(
                int(bool(item["rating"]["flags"])) for item in rated_items
            ),
            "repeated_job_exports": loaded["repeated_job_exports"],
            "duplicate_evaluation_items": len(rated_items) - len(unique_cells),
            "candidate_count": len(candidates),
            "expected_coverage": expected_coverage,
        },
        "winners": winners,
        "candidates": candidates,
    }


def _report_document(report: Mapping[str, Any]) -> str:
    payload = json.dumps(report, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(f"Image benchmark ratings — {report['stage']}")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ color-scheme:light; font:16px system-ui,sans-serif; background:#f4f1eb; color:#25231f; }}
body {{ max-width:1500px; margin:0 auto; padding:28px; }}
h1 {{ margin-bottom:6px; }} .subtle {{ color:#68635b; }}
.panel {{ background:white; border-radius:12px; padding:16px 18px; box-shadow:0 2px 12px #0001; margin:18px 0; }}
.controls {{ display:flex; flex-wrap:wrap; gap:12px 20px; align-items:end; }}
.weight {{ display:grid; gap:4px; font-size:.85rem; }}
.weight input {{ width:78px; padding:6px; }}
label.toggle {{ display:flex; gap:7px; align-items:center; padding-bottom:7px; }}
.champions {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:10px; }}
.champion {{ background:#edf3ff; border-radius:9px; padding:10px; }}
.table-wrap {{ overflow:auto; }}
table {{ border-collapse:collapse; width:100%; background:white; font-variant-numeric:tabular-nums; }}
th,td {{ border-bottom:1px solid #ddd; padding:9px 10px; text-align:right; white-space:nowrap; }}
th:nth-child(2),td:nth-child(2),th:last-child,td:last-child {{ text-align:left; }}
th {{ position:sticky; top:0; background:#eeeae2; z-index:1; }}
th button {{ border:0; background:transparent; font:inherit; font-weight:700; cursor:pointer; padding:0; }}
tr:first-child td {{ background:#f3f8ed; }}
.coverage-low {{ color:#a24b28; font-weight:700; }}
code {{ white-space:normal; }}
</style></head><body>
<h1>{title}</h1>
<p class="subtle">Scores are balanced by prompt/style/seed: repeat runs in the same evaluation cell are averaged before model means are calculated.</p>
<section class="panel"><div id="summary"></div></section>
<section class="panel"><h2>Priorities</h2><div class="controls" id="weights"></div></section>
<section class="panel"><h2>Metric leaders</h2><div class="champions" id="champions"></div></section>
<section class="table-wrap"><table><thead><tr>
<th>#</th><th>Model</th><th><button data-sort="usable">Usable weighted</button></th><th><button data-sort="quality">Quality weighted</button></th>
<th><button data-sort="relevance">Relevance</button></th><th><button data-sort="appeal">Appeal</button></th><th><button data-sort="artifacts">Artifact freedom</button></th><th><button data-sort="legibility">Legibility</button></th>
<th>Coverage</th><th>Rejected</th><th>Flags</th></tr></thead><tbody id="rows"></tbody></table></section>
<script>const report={payload};
const metricOrder=['relevance','legibility','appeal','artifacts'];
let weights={{...report.weights}};let rejectAsZero=true;let sortKey='usable';
const esc=v=>String(v).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const mean=a=>a.length?a.reduce((x,y)=>x+y,0)/a.length:null;
function weighted(scores){{const pairs=metricOrder.filter(m=>scores[m]!=null&&weights[m]>0).map(m=>[scores[m],weights[m]]);const total=pairs.reduce((s,x)=>s+x[1],0);return total?pairs.reduce((s,x)=>s+x[0]*x[1],0)/total:null;}}
function dynamicScore(candidate,usable){{const cells=candidate.cells.map(cell=>mean(cell.ratings.map(r=>{{const q=weighted(r.scores);return usable&&rejectAsZero&&r.rejected?0:q;}}).filter(x=>x!=null))).filter(x=>x!=null);return mean(cells);}}
const fmt=v=>v==null?'—':v.toFixed(2);
function value(candidate,key){{if(key==='usable')return dynamicScore(candidate,true);if(key==='quality')return dynamicScore(candidate,false);return candidate.metrics[key];}}
function render(){{const candidates=[...report.candidates].sort((a,b)=>(value(b,sortKey)??-1)-(value(a,sortKey)??-1)||b.coverage-a.coverage);
document.querySelector('#rows').innerHTML=candidates.map((c,i)=>`<tr><td>${{i+1}}</td><td><strong>${{esc(c.label)}}</strong><br><code>${{esc(c.candidate_id)}}</code></td><td>${{fmt(dynamicScore(c,true))}}</td><td>${{fmt(dynamicScore(c,false))}}</td><td>${{fmt(c.metrics.relevance)}}</td><td>${{fmt(c.metrics.appeal)}}</td><td>${{fmt(c.metrics.artifacts)}}</td><td>${{fmt(c.metrics.legibility)}}</td><td class="${{c.coverage<c.expected_coverage?'coverage-low':''}}">${{c.coverage}}/${{c.expected_coverage}} (${{c.items}} images${{c.duplicate_items?`, ${{c.duplicate_items}} repeat`:''}})</td><td>${{c.rejected}} (${{(100*c.reject_rate).toFixed(0)}}%)</td><td>${{esc(Object.entries(c.flags).map(([k,v])=>`${{k}}:${{v}}`).join(', ')||'—')}}</td></tr>`).join('');
const best=candidates[0];document.querySelector('#summary').innerHTML=`<strong>${{esc(best?.label||'No rated model')}}</strong> currently leads the selected ranking at <strong>${{fmt(best?value(best,sortKey):null)}}/5</strong>. ${{report.summary.rated_items}} rated images, ${{report.summary.rejected_items}} rejected, ${{report.summary.flagged_items}} flagged, and ${{report.summary.duplicate_evaluation_items}} repeated evaluation images.`;}}
document.querySelector('#weights').innerHTML=metricOrder.map(m=>`<label class="weight">${{esc(report.metric_labels[m])}}<input type="number" min="0" step="5" data-weight="${{m}}" value="${{weights[m]}}"></label>`).join('')+`<label class="toggle"><input id="reject-zero" type="checkbox" checked> Count rejected images as zero</label>`;
document.querySelectorAll('[data-weight]').forEach(input=>input.oninput=e=>{{weights[e.target.dataset.weight]=Math.max(0,Number(e.target.value)||0);render();}});
document.querySelector('#reject-zero').onchange=e=>{{rejectAsZero=e.target.checked;render();}};
document.querySelectorAll('[data-sort]').forEach(button=>button.onclick=()=>{{sortKey=button.dataset.sort;render();}});
document.querySelector('#champions').innerHTML=metricOrder.map(metric=>{{const best=Math.max(...report.candidates.map(c=>c.metrics[metric]).filter(v=>v!=null));const names=report.candidates.filter(c=>c.metrics[metric]===best).map(c=>c.label).join(', ');return `<div class="champion"><strong>${{esc(report.metric_labels[metric])}}</strong><br>${{esc(names)}} — ${{fmt(best)}}/5</div>`;}}).join('');render();</script>
</body></html>"""


def write_ratings_report(
    ratings_paths: Iterable[str | Path],
    *,
    html_path: str | Path,
    json_path: str | Path | None = None,
    candidate_labels: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], Path, Path]:
    loaded = load_rating_exports(ratings_paths)
    report = aggregate_ratings(loaded, candidate_labels=candidate_labels)
    destination = Path(html_path).expanduser().resolve()
    json_destination = (
        Path(json_path).expanduser().resolve()
        if json_path is not None
        else destination.with_suffix(".json")
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    json_destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(_report_document(report), encoding="utf-8")
    json_destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report, destination, json_destination
