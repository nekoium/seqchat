from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"
_PROVIDER_FIELDS = ("llm_base_url", "llm_api_key", "llm_model")


class ProviderConfigurationError(ValueError):
    """The provider configuration cannot form a supported request."""


def normalize_chat_completions_base_url(value: str) -> str:
    """Validate and normalize an HTTP(S) base URL without the endpoint suffix."""
    stripped = value.strip().rstrip("/")
    try:
        parsed = urlsplit(stripped)
    except ValueError as error:
        raise ProviderConfigurationError("The provider base URL is malformed") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ProviderConfigurationError("The provider base URL must be a plain HTTP(S) URL")
    path_parts = [part.casefold() for part in unquote(parsed.path).split("/") if part]
    for index in range(len(path_parts) - 1):
        if path_parts[index : index + 2] == ["chat", "completions"]:
            raise ProviderConfigurationError(
                "The provider base URL must not include /chat/completions"
            )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SEQCHAT_",
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_json_mode: bool = False
    database_path: Path = Field(default=PROJECT_ROOT / "data" / "seqchat.duckdb")
    frontend_origin: str = "http://localhost:5173"

    @field_validator("llm_base_url", "llm_api_key", "llm_model", mode="before")
    @classmethod
    def strip_provider_values(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @property
    def missing_provider_settings(self) -> tuple[str, ...]:
        return tuple(
            f"SEQCHAT_{name.removeprefix('llm_').upper()}"
            for name in _PROVIDER_FIELDS
            if not getattr(self, name)
        )

    @property
    def provider_configuration_error(self) -> str | None:
        if self.missing_provider_settings:
            return "model_not_configured"
        try:
            normalize_chat_completions_base_url(self.llm_base_url)
        except ProviderConfigurationError:
            return "model_configuration_invalid"
        return None

    @property
    def provider_is_configured(self) -> bool:
        return self.provider_configuration_error is None
