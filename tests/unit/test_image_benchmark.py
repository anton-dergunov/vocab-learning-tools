from __future__ import annotations

import json
import io
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from vocabgen.image_benchmark.config import (
    BenchmarkConfigError,
    CandidateConfig,
    load_benchmark_config,
)
from vocabgen.image_benchmark.harness import (
    run_benchmark,
    validate_remote_authorization,
)
from vocabgen.image_benchmark.jobs import expand_jobs
from vocabgen.image_benchmark.media import UnsafeSVGError, normalize_image, sanitize_svg_text
from vocabgen.image_benchmark.review import render_review
from scripts import image_benchmark_runner


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "image-benchmark.yaml"
RUNNER = REPO_ROOT / "scripts" / "image_benchmark_runner.py"


def load_config():
    return load_benchmark_config(CONFIG_PATH, repo_root=REPO_ROOT)


def test_tracked_config_has_expected_matrix():
    config = load_config()

    assert len(config.prompts) == 12
    assert len(expand_jobs(config, "smoke", ["icon_scene"])) == 6
    assert len(expand_jobs(config, "finalist", ["icon_scene"])) == 48
    assert config.candidates["mflux_flux2_klein_q4"].settings["quantize"] == 4
    assert config.candidates["cloudflare_flux2_klein"].remote is True


def test_job_ids_are_deterministic_and_settings_sensitive():
    config = load_config()
    first = expand_jobs(config, "smoke", ["icon_scene"])
    second = expand_jobs(config, "smoke", ["icon_scene"])
    assert [job.id for job in first] == [job.id for job in second]

    candidate = config.candidates["icon_scene"]
    changed = replace(candidate, settings={**candidate.settings, "width": 256})
    changed_config = replace(
        config, candidates={**config.candidates, "icon_scene": changed}
    )
    assert expand_jobs(changed_config, "smoke", ["icon_scene"])[0].id != first[0].id


def test_invalid_normalized_format_is_rejected(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
output:
  directory: out
  normalized: {width: 1, height: 1, format: gif, quality: 80}
prompts: []
styles: {}
stages: {}
candidates: {}
""",
        encoding="utf-8",
    )
    with pytest.raises(BenchmarkConfigError, match="format"):
        load_benchmark_config(path, repo_root=tmp_path)


def test_remote_execution_requires_switch_and_cost_ceiling():
    config = load_config()
    jobs = expand_jobs(config, "smoke", ["cloudflare_flux2_klein"])

    with pytest.raises(ValueError, match="--execute-remote"):
        validate_remote_authorization(
            jobs, config, execute_remote=False, max_cost_usd=None
        )
    with pytest.raises(ValueError, match="--max-cost-usd"):
        validate_remote_authorization(
            jobs, config, execute_remote=True, max_cost_usd=None
        )
    with pytest.raises(ValueError, match="exceeds ceiling"):
        validate_remote_authorization(
            jobs, config, execute_remote=True, max_cost_usd=0.0001
        )
    cost = validate_remote_authorization(
        jobs, config, execute_remote=True, max_cost_usd=0.01
    )
    assert cost == pytest.approx(6 * 0.000287)


def test_svg_sanitizer_rejects_scripts_and_external_urls():
    with pytest.raises(UnsafeSVGError, match="Unsupported SVG element"):
        sanitize_svg_text("<svg><script>alert(1)</script></svg>")
    with pytest.raises(UnsafeSVGError, match="External SVG reference"):
        sanitize_svg_text(
            '<svg><rect width="20" height="20" fill="url(https://bad.test/x)"/></svg>'
        )


def test_normalize_raster_to_card_size(tmp_path):
    source = tmp_path / "wide.png"
    destination = tmp_path / "card.webp"
    Image.new("RGBA", (80, 40), (255, 0, 0, 128)).save(source)

    normalize_image(
        source,
        destination,
        width=64,
        height=64,
        image_format="webp",
        quality=80,
    )

    with Image.open(destination) as normalized:
        assert normalized.size == (64, 64)
        assert normalized.mode == "RGB"


def _mock_config(tmp_path: Path):
    config = load_config()
    candidate = CandidateConfig(
        id="mock",
        label="Mock",
        provider="test",
        model="fixture-v1",
        command=(
            sys.executable,
            str(RUNNER),
            "run",
            "--backend",
            "mock",
            "--request",
            "{request}",
            "--result",
            "{result}",
        ),
        output_extension="png",
        settings={"width": 64, "height": 64, "timeout_seconds": 30},
    )
    prompts = {"spoon": config.prompts["spoon"]}
    return replace(
        config,
        output_dir=tmp_path / "output",
        prompts=prompts,
        candidates={"mock": candidate},
        normalized_width=64,
        normalized_height=64,
    )


def test_mock_runner_manifest_resume_and_review(tmp_path):
    config = _mock_config(tmp_path)
    first = run_benchmark(
        config, repo_root=REPO_ROOT, stage="smoke", candidate_ids=["mock"]
    )
    assert (first.succeeded, first.failed, first.skipped) == (1, 0, 0)
    manifest = json.loads(first.manifests[0].read_text(encoding="utf-8"))
    assert manifest["status"] == "success"
    assert manifest["native"]["generation_width"] == 64
    assert Path(manifest["normalized"]["path"]).is_file()

    resumed = run_benchmark(
        config,
        repo_root=REPO_ROOT,
        stage="smoke",
        candidate_ids=["mock"],
        resume=True,
    )
    assert (resumed.succeeded, resumed.failed, resumed.skipped) == (0, 0, 1)

    review = render_review(config, "smoke", tmp_path / "review.html")
    body = review.read_text(encoding="utf-8")
    assert "Download ratings JSON" in body
    assert "fixture-v1" not in body  # Model identity is not embedded in the card label.
    assert "data:image/webp;base64" in body


def test_mock_remote_runner_executes_with_explicit_budget(tmp_path):
    config = _mock_config(tmp_path)
    remote = replace(
        config.candidates["mock"],
        remote=True,
        estimated_cost_usd=0.002,
    )
    config = replace(config, candidates={"mock": remote})

    summary = run_benchmark(
        config,
        repo_root=REPO_ROOT,
        stage="smoke",
        candidate_ids=["mock"],
        execute_remote=True,
        max_cost_usd=0.01,
    )

    assert summary.succeeded == 1
    assert summary.projected_cost_usd == pytest.approx(0.002)


def test_failed_runner_is_recorded_without_raising(tmp_path):
    config = _mock_config(tmp_path)
    failed = replace(
        config.candidates["mock"],
        id="failed",
        command=(sys.executable, "-c", "import sys; sys.exit(7)"),
    )
    config = replace(config, candidates={"failed": failed})

    summary = run_benchmark(
        config, repo_root=REPO_ROOT, stage="smoke", candidate_ids=["failed"]
    )
    assert (summary.succeeded, summary.failed) == (0, 1)
    manifest = json.loads(summary.manifests[0].read_text(encoding="utf-8"))
    assert manifest["status"] == "error"
    assert "Runner exited 7" in manifest["error"]


def test_openverse_retrieval_path_records_license_provenance(tmp_path, monkeypatch):
    media = io.BytesIO()
    Image.new("RGB", (24, 24), "green").save(media, format="PNG")

    class Response:
        def __init__(self, *, payload=None, content=b""):
            self.payload = payload
            self.content = content

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    openverse_item = {
        "id": "public-domain-fixture",
        "thumbnail": "https://images.test/fixture.png",
        "license": "cc0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "creator": "Fixture Artist",
        "foreign_landing_url": "https://source.test/item",
        "url": "https://source.test/full.png",
    }

    def fake_get(url, **kwargs):
        if "api.openverse.org" in url:
            return Response(payload={"results": [openverse_item]})
        return Response(content=media.getvalue())

    fake_requests = types.SimpleNamespace(get=fake_get)

    class FakeTensor:
        def to(self, device):
            return self

    class FakeScores:
        def detach(self):
            return self

        def cpu(self):
            return self

        def argmax(self):
            return types.SimpleNamespace(item=lambda: 0)

    class FakeModel:
        @classmethod
        def from_pretrained(cls, model_id):
            return cls()

        def to(self, device):
            return self

        def __call__(self, **kwargs):
            return types.SimpleNamespace(logits_per_text=[FakeScores()])

    class FakeProcessor:
        @classmethod
        def from_pretrained(cls, model_id):
            return cls()

        def __call__(self, **kwargs):
            return {"inputs": FakeTensor()}

    class InferenceMode:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    fake_torch = types.SimpleNamespace(
        backends=types.SimpleNamespace(
            mps=types.SimpleNamespace(is_available=lambda: False)
        ),
        cuda=types.SimpleNamespace(is_available=lambda: False),
        inference_mode=lambda: InferenceMode(),
    )
    fake_transformers = types.SimpleNamespace(
        CLIPModel=FakeModel, CLIPProcessor=FakeProcessor
    )
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    output = tmp_path / "retrieved.png"
    request = {
        "job": {
            "prompt": "a green object",
            "gloss": "green object",
        },
        "candidate": {
            "model": "openai/clip-vit-base-patch32",
            "settings": {"top_k": 3},
        },
        "output": {"native_path": str(output)},
    }
    result = image_benchmark_runner.run_openverse(request)

    assert output.is_file()
    assert result["provenance"]["license"] == "cc0"
    assert result["provenance"]["license_verification_required"] is True
