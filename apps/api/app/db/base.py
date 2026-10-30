from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint names, so Alembic migrations can drop/alter them by name.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {datetime: DateTime(timezone=True)}


def created_at_column() -> Mapped[datetime]:
    return mapped_column(server_default=func.now())


def in_check(column: str, values: tuple[str, ...]) -> str:
    """SQL for a CHECK constraint limiting a text column to fixed values.

    Used instead of native Postgres enums, which need hand-written migrations to extend.
    """
    return f"{column} IN ({', '.join(repr(v) for v in values)})"
