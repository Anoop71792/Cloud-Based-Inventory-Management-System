"""SQLAlchemy models for MySQL (InnoDB, utf8mb4)."""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (CheckConstraint, DateTime, ForeignKey, Integer, Numeric,
                        String, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

MYSQL_TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}


def utcnow() -> datetime:
    """Naive UTC timestamp (MySQL DATETIME has no timezone)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Binary collation keeps usernames case-sensitive, as they were under SQLite.
    username: Mapped[str] = mapped_column(String(40, collation="utf8mb4_bin"), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("user_id", "sku", name="uq_products_user_sku"),
        CheckConstraint("price >= 0", name="ck_products_price_nonneg"),
        CheckConstraint("quantity >= 0", name="ck_products_quantity_nonneg"),
        CheckConstraint("reorder_level >= 0", name="ck_products_reorder_nonneg"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    sku: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Binary collation: category filtering/DISTINCT stay case-sensitive as before.
    category: Mapped[str] = mapped_column(
        String(80, collation="utf8mb4_bin"), nullable=False, default="General",
        server_default="General",
    )
    # Fixed-precision money value (the SQLite version used floating point).
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reorder_level: Mapped[int] = mapped_column(Integer, nullable=False, default=5,
                                               server_default="5")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
