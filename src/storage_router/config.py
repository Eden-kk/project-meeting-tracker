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
    voice_ingest_url: str = Field(
        default="http://127.0.0.1:8021",
        validation_alias="VOICE_INGEST_URL",
    )
    transcript_ingest_url: str = Field(
        default="http://127.0.0.1:8011",
        validation_alias="TRANSCRIPT_INGEST_URL",
    )
    # Whisper on CPU is roughly 1x real-time; 1800s headroom covers ~30 min clips.
    voice_ingest_timeout_seconds: float = Field(
        default=1800.0,
        validation_alias="VOICE_INGEST_TIMEOUT_SECONDS",
    )
    # Transcript parsing is sub-second; 30s is a generous ceiling for retries/network.
    transcript_ingest_timeout_seconds: float = Field(
        default=30.0,
        validation_alias="TRANSCRIPT_INGEST_TIMEOUT_SECONDS",
    )

    # Zoom Marketplace credentials (Wave 9). All default to empty string —
    # the SPA must continue to load when these are absent. The
    # zoom_bot_dispatcher._require_zoom_creds() helper raises a
    # 503-mapped RuntimeError at dispatch / JWT-sign time when any of
    # the four credentials are missing.
    zoom_sdk_key: str = Field(default="", validation_alias="ZOOM_SDK_KEY")
    zoom_sdk_secret: str = Field(default="", validation_alias="ZOOM_SDK_SECRET")
    zoom_oauth_client_id: str = Field(
        default="", validation_alias="ZOOM_OAUTH_CLIENT_ID"
    )
    zoom_oauth_client_secret: str = Field(
        default="", validation_alias="ZOOM_OAUTH_CLIENT_SECRET"
    )
    # Informational only — the dedicated bot account's email is shown as
    # the bot's profile/display-name. NOT used for authentication.
    zoom_bot_account_email: str = Field(
        default="", validation_alias="ZOOM_BOT_ACCOUNT_EMAIL"
    )
    # Cap on concurrent bot subprocesses on this pod.
    zoom_bot_pool_size: int = Field(
        default=3, validation_alias="ZOOM_BOT_POOL_SIZE"
    )
    # Directory hosting bot.py + zoom-bot.js + zoom-host.html.
    zoom_bot_dir: Path = Field(
        default=_ROOT / "bot",
        validation_alias="ZOOM_BOT_DIR",
    )


settings = Settings()
