"""SQLAlchemy engine/session setup. Defaults to SQLite for zero-infra local dev;
point DATABASE_URL at Postgres for the docker-compose / production path — the
schema is portable, nothing here is SQLite-specific."""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./experiments.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_session() -> Session:
    return SessionLocal()


def init_db() -> None:
    import src.models  # noqa: F401 ensures models are registered before create_all

    Base.metadata.create_all(bind=engine)
