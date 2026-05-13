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
    _create_forex_positions_if_missing()
    _add_column_if_missing("forex_positions", "last_assistant_status", "TEXT")
    _add_column_if_missing("forex_positions", "last_notified_status", "TEXT")
    _add_column_if_missing("forex_positions", "ig_deal_id", "TEXT")
    _add_column_if_missing("forex_positions", "ig_epic", "TEXT")
    _add_column_if_missing("forex_positions", "ig_size", "REAL")


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


def _create_forex_positions_if_missing() -> None:
    """Create Forex Lab practice table for existing SQLite deployments."""
    with Session(engine) as session:
        try:
            session.exec(text("""
                CREATE TABLE IF NOT EXISTS forex_positions (
                    id TEXT NOT NULL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    pair TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    risk_amount REAL NOT NULL,
                    position_units INTEGER NOT NULL DEFAULT 0,
                    timeframe TEXT NOT NULL DEFAULT '15m',
                    ig_deal_id TEXT,
                    ig_epic TEXT,
                    ig_size REAL,
                    status TEXT NOT NULL DEFAULT 'open',
                    close_price REAL,
                    realised_pnl REAL,
                    last_assistant_status TEXT,
                    last_notified_status TEXT,
                    opened_at DATETIME NOT NULL,
                    closed_at DATETIME,
                    FOREIGN KEY(user_id) REFERENCES users (id)
                )
            """))
            session.exec(text("CREATE INDEX IF NOT EXISTS ix_forex_positions_user_id ON forex_positions (user_id)"))
            session.exec(text("CREATE INDEX IF NOT EXISTS ix_forex_positions_pair ON forex_positions (pair)"))
            session.commit()
        except Exception as exc:
            logger.warning("Migration skipped forex_positions create: %s", exc)


def get_session():
    with Session(engine) as session:
        yield session
