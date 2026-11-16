"""Environment-driven configuration for the Inventory Management System.

This module uses only the standard library so that configuration can be
validated (for example by the Docker entrypoint) before any database driver is
imported. Nothing in here ever logs or prints a secret value.
"""
import os
from dataclasses import dataclass, field
from typing import Mapping, Optional

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Amazon RDS CA bundle, downloaded into the image at build time (see Dockerfile).
DEFAULT_SSL_CA = os.path.join(BASE_DIR, "certs", "rds-global-bundle.pem")

SSL_MODES = ("verify-full", "disabled")


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _int(env: Mapping[str, str], name: str, default: int,
         minimum: int = 1, maximum: Optional[int] = None) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        raise ConfigError(f"{name} must be an integer.") from None
    if value < minimum or (maximum is not None and value > maximum):
        if maximum is not None:
            raise ConfigError(f"{name} must be between {minimum} and {maximum}.")
        raise ConfigError(f"{name} must be {minimum} or greater.")
    return value


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    name: str
    user: str
    password: str = field(repr=False)  # never shown in repr()/logs
    ssl_mode: str
    ssl_ca: str
    pool_size: int
    max_overflow: int
    pool_recycle: int
    pool_timeout: int
    connect_timeout: int
    read_timeout: int
    startup_attempts: int
    startup_delay: int

    def describe(self) -> str:
        """Safe, secret-free summary suitable for logs."""
        return (f"host={self.host} port={self.port} database={self.name} "
                f"user={self.user} ssl={self.ssl_mode}")


def load_database_config(env: Optional[Mapping[str, str]] = None) -> DatabaseConfig:
    env = os.environ if env is None else env

    missing = []
    for name in ("DB_HOST", "DB_NAME", "DB_USER"):
        if not (env.get(name) or "").strip():
            missing.append(name)
    if not env.get("DB_PASSWORD"):
        missing.append("DB_PASSWORD")
    if missing:
        raise ConfigError("Missing required database environment variable(s): "
                          + ", ".join(missing))

    host = env["DB_HOST"].strip()
    if "/" in host or any(ch.isspace() for ch in host) or "@" in host:
        raise ConfigError("DB_HOST must be a bare hostname (the RDS endpoint), not a URL.")

    ssl_mode = (env.get("DB_SSL_MODE") or "verify-full").strip().lower()
    if ssl_mode not in SSL_MODES:
        raise ConfigError("DB_SSL_MODE must be one of: " + ", ".join(SSL_MODES))

    ssl_ca = (env.get("DB_SSL_CA") or "").strip() or DEFAULT_SSL_CA
    if ssl_mode == "verify-full" and not os.path.isfile(ssl_ca):
        raise ConfigError(
            f"DB_SSL_CA file not found: {ssl_ca}. TLS certificate verification is "
            "enabled by default; provide the Amazon RDS CA bundle or, for a local "
            "development database only, set DB_SSL_MODE=disabled."
        )

    return DatabaseConfig(
        host=host,
        port=_int(env, "DB_PORT", 3306, 1, 65535),
        name=env["DB_NAME"].strip(),
        user=env["DB_USER"].strip(),
        password=env["DB_PASSWORD"],
        ssl_mode=ssl_mode,
        ssl_ca=ssl_ca,
        pool_size=_int(env, "DB_POOL_SIZE", 5, 1, 50),
        max_overflow=_int(env, "DB_MAX_OVERFLOW", 5, 0, 50),
        # Recycle connections well before any server/NAT idle timeout.
        pool_recycle=_int(env, "DB_POOL_RECYCLE", 1800, 30),
        pool_timeout=_int(env, "DB_POOL_TIMEOUT", 30, 1),
        connect_timeout=_int(env, "DB_CONNECT_TIMEOUT", 10, 1),
        read_timeout=_int(env, "DB_READ_TIMEOUT", 30, 1),
        startup_attempts=_int(env, "DB_STARTUP_ATTEMPTS", 12, 1),
        startup_delay=_int(env, "DB_STARTUP_DELAY", 5, 1),
    )


def load_secret_key(env: Optional[Mapping[str, str]] = None) -> str:
    env = os.environ if env is None else env
    key = env.get("SECRET_KEY", "")
    if not key:
        raise ConfigError("Missing required environment variable: SECRET_KEY")
    if len(key) < 16:
        raise ConfigError("SECRET_KEY must be at least 16 characters long.")
    return key


def cookie_secure(env: Optional[Mapping[str, str]] = None) -> bool:
    env = os.environ if env is None else env
    return env.get("COOKIE_SECURE", "0") == "1"


def validate_all(env: Optional[Mapping[str, str]] = None):
    """Validate every setting the application needs. Returns (db_config, secret_key)."""
    return load_database_config(env), load_secret_key(env)
