"""Test fixtures. The tests run against a real MySQL server (no SQLite).

Point DB_* at a throw-away MySQL database whose name ends in "_test"; the
schema is dropped and recreated for the test session, and tables are emptied
between tests. Example:

    DB_HOST=127.0.0.1 DB_NAME=inventory_test DB_USER=... DB_PASSWORD=... \
    DB_SSL_MODE=disabled python -m pytest -v
"""
import os

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
# Local/CI test databases normally have no TLS. Override to verify-full to test against RDS.
os.environ.setdefault("DB_SSL_MODE", "disabled")


@pytest.fixture(scope="session")
def inventory_app():
    name = os.environ.get("DB_NAME", "")
    if not name.endswith("_test"):
        pytest.exit(
            "Refusing to run: DB_NAME must end with '_test' because the tests drop and "
            "recreate tables. Create a separate test database.", returncode=2)

    import app as app_module
    from models import Base

    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    app_module.app.config.update(TESTING=True)
    yield app_module
    app_module.engine.dispose()


@pytest.fixture
def client(inventory_app):
    """Fresh, empty tables for every test."""
    from sqlalchemy import text

    with inventory_app.engine.begin() as conn:
        conn.execute(text("DELETE FROM products"))
        conn.execute(text("DELETE FROM users"))
    with inventory_app.app.test_client() as test_client:
        yield test_client
