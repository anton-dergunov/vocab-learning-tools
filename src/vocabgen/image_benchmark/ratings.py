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


def load_job_resources(
    loaded: Mapping[str, Any], benchmark_output_dir: str | Path | None
) -> dict[str, dict[str, Any]]:
    if benchmark_output_dir is None:
        return {}
    root = Path(benchmark_output_dir).expanduser().resolve() / str(loaded["stage"])
    resources: dict[str, dict[str, Any]] = {}
    for item in loaded["items"]:
        manifest_path = root / item["job_id"] / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, Mapping) or manifest.get("status") != "success":
            continue
        runner_usage = manifest.get("runner", {}).get("resource_usage", {})
        if not isinstance(runner_usage, Mapping):
            runner_usage = {}
        accelerator_bytes = runner_usage.get("peak_allocated_bytes")
        accelerator_measurement = runner_usage.get("measurement")
        if accelerator_bytes is None:
            accelerator_bytes = runner_usage.get(
                "driver_allocated_bytes_after_generation"
            )
        resources[item["job_id"]] = {
            "duration_seconds": manifest.get("duration_seconds"),
            "peak_process_rss_bytes": manifest.get("peak_process_rss_bytes")
            or runner_usage.get("process_peak_rss_bytes"),
            "accelerator_bytes": accelerator_bytes,
            "accelerator": runner_usage.get("accelerator"),
            "accelerator_measurement": accelerator_measurement,
            "native_bytes": manifest.get("native", {}).get("bytes"),
            "estimated_cost_usd": manifest.get("estimated_cost_usd"),
            "manifest_path": str(manifest_path),
        }
    return resources


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
    candidate_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    job_resources: Mapping[str, Mapping[str, Any]] | None = None,
    weights: Mapping[str, float] = DEFAULT_WEIGHTS,
) -> dict[str, Any]:
    labels = candidate_labels or {}
    metadata = candidate_metadata or {}
    resources = job_resources or {}
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
        duration_cell_means: list[float] = []
        rss_cell_means: list[float] = []
        accelerator_cell_means: list[float] = []
        native_size_cell_means: list[float] = []
        all_durations: list[float] = []
        all_rss: list[float] = []
        all_accelerator: list[float] = []
        accelerator_labels: set[str] = set()
        resource_samples = 0
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
            cell_durations: list[float] = []
            cell_rss: list[float] = []
            cell_accelerator: list[float] = []
            cell_native_sizes: list[float] = []
            for entry, rating in zip(entries, ratings):
                quality = _weighted_score(rating["scores"], weights)
                if quality is not None:
                    quality_values.append(quality)
                    usable_values.append(0.0 if rating["rejected"] else quality)
                flags.update(rating["flags"])
                rejected_count += int(rating["rejected"])
                item_count += 1
                resource_data = resources.get(entry["job_id"], {})
                duration = resource_data.get("duration_seconds")
                rss = resource_data.get("peak_process_rss_bytes")
                accelerator = resource_data.get("accelerator_bytes")
                native_size = resource_data.get("native_bytes")
                if isinstance(duration, (int, float)):
                    cell_durations.append(float(duration))
                    all_durations.append(float(duration))
                    resource_samples += 1
                if isinstance(rss, (int, float)):
                    cell_rss.append(float(rss))
                    all_rss.append(float(rss))
                if isinstance(accelerator, (int, float)):
                    cell_accelerator.append(float(accelerator))
                    all_accelerator.append(float(accelerator))
                if isinstance(native_size, (int, float)):
                    cell_native_sizes.append(float(native_size))
                if resource_data.get("accelerator"):
                    accelerator_labels.add(str(resource_data["accelerator"]))
                cell_ratings.append(
                    {
                        "job_id": entry["job_id"],
                        "scores": rating["scores"],
                        "flags": rating["flags"],
                        "rejected": rating["rejected"],
                        "resource": resource_data or None,
                    }
                )
            quality_mean = _mean(quality_values)
            usable_mean = _mean(usable_values)
            if quality_mean is not None:
                cell_quality.append(quality_mean)
            if usable_mean is not None:
                cell_usable.append(usable_mean)
            for values, destination in (
                (cell_durations, duration_cell_means),
                (cell_rss, rss_cell_means),
                (cell_accelerator, accelerator_cell_means),
                (cell_native_sizes, native_size_cell_means),
            ):
                cell_mean = _mean(values)
                if cell_mean is not None:
                    destination.append(cell_mean)
            cells.append(
                {
                    "prompt_id": prompt_id,
                    "style": style,
                    "seed": seed,
                    "replicates": len(entries),
                    "ratings": cell_ratings,
                }
            )
        candidate_meta = metadata.get(candidate_id, {})
        configured_cost = candidate_meta.get("estimated_cost_usd")
        if configured_cost is None:
            measured_costs = [
                resources[entry["job_id"]].get("estimated_cost_usd")
                for entries in cell_map.values()
                for entry in entries
                if entry["job_id"] in resources
            ]
            configured_cost = next(
                (cost for cost in measured_costs if isinstance(cost, (int, float))),
                0.0,
            )
        candidates.append(
            {
                "candidate_id": candidate_id,
                "label": candidate_meta.get(
                    "label", labels.get(candidate_id, candidate_id)
                ),
                "provider": candidate_meta.get("provider", "unknown"),
                "model": candidate_meta.get("model", "unknown"),
                "remote": bool(candidate_meta.get("remote", False)),
                "estimated_cost_usd": float(configured_cost),
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
                "resources": {
                    "samples": resource_samples,
                    "mean_duration_seconds": _mean(duration_cell_means),
                    "max_duration_seconds": max(all_durations)
                    if all_durations
                    else None,
                    "mean_peak_process_rss_bytes": _mean(rss_cell_means),
                    "max_peak_process_rss_bytes": max(all_rss) if all_rss else None,
                    "mean_accelerator_bytes": _mean(accelerator_cell_means),
                    "max_accelerator_bytes": max(all_accelerator)
                    if all_accelerator
                    else None,
                    "accelerator": ", ".join(sorted(accelerator_labels)) or None,
                    "mean_native_bytes": _mean(native_size_cell_means),
                },
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
.weight input,.weight select {{ width:90px; padding:6px; }}
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
<p class="subtle">Runtime and process RSS come from the saved manifests. Hosted-process memory is intentionally hidden. Accelerator memory appears only for runs made after backend-native telemetry was added; process RSS alone can understate Apple unified-memory and GPU pressure.</p>
<section class="panel"><div id="summary"></div></section>
<section class="panel"><h2>Priorities</h2><div class="controls" id="weights"></div></section>
<section class="panel"><h2>Metric leaders</h2><div class="champions" id="champions"></div></section>
<section class="table-wrap"><table><thead><tr>
<th>#</th><th>Model</th><th><button data-sort="usable">Usable weighted</button></th><th><button data-sort="quality">Quality weighted</button></th>
<th><button data-sort="relevance">Relevance</button></th><th><button data-sort="appeal">Appeal</button></th><th><button data-sort="artifacts">Artifact freedom</button></th><th><button data-sort="legibility">Legibility</button></th>
<th>Execution</th><th><button data-sort="duration">Mean runtime</button></th><th><button data-sort="rss">Peak process RSS</button></th><th><button data-sort="accelerator">Accelerator memory</button></th><th><button data-sort="cost">Cost/image</button></th>
<th>Coverage</th><th>Rejected</th><th>Flags</th></tr></thead><tbody id="rows"></tbody></table></section>
<script>const report={payload};
const metricOrder=['relevance','legibility','appeal','artifacts'];
let weights={{...report.weights}};let rejectAsZero=true;let sortKey='usable';let rowLimit=7;let localOnly=false;
const esc=v=>String(v).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const mean=a=>a.length?a.reduce((x,y)=>x+y,0)/a.length:null;
function weighted(scores){{const pairs=metricOrder.filter(m=>scores[m]!=null&&weights[m]>0).map(m=>[scores[m],weights[m]]);const total=pairs.reduce((s,x)=>s+x[1],0);return total?pairs.reduce((s,x)=>s+x[0]*x[1],0)/total:null;}}
function dynamicScore(candidate,usable){{const cells=candidate.cells.map(cell=>mean(cell.ratings.map(r=>{{const q=weighted(r.scores);return usable&&rejectAsZero&&r.rejected?0:q;}}).filter(x=>x!=null))).filter(x=>x!=null);return mean(cells);}}
const fmt=v=>v==null?'—':v.toFixed(2);
const seconds=v=>v==null?'—':v<10?`${{v.toFixed(1)}}s`:`${{v.toFixed(0)}}s`;
const memory=v=>v==null?'—':`${{(v/1073741824).toFixed(2)}} GiB`;
const cost=v=>v===0?'$0 local':v<0.001?`$${{v.toFixed(6)}}`:`$${{v.toFixed(4)}}`;
function value(candidate,key){{if(key==='usable')return dynamicScore(candidate,true);if(key==='quality')return dynamicScore(candidate,false);if(key==='duration')return candidate.resources.mean_duration_seconds;if(key==='rss')return candidate.resources.mean_peak_process_rss_bytes;if(key==='accelerator')return candidate.resources.mean_accelerator_bytes;if(key==='cost')return candidate.estimated_cost_usd;return candidate.metrics[key];}}
function render(){{const ascending=['duration','rss','accelerator','cost'].includes(sortKey);let candidates=report.candidates.filter(c=>!localOnly||!c.remote).sort((a,b)=>{{const av=value(a,sortKey),bv=value(b,sortKey);if(av==null&&bv==null)return b.coverage-a.coverage;if(av==null)return 1;if(bv==null)return -1;return (ascending?av-bv:bv-av)||b.coverage-a.coverage;}});if(rowLimit)candidates=candidates.slice(0,rowLimit);
document.querySelector('#rows').innerHTML=candidates.map((c,i)=>`<tr><td>${{i+1}}</td><td><strong>${{esc(c.label)}}</strong><br><code>${{esc(c.candidate_id)}}</code></td><td>${{fmt(dynamicScore(c,true))}}</td><td>${{fmt(dynamicScore(c,false))}}</td><td>${{fmt(c.metrics.relevance)}}</td><td>${{fmt(c.metrics.appeal)}}</td><td>${{fmt(c.metrics.artifacts)}}</td><td>${{fmt(c.metrics.legibility)}}</td><td>${{c.remote?'Hosted':`Local · ${{esc(c.provider)}}`}}</td><td>${{seconds(c.resources.mean_duration_seconds)}}${{c.resources.max_duration_seconds!=null?` (max ${{seconds(c.resources.max_duration_seconds)}})`:''}}</td><td>${{c.remote?'hosted':memory(c.resources.mean_peak_process_rss_bytes)}}</td><td>${{c.remote?'hosted':memory(c.resources.mean_accelerator_bytes)}}${{c.resources.accelerator?`<br><small>${{esc(c.resources.accelerator)}}</small>`:''}}</td><td>${{cost(c.estimated_cost_usd)}}</td><td class="${{c.coverage<c.expected_coverage?'coverage-low':''}}">${{c.coverage}}/${{c.expected_coverage}} (${{c.items}} images${{c.duplicate_items?`, ${{c.duplicate_items}} repeat`:''}})</td><td>${{c.rejected}} (${{(100*c.reject_rate).toFixed(0)}}%)</td><td>${{esc(Object.entries(c.flags).map(([k,v])=>`${{k}}:${{v}}`).join(', ')||'—')}}</td></tr>`).join('');
const best=candidates[0];const scored=['usable','quality','relevance','legibility','appeal','artifacts'].includes(sortKey);document.querySelector('#summary').innerHTML=`<strong>${{esc(best?.label||'No rated model')}}</strong> currently leads the selected ranking at <strong>${{fmt(best?value(best,sortKey):null)}}${{scored?'/5':''}}</strong>. ${{report.summary.rated_items}} rated images, ${{report.summary.rejected_items}} rejected, ${{report.summary.flagged_items}} flagged, and ${{report.summary.duplicate_evaluation_items}} repeated evaluation images.`;}}
document.querySelector('#weights').innerHTML=metricOrder.map(m=>`<label class="weight">${{esc(report.metric_labels[m])}}<input type="number" min="0" step="5" data-weight="${{m}}" value="${{weights[m]}}"></label>`).join('')+`<label class="weight">Rows<select id="row-limit"><option value="7" selected>Top 7</option><option value="10">Top 10</option><option value="0">All</option></select></label><label class="toggle"><input id="local-only" type="checkbox"> Local models only</label><label class="toggle"><input id="reject-zero" type="checkbox" checked> Count rejected images as zero</label>`;
document.querySelectorAll('[data-weight]').forEach(input=>input.oninput=e=>{{weights[e.target.dataset.weight]=Math.max(0,Number(e.target.value)||0);render();}});
document.querySelector('#reject-zero').onchange=e=>{{rejectAsZero=e.target.checked;render();}};
document.querySelector('#row-limit').onchange=e=>{{rowLimit=Number(e.target.value);render();}};
document.querySelector('#local-only').onchange=e=>{{localOnly=e.target.checked;render();}};
document.querySelectorAll('[data-sort]').forEach(button=>button.onclick=()=>{{sortKey=button.dataset.sort;render();}});
document.querySelector('#champions').innerHTML=metricOrder.map(metric=>{{const best=Math.max(...report.candidates.map(c=>c.metrics[metric]).filter(v=>v!=null));const names=report.candidates.filter(c=>c.metrics[metric]===best).map(c=>c.label).join(', ');return `<div class="champion"><strong>${{esc(report.metric_labels[metric])}}</strong><br>${{esc(names)}} — ${{fmt(best)}}/5</div>`;}}).join('');render();</script>
</body></html>"""


def write_ratings_report(
    ratings_paths: Iterable[str | Path],
    *,
    html_path: str | Path,
    json_path: str | Path | None = None,
    candidate_labels: Mapping[str, str] | None = None,
    candidate_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    benchmark_output_dir: str | Path | None = None,
) -> tuple[dict[str, Any], Path, Path]:
    loaded = load_rating_exports(ratings_paths)
    report = aggregate_ratings(
        loaded,
        candidate_labels=candidate_labels,
        candidate_metadata=candidate_metadata,
        job_resources=load_job_resources(loaded, benchmark_output_dir),
    )
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
