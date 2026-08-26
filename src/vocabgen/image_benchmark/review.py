from __future__ import annotations

import base64
import hashlib
import html
import json
from pathlib import Path
from typing import Any, Iterable

from .config import BenchmarkConfig
from .harness import read_json


def _data_url(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = {".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}[suffix]
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _blind_labels(candidate_ids: Iterable[str], salt: str) -> dict[str, str]:
    ordered = sorted(
        set(candidate_ids),
        key=lambda value: hashlib.sha256(f"{salt}:{value}".encode()).hexdigest(),
    )
    return {candidate_id: f"Model {chr(65 + index)}" for index, candidate_id in enumerate(ordered)}


def collect_review_items(config: BenchmarkConfig, stage: str) -> list[dict[str, Any]]:
    newest_by_cell: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    for path in (config.output_dir / stage).glob("*/manifest.json"):
        try:
            manifest = read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if manifest.get("status") != "success":
            continue
        job = manifest.get("job", {})
        try:
            cell = (
                str(job["candidate_id"]),
                str(job["prompt_id"]),
                str(job["style_id"]),
                int(job["seed"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        previous = newest_by_cell.get(cell)
        if previous is None or float(manifest.get("started_at_unix", 0)) >= float(
            previous.get("started_at_unix", 0)
        ):
            newest_by_cell[cell] = manifest
    manifests = list(newest_by_cell.values())
    labels = _blind_labels(
        (item["job"]["candidate_id"] for item in manifests), config.review_blind_salt
    )
    items: list[dict[str, Any]] = []
    for manifest in manifests:
        normalized = Path(manifest["normalized"]["path"])
        if not normalized.is_absolute():
            normalized = config.source_path.parent.parent / normalized
        if not normalized.is_file():
            continue
        job = manifest["job"]
        candidate_id = job["candidate_id"]
        items.append(
            {
                "job_id": job["id"],
                "candidate_id": candidate_id,
                "blind_label": labels[candidate_id],
                "prompt_id": job["prompt_id"],
                "term": job["term"],
                "gloss": job["gloss"],
                "style": job["style_id"],
                "seed": job["seed"],
                "image": _data_url(normalized),
            }
        )
    items.sort(
        key=lambda item: hashlib.sha256(
            f"{config.review_blind_salt}:{item['job_id']}".encode()
        ).hexdigest()
    )
    return items


def render_review(config: BenchmarkConfig, stage: str, output_path: Path) -> Path:
    items = collect_review_items(config, stage)
    payload = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(f"Image benchmark review — {stage}")
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ color-scheme: light; font: 16px system-ui, sans-serif; background:#f4f1eb; color:#25231f; }}
body {{ max-width:1100px; margin:0 auto; padding:24px; }}
header {{ position:sticky; top:0; z-index:2; background:#f4f1ebee; padding:12px 0; backdrop-filter:blur(8px); }}
.toolbar {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }}
button {{ border:1px solid #777; border-radius:7px; background:white; padding:8px 12px; cursor:pointer; }}
#cards {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:18px; }}
.card {{ background:white; border:3px solid transparent; border-radius:12px; padding:14px; box-shadow:0 2px 12px #0001; }}
.card.selected {{ border-color:#496db6; }}
.card.rejected {{ opacity:.62; background:#f4dddd; }}
.image-wrap {{ display:flex; justify-content:center; background:#fafafa; border-radius:8px; }}
img {{ width:100%; max-width:384px; aspect-ratio:1; object-fit:contain; }}
h2 {{ font-size:1.2rem; margin:10px 0 2px; }}
.meta {{ color:#666; font-size:.85rem; }}
.metrics {{ display:grid; grid-template-columns:1fr auto; gap:5px 12px; margin-top:10px; }}
.metric.active {{ color:#315ca8; font-weight:700; }}
.flags {{ display:flex; gap:8px; flex-wrap:wrap; font-size:.82rem; margin-top:10px; }}
kbd {{ background:#eee; border:1px solid #bbb; border-radius:4px; padding:1px 5px; }}
#empty {{ padding:50px; text-align:center; }}
</style></head><body>
<header><h1>{title}</h1>
<p>Use <kbd>←</kbd>/<kbd>→</kbd> to navigate, <kbd>R</kbd>/<kbd>L</kbd>/<kbd>A</kbd>/<kbd>F</kbd> to choose a metric, <kbd>1</kbd>–<kbd>5</kbd> to score, and <kbd>X</kbd> to reject.</p>
<div class="toolbar"><span id="progress"></span><button id="download">Download ratings JSON</button><button id="reveal">Reveal model identities</button></div></header>
<main id="cards"></main><div id="empty" hidden>No successful images were found for this stage.</div>
<script>const items={payload};
const storageKey='vocabgen-image-review:{html.escape(stage)}';
let ratings=JSON.parse(localStorage.getItem(storageKey)||'{{}}'); let selected=0; let metric='relevance'; let revealed=false;
const metrics={{relevance:'Mnemonic relevance',legibility:'Small-size legibility',appeal:'Visual appeal',artifacts:'Artifact freedom'}};
const esc=value=>String(value).replace(/[&<>"']/g,char=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[char]));
function save(){{localStorage.setItem(storageKey,JSON.stringify(ratings)); render();}}
function rating(id){{return ratings[id]||(ratings[id]={{scores:{{}},flags:[],rejected:false}});}}
function render(){{const root=document.querySelector('#cards'); root.innerHTML=''; document.querySelector('#empty').hidden=items.length>0;
items.forEach((item,i)=>{{const value=rating(item.job_id); const card=document.createElement('article'); card.className='card'+(i===selected?' selected':'')+(value.rejected?' rejected':'');
const metricHtml=Object.entries(metrics).map(([key,label])=>`<span class="metric ${{key===metric?'active':''}}">${{label}}</span><strong>${{value.scores[key]||'—'}}/5</strong>`).join('');
card.innerHTML=`<div class="image-wrap"><img src="${{item.image}}" alt="benchmark output"></div><h2>${{esc(item.term)}} — ${{esc(item.gloss)}}</h2><div class="meta">${{esc(revealed?item.candidate_id:item.blind_label)}} · ${{esc(item.style)}} · seed ${{item.seed}}</div><div class="metrics">${{metricHtml}}</div><div class="flags">${{['irrelevant','unwanted-text','unsafe','broken-anatomy'].map(flag=>`<label><input type="checkbox" data-flag="${{flag}}" ${{value.flags.includes(flag)?'checked':''}}>${{flag}}</label>`).join('')}}</div>`;
card.onclick=e=>{{if(e.target.closest('label,input,button,a'))return;selected=i;render();}}; card.querySelectorAll('[data-flag]').forEach(box=>{{box.onclick=e=>e.stopPropagation();box.onchange=e=>{{e.stopPropagation();const f=e.target.dataset.flag;value.flags=e.target.checked?[...new Set([...value.flags,f])]:value.flags.filter(x=>x!==f);save();}};}}); root.appendChild(card);}});
const rated=items.filter(item=>{{const x=ratings[item.job_id];return x&&(Object.keys(x.scores||{{}}).length||x.rejected||(x.flags||[]).length);}}).length; document.querySelector('#progress').textContent=`${{rated}} / ${{items.length}} reviewed`;}}
document.addEventListener('keydown',e=>{{if(!items.length)return; if(e.key==='ArrowRight')selected=Math.min(items.length-1,selected+1); else if(e.key==='ArrowLeft')selected=Math.max(0,selected-1); else if('rla f'.replace(/ /g,'').includes(e.key.toLowerCase())){{const map={{r:'relevance',l:'legibility',a:'appeal',f:'artifacts'}};metric=map[e.key.toLowerCase()]||metric;}} else if(/^[1-5]$/.test(e.key)){{rating(items[selected].job_id).scores[metric]=Number(e.key);save();return;}} else if(e.key.toLowerCase()==='x'){{const v=rating(items[selected].job_id);v.rejected=!v.rejected;save();return;}} render();}});
document.querySelector('#reveal').onclick=()=>{{revealed=!revealed;render();}};
document.querySelector('#download').onclick=()=>{{const exportData={{schema_version:1,stage:{json.dumps(stage)},exported_at:new Date().toISOString(),items:items.map(i=>({{...i,image:undefined,rating:ratings[i.job_id]||null}}))}}; const blob=new Blob([JSON.stringify(exportData,null,2)],{{type:'application/json'}}); const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`image-benchmark-${{exportData.stage}}-ratings.json`;a.click();URL.revokeObjectURL(a.href);}}; render();</script>
</body></html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
    return output_path
