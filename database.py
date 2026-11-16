"""SQLAlchemy engine/session setup for AWS RDS MySQL (PyMySQL driver)."""
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import Session, sessionmaker

from settings import DatabaseConfig


def build_engine(cfg: DatabaseConfig) -> Engine:
    """Create the engine. No connection is opened until the first query.

    * URL.create() escapes special characters in the password safely.
    * pool_pre_ping tests each pooled connection on checkout and transparently
      replaces stale ones, so the app recovers after an RDS failover/restart or
      a dropped idle connection.
    * pool_recycle retires connections before server/NAT idle timeouts.
    * hide_parameters keeps bound values (e.g. password hashes) out of errors.
    * TLS with certificate *and* hostname verification against the RDS CA bundle
      is on unless DB_SSL_MODE=disabled (local development only).
    """
    url = URL.create(
        "mysql+pymysql",
        username=cfg.user,
        password=cfg.password,
        host=cfg.host,
        port=cfg.port,
        database=cfg.name,
        query={"charset": "utf8mb4"},
    )

    connect_args = {
        "connect_timeout": cfg.connect_timeout,
        "read_timeout": cfg.read_timeout,
        "write_timeout": cfg.read_timeout,
    }
    if cfg.ssl_mode == "verify-full":
        connect_args.update(
            ssl_ca=cfg.ssl_ca,
            ssl_verify_cert=True,
            ssl_verify_identity=True,
        )

    return create_engine(
        url,
        pool_size=cfg.pool_size,
        max_overflow=cfg.max_overflow,
        pool_recycle=cfg.pool_recycle,
        pool_timeout=cfg.pool_timeout,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args=connect_args,
    )


def build_session_factory(engine: Engine) -> "sessionmaker[Session]":
    return sessionmaker(bind=engine, expire_on_commit=False)
