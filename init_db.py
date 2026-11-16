"""Validate configuration, wait for MySQL, and create the schema.

Run automatically by entrypoint.py before Gunicorn starts. It can also be run
by hand:  python init_db.py

Exit codes: 0 = ready, 78 = invalid configuration, 1 = database unreachable
or schema creation failed.
"""
import sys
import time

from sqlalchemy import inspect, text
from sqlalchemy.exc import InterfaceError, OperationalError, ProgrammingError, SQLAlchemyError

import settings
from database import build_engine
from models import Base

EXIT_OK = 0
EXIT_DB_ERROR = 1
EXIT_CONFIG = 78


def log(message: str) -> None:
    print(f"[init_db] {message}", flush=True)


def _wait_for_database(engine, attempts: int, delay: int) -> bool:
    for attempt in range(1, attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            log("Database connection OK.")
            return True
        except (OperationalError, InterfaceError) as exc:
            # exc.orig is the PyMySQL error: it names the host/error code but
            # never contains the password.
            log(f"Database not reachable (attempt {attempt}/{attempts}): "
                f"{type(exc.orig).__name__}: {exc.orig}")
            if attempt < attempts:
                time.sleep(delay)
    return False


def _missing_tables(engine) -> set:
    expected = set(Base.metadata.tables)
    return expected - set(inspect(engine).get_table_names())


def initialize() -> int:
    try:
        db_config, _ = settings.validate_all()
    except settings.ConfigError as exc:
        log(f"Configuration error: {exc}")
        return EXIT_CONFIG

    log(f"Using MySQL: {db_config.describe()}")
    engine = build_engine(db_config)
    try:
        if not _wait_for_database(engine, db_config.startup_attempts, db_config.startup_delay):
            log("Giving up: database never became reachable. Check the RDS endpoint, "
                "security groups, credentials and TLS settings.")
            return EXIT_DB_ERROR

        try:
            Base.metadata.create_all(engine)  # CREATE TABLE only if missing
        except (OperationalError, ProgrammingError, InterfaceError) as exc:
            # Another container may have created the tables concurrently.
            log(f"create_all raised {type(exc.orig).__name__}; re-checking schema.")
        missing = _missing_tables(engine)
        if missing:
            log("Schema creation failed; missing tables: " + ", ".join(sorted(missing))
                + ". Does the database user have CREATE privilege?")
            return EXIT_DB_ERROR
        log("Schema ready: " + ", ".join(sorted(Base.metadata.tables)))
        return EXIT_OK
    except SQLAlchemyError as exc:
        log(f"Unexpected database error: {type(exc).__name__}")
        return EXIT_DB_ERROR
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(initialize())
