import logging
from sqlmodel import SQLModel, create_engine, Session, text
from config import settings

logger = logging.getLogger(__name__)
engine = create_engine(settings.DATABASE_URL, echo=False)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)
    _run_migrations()


def _run_migrations() -> None:
    """Safe additive column migrations for SQLite."""
    _add_column_if_missing("trade_alerts", "what_is_this", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing("trade_alerts", "sell_trigger", "TEXT")
    _add_column_if_missing("open_positions", "peak_price", "REAL")


def _add_column_if_missing(table: str, column: str, col_def: str) -> None:
    with Session(engine) as session:
        try:
            existing = session.exec(text(f"PRAGMA table_info({table})")).fetchall()
            if not existing:
                return  # table doesn't exist yet — create_all will handle it
            col_names = [row[1] for row in existing]
            if column not in col_names:
                session.exec(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"))
                session.commit()
                logger.info("Migration: added %s.%s", table, column)
        except Exception as exc:
            logger.warning("Migration skipped %s.%s: %s", table, column, exc)


def get_session():
    with Session(engine) as session:
        yield session
