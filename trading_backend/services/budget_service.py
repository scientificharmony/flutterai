"""
Daily AI budget tracking for private test mode.
GBP cost estimates (rough): Claude call ~£0.002, market data call ~£0.0001.
"""
from datetime import datetime, timezone

from sqlmodel import Session, select

from config import settings
from models.db_models import DailyAiUsage

CLAUDE_COST_GBP = 0.002
MARKET_DATA_COST_GBP = 0.0001


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_or_create_usage(user_id: str, session: Session) -> DailyAiUsage:
    today = _today()
    usage = session.exec(
        select(DailyAiUsage).where(
            DailyAiUsage.user_id == user_id,
            DailyAiUsage.date == today,
        )
    ).first()
    if not usage:
        usage = DailyAiUsage(user_id=user_id, date=today)
        session.add(usage)
        session.commit()
        session.refresh(usage)
    return usage


def budget_remaining(user_id: str, session: Session) -> float:
    usage = get_or_create_usage(user_id, session)
    return max(0.0, settings.DAILY_AI_BUDGET_GBP - usage.estimated_cost_gbp)


def can_call_claude(user_id: str, session: Session) -> tuple[bool, str]:
    """Returns (allowed, reason). Reason is empty string when allowed."""
    if not settings.is_private_test:
        return True, ""
    usage = get_or_create_usage(user_id, session)
    if usage.claude_calls >= settings.MAX_CLAUDE_SCANS_PER_DAY:
        return False, f"Daily Claude call limit ({settings.MAX_CLAUDE_SCANS_PER_DAY}) reached."
    if usage.estimated_cost_gbp >= settings.DAILY_AI_BUDGET_GBP:
        return False, f"Daily AI budget of £{settings.DAILY_AI_BUDGET_GBP:.2f} reached."
    return True, ""


def can_send_alert(user_id: str, session: Session) -> tuple[bool, str]:
    """Check daily alert cap."""
    if not settings.is_private_test:
        return True, ""
    usage = get_or_create_usage(user_id, session)
    if usage.alerts_sent >= settings.MAX_ALERTS_PER_DAY:
        return False, f"Daily alert limit ({settings.MAX_ALERTS_PER_DAY}) reached."
    return True, ""


def record_claude_call(user_id: str, session: Session) -> None:
    usage = get_or_create_usage(user_id, session)
    usage.claude_calls += 1
    usage.estimated_cost_gbp += CLAUDE_COST_GBP
    session.add(usage)
    session.commit()


def record_market_data_call(user_id: str, session: Session) -> None:
    usage = get_or_create_usage(user_id, session)
    usage.market_data_calls += 1
    usage.estimated_cost_gbp += MARKET_DATA_COST_GBP
    session.add(usage)
    session.commit()


def record_alert_sent(user_id: str, session: Session) -> None:
    usage = get_or_create_usage(user_id, session)
    usage.alerts_sent += 1
    session.add(usage)
    session.commit()
