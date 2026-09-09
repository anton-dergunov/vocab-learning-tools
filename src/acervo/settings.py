"""The one place the environment is read.

Deliberately not cached. `llmSettings()` in the hook this replaces re-read the environment on every
request, and several behaviours depend on that: health reports what the server is configured with
*now*, and the tests flip a variable between two calls to the same process. A module-level cache
would turn both into stale answers.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Bumped when the wire model changes shape. Declared here for the server, in `web/src/api.ts` for the
# interface, and in the two scripts that speak this API; a mismatch is a 409 by design.
SCHEMA_VERSION = 6

DEFAULT_LLM_MODEL = "gemini-3.1-flash-lite"
DEFAULT_GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com"


class Settings(BaseSettings):
    """Everything the service reads from its environment, and nothing it reads from anywhere else."""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    app_version: str = Field(default="0.0.0", alias="ACERVO_APP_VERSION")
    app_build: str = Field(default="0", alias="ACERVO_APP_BUILD")

    database_path: Path = Field(default=Path("/var/lib/acervo/server/acervo.db"), alias="ACERVO_DB_PATH")
    # Empty means "mint one beside the database and keep it": a restart must not sign everyone out,
    # and a local run must not need configuring.
    jwt_secret: str = Field(default="", alias="ACERVO_JWT_SECRET")

    web_path: Path = Field(default=Path("/app/web"), alias="ACERVO_WEB_PATH")
    downloads_path: Path = Field(default=Path("/var/lib/acervo/downloads"), alias="ACERVO_DOWNLOADS_PATH")
    dictionaries_path: Path = Field(default=Path("/var/lib/acervo/dictionaries"), alias="ACERVO_DICTIONARIES_PATH")
    prompts_path: Path = Field(default=Path("/app/prompts"), alias="ACERVO_PROMPTS_PATH")

    llm_provider: str = Field(default="gemini", alias="ACERVO_LLM_PROVIDER")
    llm_model: str = Field(default=DEFAULT_LLM_MODEL, alias="ACERVO_LLM_MODEL")
    # A test seam for the disposable integration server. It redirects the Gemini path only: Vertex
    # always uses Google's full project/location endpoint and cannot be pointed elsewhere.
    llm_endpoint: str = Field(default=DEFAULT_GEMINI_ENDPOINT, alias="ACERVO_LLM_ENDPOINT")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    vertex_api_key: str = Field(default="", alias="VERTEX_API_KEY")
    vertex_project: str = Field(default="", alias="ACERVO_VERTEX_PROJECT")
    vertex_location: str = Field(default="global", alias="ACERVO_VERTEX_LOCATION")

    # PocketBase allowed every origin by default and FastAPI sends nothing. The macOS host loads its
    # interface from `acervo://app` and calls the server cross-origin with headers that trigger a
    # preflight, so a missing header here fails every call inside the browser with no server-side log.
    cors_origins: str = Field(default="*", alias="ACERVO_CORS_ORIGINS")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


def settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
