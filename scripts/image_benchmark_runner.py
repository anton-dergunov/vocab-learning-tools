#!/usr/bin/env python3
"""Isolated runner implementations for the image benchmark JSON contract.

This module deliberately imports provider SDKs only inside their backend
functions. The parent benchmark can therefore invoke it through independent
``uv run --with ...`` environments without contaminating the application.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import io
import json
import os
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Runner request must be a JSON object")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def _runtime_versions(*packages: str) -> dict[str, str]:
    versions = {"python": sys.version.split()[0]}
    for package in packages:
        version = _version(package)
        if version:
            versions[package] = version
    return versions


def _output_path(request: dict[str, Any]) -> Path:
    path = Path(request["output"]["native_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _settings(request: dict[str, Any]) -> dict[str, Any]:
    return dict(request["candidate"].get("settings", {}))


def _save_image(image: Any, output: Path) -> None:
    from PIL import Image

    if not isinstance(image, Image.Image):
        raise TypeError("Expected a Pillow image")
    image.convert("RGB").save(output)


def _save_image_bytes(data: bytes, output: Path) -> None:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        _save_image(image, output)


def run_mock(request: dict[str, Any]) -> dict[str, Any]:
    from PIL import Image, ImageDraw

    output = _output_path(request)
    settings = _settings(request)
    width, height = int(settings.get("width", 512)), int(settings.get("height", 512))
    digest = hashlib.sha256(request["job"]["prompt"].encode("utf-8")).digest()
    background = (digest[0], digest[1], digest[2])
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    margin = max(12, width // 8)
    draw.rounded_rectangle(
        (margin, margin, width - margin, height - margin),
        radius=width // 10,
        fill=(245, 242, 232),
        outline=(40, 40, 40),
        width=max(2, width // 80),
    )
    draw.ellipse(
        (width * 0.33, height * 0.27, width * 0.67, height * 0.61),
        fill=(digest[3], digest[4], digest[5]),
    )
    image.save(output)
    return {"runtime_versions": _runtime_versions("Pillow"), "provenance": {"kind": "offline-fixture"}}


def _icon_svg(name: str, x: int, y: int, scale: float, color: str) -> str:
    """Small original primitive library; no external SVG is injected."""
    s = scale
    if name == "spoon":
        return f'<ellipse cx="{x}" cy="{y-45*s}" rx="{24*s}" ry="{34*s}" fill="{color}"/><rect x="{x-6*s}" y="{y-12*s}" width="{12*s}" height="{90*s}" rx="{6*s}" fill="{color}"/>'
    if name == "shirt":
        points = f"{x-65*s},{y-45*s} {x-28*s},{y-72*s} {x-15*s},{y-50*s} {x+15*s},{y-50*s} {x+28*s},{y-72*s} {x+65*s},{y-45*s} {x+43*s},{y-10*s} {x+30*s},{y-18*s} {x+30*s},{y+72*s} {x-30*s},{y+72*s} {x-30*s},{y-18*s} {x-43*s},{y-10*s}"
        return f'<polygon points="{points}" fill="{color}"/>'
    if name == "person":
        return f'<circle cx="{x}" cy="{y-52*s}" r="{24*s}" fill="{color}"/><path d="M {x-48*s} {y+58*s} Q {x-42*s} {y-8*s} {x} {y-10*s} Q {x+42*s} {y-8*s} {x+48*s} {y+58*s} Z" fill="{color}"/>'
    if name == "server":
        return f'<rect x="{x-65*s}" y="{y-68*s}" width="{130*s}" height="{136*s}" rx="{12*s}" fill="{color}"/><line x1="{x-46*s}" y1="{y-23*s}" x2="{x+46*s}" y2="{y-23*s}" stroke="#ffffff" stroke-width="{9*s}"/><line x1="{x-46*s}" y1="{y+22*s}" x2="{x+22*s}" y2="{y+22*s}" stroke="#ffffff" stroke-width="{9*s}"/><circle cx="{x+43*s}" cy="{y+22*s}" r="{6*s}" fill="#ffcf4a"/>'
    if name == "building":
        return f'<rect x="{x-72*s}" y="{y-56*s}" width="{144*s}" height="{126*s}" rx="{8*s}" fill="{color}"/><polygon points="{x-86*s},{y-56*s} {x},{y-108*s} {x+86*s},{y-56*s}" fill="{color}"/><rect x="{x-18*s}" y="{y+12*s}" width="{36*s}" height="{58*s}" fill="#fff4d6"/><rect x="{x-54*s}" y="{y-30*s}" width="{25*s}" height="{25*s}" fill="#fff4d6"/><rect x="{x+29*s}" y="{y-30*s}" width="{25*s}" height="{25*s}" fill="#fff4d6"/>'
    if name == "grain":
        grains = "".join(f'<ellipse cx="{x + ((i%2)*22-11)*s}" cy="{y + (i*22-65)*s}" rx="{12*s}" ry="{21*s}" fill="{color}" transform="rotate({-28 if i%2 else 28} {x} {y})"/>' for i in range(6))
        return grains + f'<line x1="{x}" y1="{y-82*s}" x2="{x}" y2="{y+84*s}" stroke="#6c8b3c" stroke-width="{7*s}"/>'
    if name == "music":
        return f'<circle cx="{x-34*s}" cy="{y+45*s}" r="{28*s}" fill="{color}"/><circle cx="{x+52*s}" cy="{y+20*s}" r="{28*s}" fill="{color}"/><rect x="{x-12*s}" y="{y-80*s}" width="{14*s}" height="{128*s}" fill="{color}"/><rect x="{x+74*s}" y="{y-102*s}" width="{14*s}" height="{125*s}" fill="{color}"/><polygon points="{x-12*s},{y-80*s} {x+88*s},{y-106*s} {x+88*s},{y-78*s} {x-12*s},{y-53*s}" fill="{color}"/>'
    if name == "heart":
        return f'<path d="M {x} {y+66*s} C {x-110*s} {y-2*s}, {x-66*s} {y-96*s}, {x} {y-43*s} C {x+66*s} {y-96*s}, {x+110*s} {y-2*s}, {x} {y+66*s} Z" fill="{color}"/>'
    if name == "razor":
        return f'<rect x="{x-58*s}" y="{y-66*s}" width="{116*s}" height="{42*s}" rx="{8*s}" fill="{color}"/><rect x="{x-18*s}" y="{y-24*s}" width="{36*s}" height="{115*s}" rx="{15*s}" fill="{color}"/><line x1="{x-42*s}" y1="{y-52*s}" x2="{x+42*s}" y2="{y-52*s}" stroke="#ffffff" stroke-width="{7*s}"/>'
    if name == "ruler":
        ticks = "".join(f'<line x1="{x-72*s+i*24*s}" y1="{y-18*s}" x2="{x-72*s+i*24*s}" y2="{y+(18 if i%2 else 34)*s}" stroke="#453a2d" stroke-width="{4*s}"/>' for i in range(7))
        return f'<rect x="{x-88*s}" y="{y-35*s}" width="{176*s}" height="{70*s}" rx="{8*s}" fill="{color}"/>{ticks}'
    if name == "people":
        return _icon_svg("person", x-48, y+8, s*0.72, color) + _icon_svg("person", x+48, y+8, s*0.72, color)
    return f'<circle cx="{x}" cy="{y}" r="{62*s}" fill="{color}"/><path d="M {x-28*s} {y} L {x-4*s} {y+27*s} L {x+40*s} {y-36*s}" fill="none" stroke="#ffffff" stroke-width="{12*s}" stroke-linecap="round" stroke-linejoin="round"/>'


def run_icon_scene(request: dict[str, Any]) -> dict[str, Any]:
    output = _output_path(request)
    settings = _settings(request)
    width, height = int(settings.get("width", 512)), int(settings.get("height", 512))
    scene = dict(request["job"].get("scene", {}))
    background = str(scene.get("background", "#f6f0df"))
    accent = str(scene.get("accent", "#356a72"))
    secondary = str(scene.get("secondary", "#d46a4c"))
    icons = list(scene.get("icons", ["symbol"]))[:3]
    if len(icons) == 1:
        placements = [(width // 2, height // 2, 1.35, accent)]
    elif len(icons) == 2:
        placements = [(width * 3 // 10, height // 2, 0.95, accent), (width * 7 // 10, height // 2, 0.95, secondary)]
    else:
        placements = [(width // 4, height // 2, 0.72, accent), (width // 2, height // 2, 0.72, secondary), (width * 3 // 4, height // 2, 0.72, accent)]
    body = "".join(_icon_svg(name, x, y, scale, color) for name, (x, y, scale, color) in zip(icons, placements))
    relation = scene.get("relation")
    if relation == "arrow" and len(icons) > 1:
        body += f'<line x1="{width*0.43}" y1="{height*0.78}" x2="{width*0.57}" y2="{height*0.78}" stroke="#413b35" stroke-width="10" stroke-linecap="round"/><polygon points="{width*0.57},{height*0.78} {width*0.53},{height*0.74} {width*0.53},{height*0.82}" fill="#413b35"/>'
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="{width}" height="{height}" rx="42" fill="{background}"/>{body}</svg>'
    output.write_text(svg, encoding="utf-8")
    return {
        "runtime_versions": _runtime_versions(),
        "provenance": {"kind": "deterministic-scene", "primitive_library": "vocabgen-original-v1", "scene": scene},
    }


def run_openverse(request: dict[str, Any]) -> dict[str, Any]:
    import requests
    import torch
    from PIL import Image
    from transformers import CLIPModel, CLIPProcessor

    output = _output_path(request)
    settings = _settings(request)
    query = str(settings.get("query_override") or request["job"]["gloss"])
    top_k = int(settings.get("top_k", 12))
    response = requests.get(
        "https://api.openverse.org/v1/images/",
        params={"q": query, "license": "cc0,pdm", "page_size": top_k, "mature": "false"},
        headers={"User-Agent": "vocabgen-image-benchmark/1.0"},
        timeout=30,
    )
    response.raise_for_status()
    results = [
        item for item in response.json().get("results", [])
        if str(item.get("license", "")).lower() in {"cc0", "pdm"}
    ]
    images, usable = [], []
    for item in results:
        url = item.get("thumbnail") or item.get("url")
        if not url:
            continue
        try:
            media = requests.get(url, timeout=20)
            media.raise_for_status()
            image = Image.open(io.BytesIO(media.content)).convert("RGB")
            images.append(image.copy())
            usable.append(item)
        except Exception:
            continue
    if not images:
        raise RuntimeError("Openverse returned no downloadable CC0/public-domain images")

    clip_id = str(settings.get("clip_model", "openai/clip-vit-base-patch32"))
    device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
    model = CLIPModel.from_pretrained(clip_id).to(device)
    processor = CLIPProcessor.from_pretrained(clip_id)
    inputs = processor(text=[request["job"]["prompt"]], images=images, return_tensors="pt", padding=True)
    inputs = {key: value.to(device) for key, value in inputs.items()}
    with torch.inference_mode():
        scores = model(**inputs).logits_per_text[0].detach().cpu()
    selected = int(scores.argmax().item())
    _save_image(images[selected], output)
    item = usable[selected]
    return {
        "runtime_versions": _runtime_versions("requests", "torch", "transformers", "Pillow"),
        "provenance": {
            "kind": "retrieval",
            "source": "Openverse",
            "query": query,
            "clip_model": clip_id,
            "openverse_id": item.get("id"),
            "creator": item.get("creator"),
            "license": item.get("license"),
            "license_url": item.get("license_url"),
            "foreign_landing_url": item.get("foreign_landing_url"),
            "source_url": item.get("url"),
            "license_verification_required": True,
        },
    }


def _torch_device(torch: Any, requested: str) -> str:
    if requested != "auto":
        return requested
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def run_diffusers(request: dict[str, Any]) -> dict[str, Any]:
    import torch
    from diffusers import DiffusionPipeline

    output = _output_path(request)
    settings = _settings(request)
    device = _torch_device(torch, str(settings.get("device", "auto")))
    dtype = torch.float32 if device == "cpu" else torch.float16
    model_id = request["candidate"]["model"]
    configured_revision = request["candidate"].get("revision") or settings.get("revision")
    load_options: dict[str, Any] = {"torch_dtype": dtype}
    if configured_revision:
        load_options["revision"] = configured_revision
    pipeline = DiffusionPipeline.from_pretrained(model_id, **load_options)
    pipeline = pipeline.to(device)
    if settings.get("attention_slicing", True) and hasattr(pipeline, "enable_attention_slicing"):
        pipeline.enable_attention_slicing()
    generator = torch.Generator(device="cpu").manual_seed(int(request["job"]["seed"]))
    generation = {
        "prompt": request["job"]["prompt"],
        "width": int(settings.get("width", 512)),
        "height": int(settings.get("height", 512)),
        "num_inference_steps": int(settings.get("steps", 20)),
        "guidance_scale": float(settings.get("guidance", 7.5)),
        "generator": generator,
    }
    if settings.get("negative_prompt"):
        generation["negative_prompt"] = settings["negative_prompt"]
    image = pipeline(**generation).images[0]
    _save_image(image, output)
    return {
        "runtime_versions": _runtime_versions("torch", "diffusers", "transformers", "accelerate"),
        "provenance": {
            "kind": "generation",
            "device": device,
            "model": model_id,
            "configured_revision": configured_revision,
            "resolved_revision": getattr(pipeline.config, "_commit_hash", None),
        },
    }


def run_mflux(request: dict[str, Any]) -> dict[str, Any]:
    import mlx.core as mx
    from mflux.models.common.config.model_config import ModelConfig
    from mflux.models.flux2.variants.txt2img.flux2_klein import Flux2Klein

    output = _output_path(request)
    settings = _settings(request)
    model_id = request["candidate"]["model"]
    configured_revision = request["candidate"].get("revision") or settings.get("revision")
    model_path = None if model_id == "black-forest-labs/FLUX.2-klein-4B" else model_id
    model = Flux2Klein(
        quantize=int(settings.get("quantize", 4)),
        model_path=model_path,
        model_config=ModelConfig.flux2_klein_4b(),
    )
    generated = model.generate_image(
        seed=int(request["job"]["seed"]),
        prompt=request["job"]["prompt"],
        num_inference_steps=int(settings.get("steps", 4)),
        height=int(settings.get("height", 512)),
        width=int(settings.get("width", 512)),
        guidance=float(settings.get("guidance", 1.0)),
    )
    mx.eval(generated.image)
    generated.image.save(output)
    return {
        "runtime_versions": _runtime_versions("mflux", "mlx"),
        "provenance": {
            "kind": "generation",
            "device": "mlx",
            "model": model_id,
            "configured_revision": configured_revision,
        },
    }


def run_mflux_z_image(request: dict[str, Any]) -> dict[str, Any]:
    from mflux.models.common.config.model_config import ModelConfig
    from mflux.models.z_image import ZImageTurbo

    output = _output_path(request)
    settings = _settings(request)
    model_id = request["candidate"]["model"]
    configured_revision = request["candidate"].get("revision") or settings.get("revision")
    quantize = settings.get("quantize")
    model = ZImageTurbo(
        quantize=int(quantize) if quantize is not None else None,
        model_path=model_id,
        model_config=ModelConfig.z_image_turbo(),
    )
    image = model.generate_image(
        seed=int(request["job"]["seed"]),
        prompt=request["job"]["prompt"],
        num_inference_steps=int(settings.get("steps", 9)),
        height=int(settings.get("height", 512)),
        width=int(settings.get("width", 512)),
        guidance=float(settings.get("guidance", 0.0)),
    )
    _save_image(image, output)
    return {
        "runtime_versions": _runtime_versions("mflux", "mlx"),
        "provenance": {
            "kind": "generation",
            "device": "mlx",
            "model": model_id,
            "configured_revision": configured_revision,
            "prequantized": quantize is None,
            "quantize": quantize,
        },
    }


def run_drawthings(request: dict[str, Any]) -> dict[str, Any]:
    output = _output_path(request)
    settings = _settings(request)
    executable = str(settings.get("executable", "draw-things-cli"))
    command = [
        executable,
        "generate",
        "--model", str(settings.get("checkpoint", "flux_2_klein_4b_q6p.ckpt")),
        "--prompt", request["job"]["prompt"],
        "--width", str(settings.get("width", 512)),
        "--height", str(settings.get("height", 512)),
        "--steps", str(settings.get("steps", 4)),
        "--cfg", str(settings.get("guidance", 1)),
        "--seed", str(request["job"]["seed"]),
        "--output", str(output),
    ]
    if settings.get("models_dir"):
        command.extend(["--models-dir", os.path.expanduser(str(settings["models_dir"]))])
    if settings.get("offline", False):
        command.extend(["--offline", "--no-download-missing"])
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return {
        "runtime_versions": _runtime_versions(),
        "provenance": {"kind": "generation", "runtime": "draw-things-cli", "command": command},
    }


def run_cloudflare(request: dict[str, Any]) -> dict[str, Any]:
    import requests

    output = _output_path(request)
    settings = _settings(request)
    account_id = os.environ[str(settings.get("account_id_env", "CLOUDFLARE_ACCOUNT_ID"))]
    token = os.environ[str(settings.get("token_env", "CLOUDFLARE_API_TOKEN"))]
    model = request["candidate"]["model"]
    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    # Cloudflare's FLUX.2 partner models require multipart/form-data even for
    # text-only requests. The (None, value) tuples force requests to include a
    # multipart boundary without representing scalar fields as uploaded files.
    fields = {
        "prompt": (None, request["job"]["prompt"]),
        "width": (None, str(int(settings.get("width", 512)))),
        "height": (None, str(int(settings.get("height", 512)))),
        "seed": (None, str(int(request["job"]["seed"]))),
        "guidance": (None, str(float(settings.get("guidance", 1.0)))),
    }
    response = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {token}"},
        files=fields,
        timeout=float(settings.get("request_timeout_seconds", 180)),
    )
    if not response.ok:
        try:
            detail = json.dumps(response.json(), ensure_ascii=False)
        except (ValueError, TypeError):
            detail = response.text
        detail = detail.strip()[:2000] or "empty response body"
        raise RuntimeError(f"Cloudflare HTTP {response.status_code}: {detail}")
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("image/"):
        data = response.content
    else:
        payload = response.json()
        if not payload.get("success", True):
            raise RuntimeError(str(payload.get("errors")))
        result = payload.get("result", payload)
        encoded = result.get("image") if isinstance(result, dict) else result
        if isinstance(encoded, list):
            encoded = encoded[0]
        if not isinstance(encoded, str):
            raise RuntimeError("Cloudflare response did not contain image data")
        data = base64.b64decode(encoded.split(",", 1)[-1])
    _save_image_bytes(data, output)
    return {
        "runtime_versions": _runtime_versions("requests"),
        "provenance": {
            "kind": "generation",
            "service": "Cloudflare Workers AI",
            "model": model,
            "request_format": "multipart/form-data",
        },
    }


def run_bfl(request: dict[str, Any]) -> dict[str, Any]:
    import requests

    output = _output_path(request)
    settings = _settings(request)
    api_key = os.environ[str(settings.get("api_key_env", "BFL_API_KEY"))]
    endpoint = str(settings.get("endpoint", "https://api.bfl.ai/v1/flux-2-klein-4b"))
    response = requests.post(
        endpoint,
        headers={"x-key": api_key, "Content-Type": "application/json"},
        json={
            "prompt": request["job"]["prompt"],
            "width": int(settings.get("width", 512)),
            "height": int(settings.get("height", 512)),
            "seed": int(request["job"]["seed"]),
        },
        timeout=30,
    )
    response.raise_for_status()
    task_id = response.json()["id"]
    poll_url = str(settings.get("poll_url", "https://api.bfl.ai/v1/get_result"))
    deadline = time.monotonic() + float(settings.get("request_timeout_seconds", 300))
    result: dict[str, Any] = {}
    while time.monotonic() < deadline:
        poll = requests.get(poll_url, headers={"x-key": api_key}, params={"id": task_id}, timeout=30)
        poll.raise_for_status()
        result = poll.json()
        if result.get("status") == "Ready":
            break
        if result.get("status") in {"Error", "Failed"}:
            raise RuntimeError(str(result))
        time.sleep(1.0)
    else:
        raise TimeoutError(f"BFL task {task_id} did not finish")
    sample_url = result.get("result", {}).get("sample")
    media = requests.get(sample_url, timeout=60)
    media.raise_for_status()
    _save_image_bytes(media.content, output)
    return {"runtime_versions": _runtime_versions("requests"), "provenance": {"kind": "generation", "service": "BFL API", "task_id": task_id, "sample_url": sample_url}}


def run_gemini(request: dict[str, Any]) -> dict[str, Any]:
    from google import genai
    from google.genai import types

    output = _output_path(request)
    settings = _settings(request)
    if settings.get("vertexai", True):
        project = os.environ[str(settings.get("project_env", "GOOGLE_CLOUD_PROJECT"))]
        location = os.environ.get(str(settings.get("location_env", "GOOGLE_CLOUD_LOCATION")), "global")
        client = genai.Client(vertexai=True, project=project, location=location)
    else:
        client = genai.Client(api_key=os.environ[str(settings.get("api_key_env", "GEMINI_API_KEY"))])
    response = client.models.generate_content(
        model=request["candidate"]["model"],
        contents=request["job"]["prompt"],
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )
    for candidate in response.candidates or []:
        for part in candidate.content.parts or []:
            if getattr(part, "inline_data", None) and part.inline_data.data:
                _save_image_bytes(part.inline_data.data, output)
                return {"runtime_versions": _runtime_versions("google-genai"), "provenance": {"kind": "generation", "service": "Google GenAI", "model": request["candidate"]["model"], "vertexai": bool(settings.get("vertexai", True))}}
    raise RuntimeError("Gemini response contained no image")


def run_starvector(request: dict[str, Any]) -> dict[str, Any]:
    import torch
    from transformers import AutoModelForCausalLM

    output = _output_path(request)
    settings = _settings(request)
    model_id = request["candidate"]["model"]
    configured_revision = request["candidate"].get("revision") or settings.get("revision")
    device = _torch_device(torch, str(settings.get("device", "auto")))
    dtype = torch.float16 if device in {"mps", "cuda"} else torch.float32
    load_options: dict[str, Any] = {
        "torch_dtype": dtype,
        "trust_remote_code": True,
    }
    if configured_revision:
        load_options["revision"] = configured_revision
    model = AutoModelForCausalLM.from_pretrained(model_id, **load_options)
    model = model.to(device).eval()
    target = model if hasattr(model, "generate_text2svg") else getattr(model, "model", model)
    if not hasattr(target, "generate_text2svg"):
        raise RuntimeError(
            "This StarVector checkpoint exposes no generate_text2svg method; "
            "the upstream 1B release may be image-to-SVG-only despite its model-card task claim"
        )
    prompt = request["job"]["prompt"]
    try:
        generated = target.generate_text2svg(
            {"text": [prompt]},
            max_length=int(settings.get("max_length", 2048)),
            temperature=float(settings.get("temperature", 0.4)),
        )
    except TypeError:
        generated = target.generate_text2svg(
            prompt,
            max_length=int(settings.get("max_length", 2048)),
            temperature=float(settings.get("temperature", 0.4)),
        )
    svg = generated[0] if isinstance(generated, (list, tuple)) else generated
    if not isinstance(svg, str) or "<svg" not in svg:
        raise RuntimeError("StarVector did not return SVG text")
    svg = svg[svg.index("<svg") :]
    output.write_text(svg, encoding="utf-8")
    return {
        "runtime_versions": _runtime_versions("torch", "transformers"),
        "provenance": {
            "kind": "generation",
            "model": model_id,
            "configured_revision": configured_revision,
            "resolved_revision": getattr(model.config, "_commit_hash", None),
            "device": device,
            "experimental": True,
        },
    }


BACKENDS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "mock": run_mock,
    "icon-scene": run_icon_scene,
    "openverse": run_openverse,
    "diffusers": run_diffusers,
    "mflux": run_mflux,
    "mflux-z-image": run_mflux_z_image,
    "drawthings": run_drawthings,
    "cloudflare": run_cloudflare,
    "bfl": run_bfl,
    "gemini": run_gemini,
    "starvector": run_starvector,
}


def run_command(args: argparse.Namespace) -> int:
    request = _read_json(args.request)
    started = time.perf_counter()
    try:
        details = BACKENDS[args.backend](request)
        result = {"contract_version": 1, "status": "success", "backend": args.backend, "backend_duration_seconds": time.perf_counter() - started, **details}
        _write_json(args.result, result)
        return 0
    except Exception as exc:
        result = {"contract_version": 1, "status": "error", "backend": args.backend, "backend_duration_seconds": time.perf_counter() - started, "error": f"{type(exc).__name__}: {exc}"}
        _write_json(args.result, result)
        print(result["error"], file=sys.stderr)
        return 1


def prepare_command(args: argparse.Namespace) -> int:
    from huggingface_hub import snapshot_download

    path = snapshot_download(repo_id=args.model_id)
    print(path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--backend", choices=sorted(BACKENDS), required=True)
    run.add_argument("--request", type=Path, required=True)
    run.add_argument("--result", type=Path, required=True)
    run.set_defaults(handler=run_command)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--model-id", required=True)
    prepare.set_defaults(handler=prepare_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
