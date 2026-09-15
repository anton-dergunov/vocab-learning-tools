"""Two OCR engines, one page layout.

Both engines are reduced to the same shape, so everything downstream (layout, segmentation, hit
testing, scoring) cannot tell which one read the page:

    {"engine": ..., "width": w, "height": h,
     "words": [{"text", "confidence", "polygon": [[x, y] * 4] (0..1), "line": int,
                "break": "space" | "eol" | "hyphen" | None}],
     "timing": {...}}

`break` is what follows the word. Cloud Vision reports it (`detectedBreak`); RapidOCR does not, so
for it the end of each detected line is `eol` and a trailing hyphen becomes `hyphen` in `layout.py`.

Every engine response is cached by (engine, settings, image bytes), so a rerun of any later step
spends nothing and a report can be rebuilt offline.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
CACHE = HERE / "runs" / "cache"


# ── Images ────────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Variant:
    """How the device would prepare a photo before sending it."""

    crop: str  # "full" | "centre"
    long_edge: int | None  # None keeps the original size

    @property
    def name(self) -> str:
        return f"{self.crop}-{self.long_edge or 'orig'}"


def centre_box(width: int, height: int) -> tuple[int, int, int, int]:
    """The square centre crop, as (x0, y0, x1, y1) in original pixels.

    Square because the capture screen keeps the lower part free for the sheet: the frame the owner
    sees and aims with is this square, not the whole sensor.
    """
    side = min(width, height)
    x0 = (width - side) // 2
    y0 = (height - side) // 2
    return x0, y0, x0 + side, y0 + side


def prepare(path: Path, variant: Variant) -> tuple[bytes, tuple[int, int, int, int], float]:
    """Encode a fixture the way the device would. Returns (jpeg, crop box in original px, scale)."""
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    height, width = image.shape[:2]
    box = (0, 0, width, height) if variant.crop == "full" else centre_box(width, height)
    image = image[box[1]:box[3], box[0]:box[2]]
    scale = 1.0
    if variant.long_edge:
        longest = max(image.shape[:2])
        if longest > variant.long_edge:
            scale = variant.long_edge / longest
            image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
    assert ok
    return encoded.tobytes(), box, scale


def _cache_path(engine: str, settings: dict[str, Any], data: bytes) -> Path:
    key = hashlib.sha256(json.dumps(settings, sort_keys=True).encode() + data).hexdigest()[:24]
    return CACHE / engine / f"{key}.json"


def _normalise(polygon: list[list[float]], width: int, height: int) -> list[list[float]]:
    return [[round(x / width, 5), round(y / height, 5)] for x, y in polygon]


# ── RapidOCR ──────────────────────────────────────────────────────────────────────────────────────

_ENGINES: dict[tuple, Any] = {}

# Model combinations worth comparing. v5 "latin" is the recognition model info-triage's choice would
# become for Spanish; v6 is RapidOCR's own default family, multilingual in one model.
PRESETS: dict[str, dict[str, str]] = {
    "v5m-latin": {"det": "PP-OCRv5/ch/mobile", "rec": "PP-OCRv5/latin/mobile"},
    "v6s": {"det": "PP-OCRv6/ch/small", "rec": "PP-OCRv6/ch/small"},
    "v6m": {"det": "PP-OCRv6/ch/medium", "rec": "PP-OCRv6/ch/medium"},
    "v6s-det-v5-latin": {"det": "PP-OCRv6/ch/small", "rec": "PP-OCRv5/latin/mobile"},
}


def _rapidocr(preset: str, box_thresh: float, threads: int | None):
    key = (preset, box_thresh, threads)
    if key not in _ENGINES:
        from rapidocr import LangDet, LangRec, ModelType, OCRVersion, RapidOCR

        def parts(spec: str):
            version, lang, size = spec.split("/")
            return OCRVersion(version), lang, ModelType(size)

        det_version, det_lang, det_size = parts(PRESETS[preset]["det"])
        rec_version, rec_lang, rec_size = parts(PRESETS[preset]["rec"])
        params: dict[str, Any] = {
            "Global.use_cls": False,
            "Global.text_score": 0.5,
            "Global.log_level": "error",
            # RapidOCR silently shrinks every image to 2000 px on its longest side before detection
            # (Global.max_side_len). Lifted, so the size the device sends is the size that is read,
            # and the detector sees the whole image rather than its own downscaled copy.
            "Global.max_side_len": 10000,
            "Det.lang_type": LangDet(det_lang),
            "Det.ocr_version": det_version,
            "Det.model_type": det_size,
            "Det.limit_side_len": 10000,
            "Det.limit_type": "max",
            "Det.box_thresh": box_thresh,
            "Rec.lang_type": LangRec(rec_lang),
            "Rec.ocr_version": rec_version,
            "Rec.model_type": rec_size,
        }
        if threads:
            params["EngineConfig.onnxruntime.intra_op_num_threads"] = threads
            params["EngineConfig.onnxruntime.inter_op_num_threads"] = 1
        _ENGINES[key] = RapidOCR(params=params)
    return _ENGINES[key]


def rapidocr_read(data: bytes, preset: str = "v5m-latin", box_thresh: float = 0.5,
                  threads: int | None = None, use_cache: bool = True) -> dict[str, Any]:
    settings = {"preset": PRESETS[preset], "box_thresh": box_thresh, "max_side": "unlimited"}
    cached = _cache_path("rapidocr", settings, data)
    if use_cache and cached.exists():
        return json.loads(cached.read_text())

    engine = _rapidocr(preset, box_thresh, threads)
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    height, width = image.shape[:2]
    started = time.perf_counter()
    result = engine(image, return_word_box=True)
    elapsed = time.perf_counter() - started

    words = []
    lines = result.word_results if result.txts is not None else ()
    for line_index, line in enumerate(lines):
        for word_index, (text, score, box) in enumerate(line):
            if not text.strip() or box is None:
                continue
            words.append({
                "text": text,
                "confidence": float(score),
                "polygon": _normalise(box, width, height),
                "line": line_index,
                "break": "eol" if word_index == len(line) - 1 else "space",
            })
    layout = {
        "engine": f"rapidocr-{preset}" + (f"-box{box_thresh}" if box_thresh != 0.5 else ""),
        "width": width,
        "height": height,
        "words": words,
        "timing": {"ocr_s": round(elapsed, 3), "bytes": len(data)},
    }
    if use_cache:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(layout, ensure_ascii=False))
    return layout


# ── Cloud Vision ──────────────────────────────────────────────────────────────────────────────────

_SESSION: dict[str, Any] = {}


def load_env() -> None:
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                name, value = line.split("=", 1)
                os.environ.setdefault(name.strip(), value.strip())


def vision_credentials():
    """A token from exactly the named ADC file, proven to belong to the named account.

    Half a guard is not one: if tokeninfo cannot say whose token this is, the call is refused rather
    than made on the assumption that it is probably the right login.
    """
    if "token" in _SESSION and _SESSION["expiry"] > time.time() + 60:
        return _SESSION["token"], _SESSION["project"]
    load_env()
    adc = os.environ.get("PHOTO_SPIKE_ADC")
    project = os.environ.get("PHOTO_SPIKE_GCP_PROJECT")
    account = os.environ.get("PHOTO_SPIKE_GCP_ACCOUNT")
    if not (adc and project and account):
        raise SystemExit("Set PHOTO_SPIKE_ADC, PHOTO_SPIKE_GCP_PROJECT and PHOTO_SPIKE_GCP_ACCOUNT "
                         "(experiments/photo-capture/.env) before calling Cloud Vision.")
    import google.auth.exceptions
    import google.auth.transport.requests
    import requests
    from google.oauth2 import credentials as user_credentials
    from google.oauth2 import service_account

    info = json.loads(Path(adc).read_text())
    scopes = ["https://www.googleapis.com/auth/cloud-platform",
              "https://www.googleapis.com/auth/userinfo.email"]
    if info.get("type") == "service_account":
        creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    else:
        creds = user_credentials.Credentials.from_authorized_user_info(info)
    try:
        creds.refresh(google.auth.transport.requests.Request())
    except google.auth.exceptions.RefreshError as error:
        raise SystemExit(f"Those Google credentials need signing in again ({error}). "
                         "Refresh the file named by PHOTO_SPIKE_ADC, e.g. with `gcp login <profile>`.")

    who = requests.get("https://oauth2.googleapis.com/tokeninfo",
                       params={"access_token": creds.token}, timeout=10)
    email = who.json().get("email") if who.ok else None
    if email is None:
        raise SystemExit("Refusing to call Cloud Vision: these credentials cannot prove whose they are.")
    if email.lower() != account.lower():
        raise SystemExit("Refusing to call Cloud Vision: the credentials belong to a different "
                         "account than PHOTO_SPIKE_GCP_ACCOUNT.")
    _SESSION.update(token=creds.token, project=project,
                    expiry=creds.expiry.timestamp() if creds.expiry else time.time() + 1800)
    return creds.token, project


_BREAKS = {"SPACE": "space", "SURE_SPACE": "space", "EOL_SURE_SPACE": "eol",
           "LINE_BREAK": "eol", "HYPHEN": "hyphen"}


def vision_read(data: bytes, use_cache: bool = True) -> dict[str, Any]:
    settings = {"feature": "DOCUMENT_TEXT_DETECTION", "hints": ["es"]}
    cached = _cache_path("vision", settings, data)
    if use_cache and cached.exists():
        return json.loads(cached.read_text())

    import requests

    token, project = vision_credentials()
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    height, width = image.shape[:2]
    body = {"requests": [{
        "image": {"content": base64.b64encode(data).decode()},
        "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
        "imageContext": {"languageHints": ["es"]},
    }]}
    started = time.perf_counter()
    response = requests.post(
        "https://vision.googleapis.com/v1/images:annotate",
        headers={"Authorization": f"Bearer {token}", "x-goog-user-project": project},
        json=body, timeout=60,
    )
    elapsed = time.perf_counter() - started
    response.raise_for_status()
    answer = response.json()["responses"][0]
    if "error" in answer:
        raise RuntimeError(answer["error"])

    words = []
    line = 0
    annotation = answer.get("fullTextAnnotation", {})
    for page in annotation.get("pages", []):
        for block in page.get("blocks", []):
            for paragraph in block.get("paragraphs", []):
                for word in paragraph.get("words", []):
                    symbols = word.get("symbols", [])
                    text = "".join(symbol.get("text", "") for symbol in symbols)
                    last = symbols[-1].get("property", {}) if symbols else {}
                    kind = last.get("detectedBreak", {}).get("type")
                    vertices = [[v.get("x", 0), v.get("y", 0)]
                                for v in word.get("boundingBox", {}).get("vertices", [])]
                    words.append({
                        "text": text,
                        "confidence": float(word.get("confidence", 0.0)),
                        "polygon": _normalise(vertices, width, height),
                        "line": line,
                        "break": _BREAKS.get(kind),
                    })
                    if _BREAKS.get(kind) in ("eol", "hyphen"):
                        line += 1
                line += 1  # a paragraph always ends a line
    layout = {
        "engine": "vision",
        "width": width,
        "height": height,
        "words": words,
        "language": (annotation.get("pages") or [{}])[0].get("property", {})
        .get("detectedLanguages", [{}])[0].get("languageCode"),
        "timing": {"roundtrip_s": round(elapsed, 3), "bytes": len(data)},
    }
    if use_cache:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(layout, ensure_ascii=False))
    return layout
