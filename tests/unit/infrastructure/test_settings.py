import pytest

from small_service.infrastructure.settings import ConfigurationError, Settings

BASE = {"POSTGRES_PASSWORD": "pw"}


def test_defaults_apply_when_only_the_password_is_set():
    settings = Settings.from_env(BASE)
    assert (settings.postgres_host, settings.postgres_port, settings.cache_ttl_seconds) == ("localhost", 5432, 30)


def test_the_password_has_no_default():
    with pytest.raises(ConfigurationError, match="POSTGRES_PASSWORD"):
        Settings.from_env({})


def test_the_connection_uri_escapes_special_characters():
    settings = Settings.from_env({"POSTGRES_PASSWORD": "p@ss/word", "POSTGRES_USER": "me"})
    assert settings.dsn == "postgresql://me:p%40ss%2Fword@localhost:5432/service"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("POSTGRES_PORT", "0"),
        ("POSTGRES_PORT", "70000"),
        ("POSTGRES_PORT", "5432.5"),
        ("POSTGRES_PORT", "abc"),
        ("POSTGRES_HOST", "bad host"),
        ("LOG_LEVEL", "LOUD"),
        ("CACHE_TTL_SECONDS", "-1"),
        ("JOB_TIMEOUT_SECONDS", "0"),
    ],
)
def test_an_unusable_value_names_its_variable(name, value):
    with pytest.raises(ConfigurationError, match=name):
        Settings.from_env({**BASE, name: value})


def test_the_log_level_is_case_insensitive():
    assert Settings.from_env({**BASE, "LOG_LEVEL": "debug"}).log_level == "DEBUG"
