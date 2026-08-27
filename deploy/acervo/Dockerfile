FROM python:3.12-slim-bookworm

ARG ANKI_VERSION=26.8.1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

RUN python -m pip install --no-cache-dir \
    "anki==${ANKI_VERSION}" \
    "pydantic>=2,<3" \
    "python-slugify>=8,<9"

WORKDIR /app
COPY src /app/src
COPY scripts/anki_robot.py /app/scripts/anki_robot.py
COPY scripts/integration/anki_sync_client.py /app/scripts/integration/anki_sync_client.py
COPY templates /app/templates

RUN mkdir -p /var/lib/acervo/anki-server /var/lib/acervo/anki-robot /input

EXPOSE 8080
