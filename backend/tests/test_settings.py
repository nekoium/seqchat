from __future__ import annotations

from pathlib import Path

import pytest

from seqchat.settings import ENV_FILE, PROJECT_ROOT, Settings


def configured(**overrides: str) -> Settings:
    values = {
        "llm_base_url": "https://provider.example/v1",
        "llm_api_key": "test-key",
        "llm_model": "arbitrary-model",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize("model", ["arbitrary-model", "gpt-5.6-luna"])
def test_accepts_any_nonblank_model_identifier(model: str) -> None:
    assert configured(llm_model=model).provider_is_configured


@pytest.mark.parametrize("field", ["llm_base_url", "llm_api_key", "llm_model"])
@pytest.mark.parametrize("value", ["", "   \t"])
def test_missing_or_whitespace_provider_values_are_not_configured(field: str, value: str) -> None:
    settings = configured(**{field: value})
    assert not settings.provider_is_configured
    assert settings.provider_configuration_error == "model_not_configured"
    assert getattr(settings, field) == ""


@pytest.mark.parametrize(
    "overrides",
    [
        {"llm_base_url": "", "llm_api_key": ""},
        {"llm_api_key": "", "llm_model": ""},
        {"llm_base_url": "", "llm_model": ""},
        {"llm_base_url": "", "llm_api_key": "", "llm_model": ""},
    ],
)
def test_incomplete_provider_combinations_are_rejected(overrides: dict[str, str]) -> None:
    assert not configured(**overrides).provider_is_configured


def test_default_env_file_is_anchored_at_repository_root() -> None:
    assert ENV_FILE == PROJECT_ROOT / ".env"


def test_loads_env_file_and_process_environment_overrides_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SEQCHAT_LLM_BASE_URL=https://file.example/v1\n"
        "SEQCHAT_LLM_API_KEY=file-key\n"
        "SEQCHAT_LLM_MODEL=file-model\n"
        "SEQCHAT_LLM_JSON_MODE=true\n",
        encoding="utf-8",
    )
    other_working_directory = tmp_path / "other"
    other_working_directory.mkdir()
    monkeypatch.chdir(other_working_directory)
    monkeypatch.setenv("SEQCHAT_LLM_MODEL", "environment-model")
    settings = Settings(_env_file=env_file)
    assert settings.llm_base_url == "https://file.example/v1"
    assert settings.llm_api_key == "file-key"
    assert settings.llm_model == "environment-model"
    assert settings.llm_json_mode is True
