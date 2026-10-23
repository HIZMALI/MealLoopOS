"""Apply pending Alembic migrations to MEALLOOP_DATABASE_URL or local SQLite."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.database import database_url, make_engine, migrate

if __name__ == "__main__":
    engine = make_engine(database_url())
    try:
        migrate(engine)
        print("Database migrations are up to date (head: 0004).")
    finally:
        engine.dispose()
