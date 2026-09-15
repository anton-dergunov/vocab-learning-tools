#!/usr/bin/env python3
"""Step 6: how long RapidOCR takes on the machine that would serve it.

Self-contained on purpose: it is copied to the server with a folder of prepared JPEGs and run in a
throwaway virtualenv, so it imports nothing from the spike or from Acervo.

    python bench_nas.py --images DIR --threads 1 2 4 --repeat 3 > bench.json
"""

from __future__ import annotations

import argparse
import json
import platform
import resource
import statistics
import time
from pathlib import Path

PRESETS = {
    "v5m-latin": ("PP-OCRv5", "mobile", "PP-OCRv5", "latin", "mobile"),
    "v6s-det-v5-latin": ("PP-OCRv6", "small", "PP-OCRv5", "latin", "mobile"),
}


def engine(preset: str, threads: int, box_thresh: float):
    from rapidocr import LangDet, LangRec, ModelType, OCRVersion, RapidOCR

    det_version, det_size, rec_version, rec_lang, rec_size = PRESETS[preset]
    return RapidOCR(params={
        "Global.use_cls": False,
        "Global.text_score": 0.5,
        "Global.log_level": "error",
        "Global.max_side_len": 10000,
        "Det.lang_type": LangDet.CH,
        "Det.ocr_version": OCRVersion(det_version),
        "Det.model_type": ModelType(det_size),
        "Det.limit_side_len": 10000,
        "Det.limit_type": "max",
        "Det.box_thresh": box_thresh,
        "Rec.lang_type": LangRec(rec_lang),
        "Rec.ocr_version": OCRVersion(rec_version),
        "Rec.model_type": ModelType(rec_size),
        "EngineConfig.onnxruntime.intra_op_num_threads": threads,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
    })


def main() -> None:
    import cv2

    parser = argparse.ArgumentParser()
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--presets", nargs="+", default=list(PRESETS))
    parser.add_argument("--threads", nargs="+", type=int, default=[1, 2, 4])
    parser.add_argument("--box-thresh", type=float, default=0.3)
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()

    files = sorted(args.images.glob("*.jpg"))
    images = {f.name: cv2.imread(str(f)) for f in files}
    result = {"machine": platform.machine(), "processor": platform.processor(),
              "cpus": __import__("os").cpu_count(), "runs": []}
    try:
        result["cpuModel"] = next(line.split(":", 1)[1].strip()
                                  for line in open("/proc/cpuinfo") if line.startswith("model name"))
    except (OSError, StopIteration):
        pass

    for preset in args.presets:
        for threads in args.threads:
            started = time.perf_counter()
            ocr = engine(preset, threads, args.box_thresh)
            load_s = time.perf_counter() - started
            ocr(images[files[0].name])  # warm-up: first call pays for graph optimisation
            for name, image in images.items():
                timings = []
                for _ in range(args.repeat):
                    t = time.perf_counter()
                    ocr(image, return_word_box=True)
                    timings.append(time.perf_counter() - t)
                result["runs"].append({"preset": preset, "threads": threads, "image": name,
                                       "loadSeconds": round(load_s, 2),
                                       "median": round(statistics.median(timings), 3),
                                       "all": [round(t, 3) for t in timings]})
                print(f"{preset:18} t{threads} {name:28} {statistics.median(timings):6.2f}s",
                      file=__import__("sys").stderr, flush=True)
    result["peakRssMb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
