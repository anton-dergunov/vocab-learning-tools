FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ACERVO_DB_PATH=/var/lib/acervo/server/acervo.db \
    ACERVO_WEB_PATH=/app/web \
    ACERVO_PROMPTS_PATH=/app/prompts \
    ACERVO_DOWNLOADS_PATH=/var/lib/acervo/downloads \
    ACERVO_DICTIONARIES_PATH=/var/lib/acervo/dictionaries

WORKDIR /app

COPY requirements /app/requirements
RUN pip install --no-cache-dir -r requirements/server.txt

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
# The built interface. `.dockerignore` excludes `web/dist`, so `scripts/stage-web.sh` is what puts it
# somewhere a build context can see.
COPY deploy/acervo/server/web /app/web

RUN mkdir -p /var/lib/acervo/server /var/lib/acervo/downloads /var/lib/acervo/dictionaries \
    && chmod -R a+rX /app \
    && chmod -R a+rwX /var/lib/acervo

EXPOSE 8000
CMD ["python", "-m", "acervo.admin", "serve", "--host", "0.0.0.0", "--port", "8000"]
