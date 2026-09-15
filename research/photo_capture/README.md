# Photo-capture spike

Measures whether "photograph a page, tap a word, see its meaning in context" is fast and accurate
enough to build. The questions, thresholds and results are in
[`docs/plans/photo-capture.md`](../../docs/plans/photo-capture.md#spike-results). The photos and the
hand-written truth are in [`tests/fixtures/photo-capture/`](../../tests/fixtures/photo-capture/).

Nothing here ships. `pytest.ini` collects only `tests/`, so this directory's tests run only from its
own environment.

## Environment

Its own, so RapidOCR, OpenCV and SaT never enter the application's requirements:

```sh
cd research/photo_capture
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt --override overrides.txt
.venv/bin/python -m pytest -q test_spike.py
```

`overrides.txt` stops RapidOCR pulling in the GUI build of OpenCV next to the headless one.

Cloud Vision needs an untracked `.env` here naming which credentials it may spend:

```sh
PHOTO_SPIKE_ADC=/path/to/application_default_credentials.json
PHOTO_SPIKE_GCP_PROJECT=your-project-id
PHOTO_SPIKE_GCP_ACCOUNT=learner@account.example.com
```

A Vision call first asks Google whose token it holds, and refuses if the answer is not that
account, or if Google cannot say.

## Files

| File | Job |
| --- | --- |
| `engines.py` | Cloud Vision and RapidOCR, both reduced to one layout (words, polygons, lines, breaks). Every response is cached in `runs/cache/`, keyed by settings and image bytes. |
| `layout.py` | Rebuilds RapidOCR's fragments into lines, then joins words into one text with a character span per tappable token, joining hyphenation across lines. |
| `segment.py` | Three sentence splitters: rules, pySBD, SaT. |
| `hit.py` | A tap point to a token and its sentence. |
| `evaluate.py`, `score.py` | Alignment against the truth, tap placement, and every metric. |
| `quick_prompt.md`, `quick.py` | The tap → meaning call, through Acervo's own `llm_json`, one pinned model at a time. Runs in the application's `.venv`. |
| `bench_nas.py` | A self-contained RapidOCR timing script to copy to the server. |
| `spike.py` | `ocr`: fill the engine cache for every fixture and upload size. |
| `report.py` | Every table, from the cache only. |

## Rerunning

```sh
# OCR, cached; Vision costs one unit per image and variant (free for 1,000 a month)
.venv/bin/python spike.py ocr --engine vision
.venv/bin/python spike.py ocr --engine rapidocr --presets v5m-latin --box-thresh 0.5 0.3
.venv/bin/python spike.py ocr --engine rapidocr --presets v6s-det-v5-latin --box-thresh 0.3

# Tables, no network
.venv/bin/python report.py > runs/report.md

# The quick call, from the repository root, in the application environment
set -a; . ./.env; set +a
.venv/bin/python research/photo_capture/quick.py \
  --taps research/photo_capture/runs/taps-vision-full-2048-sat.json \
  --pair gemini-free:gemini/gemini-3.5-flash-lite --pace 4.5
```

`runs/taps-vision-full-2048-sat.json` is written by `score.py` when it scores Vision at 2048 px with
SaT; the quick call reads OCR'd sentences from it, so OCR damage is part of what the model sees.
The Gemini free tier allows 15 requests a minute per model, hence `--pace`.

On the NAS, `bench_nas.py` ran in a throwaway Python 3.12 that `uv` fetched into a temporary folder,
because DSM's Python is 3.8. No Docker, no sudo, and the folder was deleted afterwards.
