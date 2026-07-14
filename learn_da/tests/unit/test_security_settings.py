import pytest
from pydantic import ValidationError

from config.settings import Settings


def production_settings(**overrides):
    values = {
        "APP_ENV": "production",
        "CORS_ORIGINS": "https://learn.example.com",
        "RUNNER_URL": "http://runner:8080",
        "RUNNER_TOKEN": "r" * 32,
        "SESSION_SECRET": "s" * 32,
        "SANDBOX_LOCAL_ENABLED": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_accepts_complete_runner_and_session_configuration():
    settings = production_settings()

    assert settings.RUNNER_URL == "http://runner:8080"
    assert settings.RUNNER_TOKEN == "r" * 32
    assert settings.SESSION_SECRET == "s" * 32


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"RUNNER_URL": ""}, "RUNNER_URL is required in production"),
        ({"RUNNER_TOKEN": "r" * 31}, "RUNNER_TOKEN must contain at least 32 characters"),
        (
            {"SESSION_SECRET": "s" * 31},
            "SESSION_SECRET must contain at least 32 characters",
        ),
    ],
)
def test_production_requires_runner_and_session_secrets(overrides, message):
    with pytest.raises(ValidationError, match=message):
        production_settings(**overrides)


def test_production_rejects_local_execution():
    with pytest.raises(
        ValidationError,
        match="SANDBOX_LOCAL_ENABLED must be false in production",
    ):
        production_settings(SANDBOX_LOCAL_ENABLED=True)
