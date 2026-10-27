"""Application settings loaded from environment variables prefixed with ``YV_``."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="YV_",
        env_file=REPOSITORY_ROOT / ".env",
        extra="ignore",
    )

    data_dir: Path = REPOSITORY_ROOT / "data"
    database_url: str | None = None
    frontend_dist_dir: Path = REPOSITORY_ROOT / "frontend" / "dist"

    host: str = "127.0.0.1"
    port: int = 8100

    hf_token: str | None = None
    runtime_host: str = "127.0.0.1"
    runtime_stop_timeout_seconds: int = 15

    agent_max_iterations: int = 60
    tool_output_limit: int = 20_000
    document_character_limit: int = 200_000

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'your_voice.db').as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
