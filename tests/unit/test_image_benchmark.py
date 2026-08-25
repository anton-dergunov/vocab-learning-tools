from __future__ import annotations

import base64
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
    assert config.candidates["mflux_z_image_turbo_q4"].model.endswith("mflux-4bit")
    assert config.candidates["mflux_z_image_turbo_q4"].settings["quantize"] is None
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


def test_cloudflare_uses_multipart_and_decodes_base64_result(tmp_path, monkeypatch):
    media = io.BytesIO()
    Image.new("RGB", (24, 24), "orange").save(media, format="PNG")
    captured = {}

    class Response:
        ok = True
        status_code = 200
        headers = {"content-type": "application/json"}
        content = b""
        text = ""

        def json(self):
            return {
                "success": True,
                "result": {"image": base64.b64encode(media.getvalue()).decode("ascii")},
            }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(post=fake_post))
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account-fixture")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token-fixture")
    output = tmp_path / "cloudflare.png"
    request = {
        "job": {"prompt": "an orange square", "seed": 17},
        "candidate": {
            "model": "@cf/black-forest-labs/flux-2-klein-4b",
            "settings": {"width": 512, "height": 512, "guidance": 1.0},
        },
        "output": {"native_path": str(output)},
    }

    result = image_benchmark_runner.run_cloudflare(request)

    assert output.is_file()
    assert "json" not in captured
    assert captured["files"]["prompt"] == (None, "an orange square")
    assert captured["files"]["width"] == (None, "512")
    assert result["provenance"]["request_format"] == "multipart/form-data"


def test_cloudflare_error_includes_response_body(tmp_path, monkeypatch):
    class Response:
        ok = False
        status_code = 400
        headers = {"content-type": "application/json"}
        text = ""

        def json(self):
            return {"success": False, "errors": [{"code": 5006, "message": "bad multipart"}]}

    monkeypatch.setitem(
        sys.modules,
        "requests",
        types.SimpleNamespace(post=lambda *args, **kwargs: Response()),
    )
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account-fixture")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token-fixture")
    request = {
        "job": {"prompt": "fixture", "seed": 17},
        "candidate": {
            "model": "@cf/black-forest-labs/flux-2-klein-4b",
            "settings": {},
        },
        "output": {"native_path": str(tmp_path / "unused.png")},
    }

    with pytest.raises(RuntimeError, match="5006.*bad multipart"):
        image_benchmark_runner.run_cloudflare(request)


def test_gemini_configures_bounded_retry_for_429(tmp_path, monkeypatch):
    media = io.BytesIO()
    Image.new("RGB", (24, 24), "blue").save(media, format="PNG")
    captured = {}

    class FakeHttpRetryOptions:
        def __init__(self, **kwargs):
            self.values = kwargs

    class FakeHttpOptions:
        def __init__(self, **kwargs):
            self.retry_options = kwargs["retry_options"]

    class FakeGenerateContentConfig:
        def __init__(self, **kwargs):
            captured["generate_config"] = kwargs

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.models = self

        def generate_content(self, **kwargs):
            captured["generate"] = kwargs
            part = types.SimpleNamespace(
                inline_data=types.SimpleNamespace(data=media.getvalue())
            )
            content = types.SimpleNamespace(parts=[part])
            return types.SimpleNamespace(
                candidates=[types.SimpleNamespace(content=content)]
            )

    fake_types = types.SimpleNamespace(
        GenerateContentConfig=FakeGenerateContentConfig,
        HttpOptions=FakeHttpOptions,
        HttpRetryOptions=FakeHttpRetryOptions,
    )
    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = FakeClient
    fake_genai.types = fake_types
    fake_google = types.ModuleType("google")
    fake_google.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project-fixture")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "global")

    output = tmp_path / "gemini.png"
    request = {
        "job": {"prompt": "a blue square", "seed": 17},
        "candidate": {
            "model": "gemini-3.1-flash-image",
            "settings": {
                "vertexai": True,
                "retry_attempts": 3,
                "retry_initial_delay_seconds": 10,
                "retry_max_delay_seconds": 30,
            },
        },
        "output": {"native_path": str(output)},
    }

    result = image_benchmark_runner.run_gemini(request)

    retry = captured["client"]["http_options"].retry_options.values
    assert output.is_file()
    assert captured["client"]["location"] == "global"
    assert retry["attempts"] == 3
    assert retry["initial_delay"] == 10
    assert retry["max_delay"] == 30
    assert retry["http_status_codes"] == [408, 429, 500, 502, 503, 504]
    assert result["provenance"]["retry_policy"] == retry


def test_mflux_z_image_uses_prequantized_checkpoint(tmp_path, monkeypatch):
    captured = {}

    class FakeModelConfig:
        @staticmethod
        def z_image_turbo():
            return "z-image-turbo-config"

    class FakeZImageTurbo:
        def __init__(self, **kwargs):
            captured["init"] = kwargs

        def generate_image(self, **kwargs):
            captured["generate"] = kwargs
            return types.SimpleNamespace(image=Image.new("RGB", (32, 32), "purple"))

    modules = {
        "mflux": types.ModuleType("mflux"),
        "mflux.models": types.ModuleType("mflux.models"),
        "mflux.models.common": types.ModuleType("mflux.models.common"),
        "mflux.models.common.config": types.ModuleType("mflux.models.common.config"),
        "mflux.models.common.config.model_config": types.ModuleType(
            "mflux.models.common.config.model_config"
        ),
        "mflux.models.z_image": types.ModuleType("mflux.models.z_image"),
    }
    modules["mflux.models.common.config.model_config"].ModelConfig = FakeModelConfig
    modules["mflux.models.z_image"].ZImageTurbo = FakeZImageTurbo
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    output = tmp_path / "z-image.png"
    request = {
        "job": {"prompt": "a purple square", "seed": 17},
        "candidate": {
            "model": "filipstrand/Z-Image-Turbo-mflux-4bit",
            "revision": None,
            "settings": {
                "width": 512,
                "height": 512,
                "steps": 9,
                "guidance": 0.0,
                "quantize": None,
            },
        },
        "output": {"native_path": str(output)},
    }

    result = image_benchmark_runner.run_mflux_z_image(request)

    assert output.is_file()
    assert captured["init"]["quantize"] is None
    assert captured["init"]["model_path"].endswith("mflux-4bit")
    assert captured["generate"]["num_inference_steps"] == 9
    assert result["provenance"]["prequantized"] is True
