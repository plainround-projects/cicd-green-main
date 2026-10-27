"""Configuration from the environment, validated once at startup (twelve-factor)."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import quote

_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}
_HOST = re.compile(r"^[\w.\-]+$")


class ConfigurationError(ValueError):
    """An environment variable is missing or has an unusable value."""


def _text(environ: Mapping[str, str], name: str, default: str | None = None) -> str:
    value = environ.get(name, default if default is not None else "").strip()
    if not value:
        raise ConfigurationError(f"{name} must be set and not empty")
    return value


def _positive_number(environ: Mapping[str, str], name: str, default: float) -> float:
    raw = environ.get(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError:
        raise ConfigurationError(f"{name} must be a number, got {raw!r}") from None
    if value <= 0:
        raise ConfigurationError(f"{name} must be positive, got {raw!r}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything the programs read from the environment. See .env.example for each variable."""

    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    log_level: str
    cache_ttl_seconds: float
    job_timeout_seconds: float

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """Read and validate. The password has no default: it must come from the environment."""
        env = os.environ if environ is None else environ
        host = _text(env, "POSTGRES_HOST", "localhost")
        if not _HOST.match(host):
            raise ConfigurationError(f"POSTGRES_HOST must be a host name or address, got {host!r}")
        port = _positive_number(env, "POSTGRES_PORT", 5432)
        if port != int(port) or port > 65535:
            raise ConfigurationError(f"POSTGRES_PORT must be a port number, got {port}")
        level = _text(env, "LOG_LEVEL", "INFO").upper()
        if level not in _LEVELS:
            raise ConfigurationError(f"LOG_LEVEL must be one of {sorted(_LEVELS)}, got {level!r}")
        return cls(
            postgres_host=host,
            postgres_port=int(port),
            postgres_db=_text(env, "POSTGRES_DB", "service"),
            postgres_user=_text(env, "POSTGRES_USER", "service"),
            postgres_password=_text(env, "POSTGRES_PASSWORD"),
            log_level=level,
            cache_ttl_seconds=_positive_number(env, "CACHE_TTL_SECONDS", 30),
            job_timeout_seconds=_positive_number(env, "JOB_TIMEOUT_SECONDS", 5),
        )

    @property
    def dsn(self) -> str:
        """A libpq connection URI. Never log this: it holds the password."""
        return (
            f"postgresql://{quote(self.postgres_user, safe='')}:{quote(self.postgres_password, safe='')}"
            f"@{self.postgres_host}:{self.postgres_port}/{quote(self.postgres_db, safe='')}"
        )
