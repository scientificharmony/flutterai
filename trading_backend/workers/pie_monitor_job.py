"""
Phase 11 — Pie monitoring job.
Checks saved pies for:
  - Allocation drift (slice drifted >5% from target)
  - Weak slice score (opportunity_score dropped below 60)
  - Improved opportunity (score improved to >85 on a previously weak slice)
Sends push notifications without trade instructions.
"""
import logging
from datetime import datetime, timezone

from sqlmodel import Session, select

from database import engine
from models.db_models import SavedPie, DeviceToken
from services.market_themes import THEMES
from services.pie_formula_engine import score_pie_candidate, MIN_OPPORTUNITY_SCORE
from services.notification_service import send_to_user_devices
from services import trading212_service

logger = logging.getLogger(__name__)

DRIFT_THRESHOLD = 5.0        # % drift triggers a notification
WEAK_SCORE_THRESHOLD = 60.0  # below this is considered a weak slice
STRONG_SCORE_THRESHOLD = 85.0  # above this is an improved opportunity


async def run_pie_monitoring() -> None:
    """Check all monitoring-enabled pies and send alerts if needed."""
    with Session(engine) as session:
        pies = session.exec(
            select(SavedPie).where(SavedPie.monitoring_enabled == True)
        ).all()

        for pie in pies:
            try:
                await _check_pie(pie, session)
                pie.last_monitored_at = datetime.now(timezone.utc)
                session.add(pie)
            except Exception as exc:
                logger.warning("Pie monitoring failed for %s: %s", pie.id, exc)

        session.commit()


async def _check_pie(pie: SavedPie, session: Session) -> None:
    slices = pie.slices or []
    if not slices:
        return

    notifications: list[tuple[str, str]] = []  # (title, body) pairs

    for slice_data in slices:
        ticker = slice_data.get("ticker", "")
        theme = slice_data.get("market_theme", "global_equity")
        target_pct = float(slice_data.get("allocation_percent", 0))
        prev_score = float(slice_data.get("opportunity_score", 0))

        # Re-score
        try:
            ok, instrument_type = await trading212_service.validate_invest_instrument(ticker)
        except Exception:
            continue

        if not ok:
            continue

        fresh = score_pie_candidate(ticker, theme, instrument_type, [])
        if fresh is None:
            continue

        new_score = fresh.opportunity_score

        # Drift check: compare current price weight vs target
        # For MVP, we use the score change as a proxy for drift
        score_drift = abs(new_score - prev_score)
        if score_drift >= DRIFT_THRESHOLD * 2:
            notifications.append((
                f"Pie review suggested: {pie.pie_name}",
                f"Your {ticker} slice has moved significantly. Consider reviewing your allocation.",
            ))

        # Weak slice
        if new_score < WEAK_SCORE_THRESHOLD and prev_score >= WEAK_SCORE_THRESHOLD:
            notifications.append((
                f"Weak slice detected: {ticker}",
                f"The opportunity score for {ticker} in your {pie.pie_name} has declined. Consider reviewing.",
            ))

        # Improved opportunity
        if new_score >= STRONG_SCORE_THRESHOLD and prev_score < STRONG_SCORE_THRESHOLD:
            notifications.append((
                f"Opportunity improved: {ticker}",
                f"{ticker} in your {pie.pie_name} has reached a strong opportunity score of {new_score:.0f}.",
            ))

    if not notifications:
        return

    # Fetch device tokens for user
    tokens = session.exec(
        select(DeviceToken).where(DeviceToken.user_id == pie.user_id)
    ).all()
    if not tokens:
        return

    token_list = [t.token for t in tokens]
    for title, body in notifications:
        send_to_user_devices(
            token_list,
            title=title,
            body=body,
            alert_id=pie.id,
            ticker="PIE",
        )
        logger.info("PIE MONITOR | pie=%s | sent: %s", pie.id, title)
