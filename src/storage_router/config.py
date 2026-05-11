"""Settings loaded from env + .env.local (auto-loaded if present)."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env.local from the worktree root so plain `python -c` invocations
# pick up the managed-Postgres DSN without an explicit shell source step.
_ROOT = Path(__file__).resolve().parents[2]
_ENV_LOCAL = _ROOT / ".env.local"
if _ENV_LOCAL.exists():
    load_dotenv(_ENV_LOCAL)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg://tracker:tracker@localhost:5433/tracker",
        validation_alias="DATABASE_URL",
    )
    blob_store_dir: Path = Field(
        default=Path("./var/blobs"),
        validation_alias="BLOB_STORE_DIR",
    )
    ingest_backend: str = Field(
        default="stub",
        validation_alias="INGEST_BACKEND",
    )


settings = Settings()
