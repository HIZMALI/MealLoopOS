import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

ROOT = Path(__file__).resolve().parents[2]


class Base(DeclarativeBase):
    pass


def make_engine(url: str, *, readonly=False):
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def sqlite_settings(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            if readonly:
                connection.execute("PRAGMA query_only=ON")
    return engine


def migrate(engine):
    config = Config()
    config.set_main_option("script_location", str(ROOT / "backend/migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def database_url():
    (ROOT / "data").mkdir(exist_ok=True)
    return os.getenv("MEALLOOP_DATABASE_URL", f"sqlite:///{(ROOT / 'data/mealloop.db').as_posix()}")


def sessions(engine):
    return sessionmaker(engine, expire_on_commit=False)
