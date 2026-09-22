FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ACERVO_DB_PATH=/var/lib/acervo/server/acervo.db \
    ACERVO_WEB_PATH=/app/web \
    ACERVO_PROMPTS_PATH=/app/prompts \
    ACERVO_DOWNLOADS_PATH=/var/lib/acervo/downloads \
    ACERVO_DICTIONARIES_PATH=/var/lib/acervo/dictionaries

WORKDIR /app

# The meaning map's encoder runs on torch, and the default wheel carries CUDA libraries a NAS has no
# use for; the CPU-only build is a fraction of the size, so it goes in first and the requirements
# below find it already satisfied.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch

COPY requirements /app/requirements
RUN pip install --no-cache-dir -r requirements/server.txt

# The encoder's weights, at the revision `models/encoder.json` pins, fetched once at build time and
# before `src` is copied, so a code change never downloads them again. Only the files
# sentence-transformers reads: the repository also carries ONNX and OpenVINO copies nobody here uses.
# At run time the library is told it is offline, so drawing a map never reaches the network.
ENV HF_HOME=/opt/huggingface
COPY models/encoder.json /app/models/encoder.json
RUN python -c "import json; from huggingface_hub import snapshot_download; \
pin = json.load(open('/app/models/encoder.json')); \
snapshot_download(pin['model'], revision=pin['revision'], allow_patterns=pin['files'])" \
    && chmod -R a+rX /opt/huggingface
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    NUMBA_CACHE_DIR=/tmp/numba

COPY pyproject.toml /app/pyproject.toml
COPY README.md /app/README.md
COPY src /app/src
# The provider catalogue, beside `src` the way `dictionaries/` is: the package resolves it
# relative to itself, so it needs no environment variable and no staging step.
COPY models /app/models
RUN pip install --no-cache-dir --no-deps -e /app

# The capture prompts are content, not code: tracked once at the repository root and read at request
# time, so changing what an entry says never means changing the code that builds a request.
COPY prompts /app/prompts
# The style table is content of the same kind, and `acervo.images.styles` resolves it relative to
# the package exactly as the two catalogues above do — hence the matching path rather than a third
# environment variable.
COPY config/image-styles.yaml /app/config/image-styles.yaml
COPY config/story-types.yaml /app/config/story-types.yaml
# The built interface. `.dockerignore` excludes `web/dist`, so `scripts/stage-web.sh` is what puts it
# somewhere a build context can see.
COPY deploy/acervo/server/web /app/web

RUN mkdir -p /var/lib/acervo/server /var/lib/acervo/downloads /var/lib/acervo/dictionaries \
    && chmod -R a+rX /app \
    && chmod -R a+rwX /var/lib/acervo

EXPOSE 8000
CMD ["python", "-m", "acervo.admin", "serve", "--host", "0.0.0.0", "--port", "8000"]
