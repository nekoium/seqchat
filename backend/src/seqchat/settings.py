from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SEQCHAT_", extra="ignore")

    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    database_path: Path = Field(default=PROJECT_ROOT / "data" / "seqchat.duckdb")
    frontend_origin: str = "http://localhost:5173"

    @property
    def provider_is_configured(self) -> bool:
        return bool(
            self.llm_base_url
            and self.llm_api_key
            and self.llm_model == "gpt-5.6-luna"
        )
