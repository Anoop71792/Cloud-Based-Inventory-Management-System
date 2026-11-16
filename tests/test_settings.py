"""Configuration tests. These need no database server."""
import pytest

import settings

GOOD = {
    "DB_HOST": "mydb.abc123.ap-south-1.rds.amazonaws.com",
    "DB_NAME": "inventorydb",
    "DB_USER": "inventoryuser",
    "DB_PASSWORD": "s3cret-value",
    "DB_SSL_MODE": "disabled",
}


def test_valid_config_applies_defaults():
    cfg = settings.load_database_config(GOOD)
    assert cfg.port == 3306
    assert cfg.pool_size == 5
    assert cfg.ssl_mode == "disabled"


@pytest.mark.parametrize("missing", ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"])
def test_missing_variable_is_reported_without_values(missing):
    env = {k: v for k, v in GOOD.items() if k != missing}
    with pytest.raises(settings.ConfigError) as exc:
        settings.load_database_config(env)
    assert missing in str(exc.value)
    assert "s3cret-value" not in str(exc.value)


def test_password_never_appears_in_repr_or_description():
    cfg = settings.load_database_config(GOOD)
    assert "s3cret-value" not in repr(cfg)
    assert "s3cret-value" not in cfg.describe()


def test_invalid_port_rejected():
    with pytest.raises(settings.ConfigError):
        settings.load_database_config({**GOOD, "DB_PORT": "abc"})
    with pytest.raises(settings.ConfigError):
        settings.load_database_config({**GOOD, "DB_PORT": "70000"})


def test_host_must_not_be_a_url():
    with pytest.raises(settings.ConfigError):
        settings.load_database_config({**GOOD, "DB_HOST": "mysql://host/db"})


def test_unknown_ssl_mode_rejected():
    with pytest.raises(settings.ConfigError):
        settings.load_database_config({**GOOD, "DB_SSL_MODE": "maybe"})


def test_verify_full_requires_ca_file(tmp_path):
    env = {**GOOD, "DB_SSL_MODE": "verify-full", "DB_SSL_CA": str(tmp_path / "missing.pem")}
    with pytest.raises(settings.ConfigError):
        settings.load_database_config(env)
    ca = tmp_path / "ca.pem"
    ca.write_text("dummy")
    cfg = settings.load_database_config({**env, "DB_SSL_CA": str(ca)})
    assert cfg.ssl_mode == "verify-full" and cfg.ssl_ca == str(ca)


def test_secret_key_required_and_long_enough():
    with pytest.raises(settings.ConfigError):
        settings.load_secret_key({})
    with pytest.raises(settings.ConfigError):
        settings.load_secret_key({"SECRET_KEY": "short"})
    assert settings.load_secret_key({"SECRET_KEY": "x" * 16}) == "x" * 16
