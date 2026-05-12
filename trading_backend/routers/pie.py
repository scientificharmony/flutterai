"""
Pie Builder API endpoints.
POST /pie/build    — run full pipeline, return PieBuildResponse
GET  /pie/templates — return preset goal templates
POST /pie/save     — persist a built pie to user history
GET  /pie/history  — list user's saved pies
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from auth import get_current_user
from config import settings
from database import get_session
from models.db_models import User, SavedPie, PieUsage
from models.pie_schemas import (
    DATA_STALENESS_DAYS,
    PRACTICAL_MIN_SLICE_AMOUNT,
    DataFreshness,
    PieBuildRequest,
    PieBuildResponse,
    PieDeployRequest,
    PieDeployResponse,
    PieSlice,
    PieTemplate,
    SavePieRequest,
    SavedPieResponse,
    ScoredPieCandidate,
)
from models.schemas import label_for_action_strength
from services import trading212_service
from services.allocation_engine import build_allocation
from services.market_themes import get_candidates_for_themes, themes_for_goal
from services.pie_claude_service import explain_pie
from services.pie_formula_engine import score_pie_candidate, MIN_OPPORTUNITY_SCORE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pie", tags=["pie"])

FREE_PIE_BUILDS_PER_DAY = 1
PRO_PIE_BUILDS_PER_DAY = 10


# ── Quota helpers ─────────────────────────────────────────────────────────────

def _check_pie_quota(user: User, session: Session) -> None:
    if settings.is_private_test:
        return  # No quota in private test mode
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    usage = session.exec(
        select(PieUsage).where(PieUsage.user_id == user.id, PieUsage.date == today)
    ).first()
    limit = PRO_PIE_BUILDS_PER_DAY if user.plan == "pro" else FREE_PIE_BUILDS_PER_DAY
    if usage and usage.build_count >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Daily Pie build limit of {limit} reached. Upgrade to Pro for more.",
        )


def _increment_pie_usage(user_id: str, session: Session) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    usage = session.exec(
        select(PieUsage).where(PieUsage.user_id == user_id, PieUsage.date == today)
    ).first()
    if usage:
        usage.build_count += 1
        usage.estimated_cost_usd += 0.003
    else:
        usage = PieUsage(user_id=user_id, date=today, build_count=1, estimated_cost_usd=0.003)
    session.add(usage)
    session.commit()


# ── Freshness helpers ─────────────────────────────────────────────────────────

def _oldest_allowed() -> datetime:
    """Newest data row must be no older than DATA_STALENESS_DAYS calendar days."""
    return datetime.now(timezone.utc) - timedelta(days=DATA_STALENESS_DAYS)


def _is_data_stale(ts: datetime) -> bool:
    return ts < _oldest_allowed()


def _build_freshness(candidates: list[ScoredPieCandidate]) -> DataFreshness:
    oldest_allowed = _oldest_allowed()
    stale = [c.ticker for c in candidates if _is_data_stale(c.data_timestamp)]
    newest_ts = max(c.data_timestamp for c in candidates)
    if not stale:
        status = "fresh"
    elif len(stale) == len(candidates):
        status = "unavailable"
    else:
        status = "stale"
    return DataFreshness(
        status=status,
        newest_data_timestamp=newest_ts,
        oldest_allowed_timestamp=oldest_allowed,
        stale_tickers=stale,
    )


# ── Amount sanity check ───────────────────────────────────────────────────────

def _min_viable_amount(n_slices: int) -> float:
    """Minimum total £ so every slice can be at least PRACTICAL_MIN_SLICE_AMOUNT."""
    return n_slices * PRACTICAL_MIN_SLICE_AMOUNT / (5.0 / 100)  # min slice is 5%


# ── Build endpoint ────────────────────────────────────────────────────────────

@router.post("/build", response_model=PieBuildResponse)
async def build_pie(
    body: PieBuildRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _check_pie_quota(user, session)

    safety_flags: list[str] = []
    warnings: list[str] = []
    invest_only_verified = True
    all_slices_validated = True

    # 1. Resolve themes
    themes = themes_for_goal(body.goal, body.preferred_themes, body.excluded_themes)
    if not themes:
        raise HTTPException(status_code=422, detail="No valid themes after applying exclusions.")

    # 2. Get candidate tickers
    raw_candidates = get_candidates_for_themes(themes)

    # 3. Validate, score, and freshness-check each candidate
    validated: list[ScoredPieCandidate] = []
    already_selected_themes: list[str] = []

    for ticker, theme in raw_candidates:
        if len(validated) >= 20:
            break

        # T212 Invest-only validation
        try:
            ok, instrument_type = await trading212_service.validate_invest_instrument(ticker)
        except Exception:
            all_slices_validated = False
            continue
        if not ok:
            invest_only_verified = False
            logger.debug("Rejected %s (T212 invest check failed)", ticker)
            continue

        # Score
        candidate = score_pie_candidate(ticker, theme, instrument_type, already_selected_themes)
        if candidate is None:
            all_slices_validated = False
            continue

        # Freshness gate: reject stale candidates outright
        if _is_data_stale(candidate.data_timestamp):
            safety_flags.append(
                f"{ticker} rejected: market data is stale "
                f"(last row {candidate.data_timestamp.date()}, "
                f"threshold {_oldest_allowed().date()})"
            )
            all_slices_validated = False
            continue

        if candidate.opportunity_score < MIN_OPPORTUNITY_SCORE:
            logger.debug("Rejected %s: score %.1f < %.1f", ticker, candidate.opportunity_score, MIN_OPPORTUNITY_SCORE)
            continue

        candidate = candidate.model_copy(
            update={
                "name": trading212_service.get_instrument_name(ticker) or ticker,
                "invest_validated": True,
            }
        )
        validated.append(candidate)
        already_selected_themes.append(theme)

    # 4. Guard: no valid candidates
    if not validated:
        # Still need to return a structured response, not a 422, so the client
        # can display the reason. Build a minimal non-executable response.
        now = datetime.now(timezone.utc)
        dummy_ts = now - timedelta(days=DATA_STALENESS_DAYS + 1)
        freshness = DataFreshness(
            status="unavailable",
            newest_data_timestamp=dummy_ts,
            oldest_allowed_timestamp=_oldest_allowed(),
            stale_tickers=[],
        )
        return PieBuildResponse(
            pie_name="No Pie Generated",
            goal=body.goal,
            risk_level=body.risk_level,
            total_amount=body.total_amount,
            time_horizon=body.time_horizon,
            slices=[],
            overall_rationale="",
            risk_note="",
            executable=False,
            safety_flags=safety_flags + ["No candidates passed scoring and T212 validation."],
            warnings=["Try different themes, remove exclusions, or increase the amount."],
            data_freshness=freshness,
            market_data_timestamp=dummy_ts,
            valid_until=now + timedelta(hours=24),
            invest_only_verified=invest_only_verified,
            all_slices_validated=False,
            manual_execution_only=True,
        )

    # 5. Guard: amount too low for minimum slice sizing
    min_needed = _min_viable_amount(min(len(validated), 8))
    if body.total_amount < min_needed:
        warnings.append(
            f"£{body.total_amount:.2f} may be too low for {min(len(validated),8)} slices "
            f"(minimum recommended: £{min_needed:.0f}). "
            "Some slices may fall below the practical minimum."
        )

    # 6. Allocation engine
    allocation_slices, alloc_flags = build_allocation(validated, body.risk_level, body.total_amount)
    safety_flags.extend(alloc_flags)

    if not allocation_slices:
        msg = alloc_flags[0] if alloc_flags else "Allocation failed."
        safety_flags.append(msg)
        now = datetime.now(timezone.utc)
        ts = max(c.data_timestamp for c in validated)
        freshness = _build_freshness(validated)
        return PieBuildResponse(
            pie_name="Allocation Failed",
            goal=body.goal,
            risk_level=body.risk_level,
            total_amount=body.total_amount,
            time_horizon=body.time_horizon,
            slices=[],
            overall_rationale="",
            risk_note="",
            executable=False,
            safety_flags=safety_flags,
            warnings=warnings,
            data_freshness=freshness,
            market_data_timestamp=ts,
            valid_until=now + timedelta(hours=24),
            invest_only_verified=invest_only_verified,
            all_slices_validated=all_slices_validated,
            manual_execution_only=True,
        )

    # 7. Guard: allocation must normalise to exactly 100%
    total_pct = round(sum(s.allocation_pct for s in allocation_slices), 1)
    if total_pct != 100.0:
        safety_flags.append(
            f"Allocation normalisation error: slices sum to {total_pct}% instead of 100%."
        )
        all_slices_validated = False

    # 8. Build freshness metadata across final slices
    slice_candidates = [s.candidate for s in allocation_slices]
    freshness = _build_freshness(slice_candidates)
    market_data_ts = freshness.newest_data_timestamp
    valid_until = market_data_ts + timedelta(hours=24)
    now = datetime.now(timezone.utc)

    if freshness.status == "stale":
        safety_flags.append(
            "Some slice data is stale. Market conditions may have changed."
        )

    # 9. Determine executable
    executable = (
        len([f for f in safety_flags if "error" in f.lower() or "stale" in f.lower() or "failed" in f.lower()]) == 0
        and freshness.status != "unavailable"
        and total_pct == 100.0
        and body.total_amount >= PRACTICAL_MIN_SLICE_AMOUNT
    )

    # 10. Claude explanation
    explanation = await explain_pie(
        allocation_slices, body.goal, body.risk_level, body.time_horizon, body.total_amount
    )

    # 11. Assemble slices
    slices = [
        PieSlice(
            ticker=s.candidate.ticker,
            name=s.candidate.name,
            instrument_type=s.candidate.instrument_type,  # type: ignore[arg-type]
            market_theme=s.candidate.market_theme,
            allocation_percent=s.allocation_pct,
            amount=s.amount,
            opportunity_score=s.candidate.opportunity_score,
            opportunity_strength=int(round(s.candidate.opportunity_score)),
            strength_label=label_for_action_strength(int(round(s.candidate.opportunity_score))),
            rationale=explanation["slice_rationales"].get(
                s.candidate.ticker,
                f"Provides {s.candidate.market_theme.replace('_', ' ')} exposure.",
            ),
        )
        for s in allocation_slices
    ]

    _increment_pie_usage(user.id, session)

    logger.info(
        "PIE BUILD | user=%s | goal=%s | risk=%s | slices=%d | £%.2f | "
        "executable=%s | freshness=%s | invest_only=%s",
        user.id, body.goal, body.risk_level, len(slices), body.total_amount,
        executable, freshness.status, invest_only_verified,
    )

    return PieBuildResponse(
        pie_name=explanation["pie_name"],
        goal=body.goal,
        risk_level=body.risk_level,
        total_amount=body.total_amount,
        time_horizon=body.time_horizon,
        slices=slices,
        overall_rationale=explanation["overall_rationale"],
        risk_note=explanation["risk_note"],
        executable=executable,
        safety_flags=safety_flags,
        warnings=warnings,
        data_freshness=freshness,
        market_data_timestamp=market_data_ts,
        valid_until=valid_until,
        invest_only_verified=invest_only_verified,
        all_slices_validated=all_slices_validated,
        manual_execution_only=True,
    )


# ── Templates ─────────────────────────────────────────────────────────────────

_TEMPLATES: list[PieTemplate] = [
    PieTemplate(
        id="safer_core_low",
        name="Safer Core",
        goal="safer_core",
        risk_level="low",
        description="90%+ ETFs across global equity and defensive themes for capital preservation.",
        themes=["global_equity", "sp500", "defensive"],
        pro_only=False,
    ),
    PieTemplate(
        id="balanced_growth_medium",
        name="Balanced Growth",
        goal="balanced_growth",
        risk_level="medium",
        description="Mix of global equity, technology, and dividend ETFs for steady growth.",
        themes=["global_equity", "technology", "dividend_income"],
        pro_only=False,
    ),
    PieTemplate(
        id="ai_tech_high",
        name="AI & Technology",
        goal="ai_technology",
        risk_level="high",
        description="Technology and semiconductor exposure for high-growth investors.",
        themes=["technology", "semiconductors", "sp500"],
        pro_only=True,
    ),
    PieTemplate(
        id="clean_energy_medium",
        name="Clean Energy",
        goal="clean_energy",
        risk_level="medium",
        description="Renewable energy and ESG-aligned ETFs and stocks.",
        themes=["clean_energy", "technology"],
        pro_only=True,
    ),
    PieTemplate(
        id="dividend_income_low",
        name="Dividend Income",
        goal="dividend_income",
        risk_level="low",
        description="High-yield dividend ETFs and blue-chip income stocks.",
        themes=["dividend_income", "defensive", "uk_large_cap"],
        pro_only=False,
    ),
]


@router.get("/templates", response_model=list[PieTemplate])
def get_templates(user: User = Depends(get_current_user)):
    if settings.is_private_test or user.plan != "free":
        return _TEMPLATES
    return [t for t in _TEMPLATES if not t.pro_only]


# ── Save & History ────────────────────────────────────────────────────────────

@router.post("/save", response_model=SavedPieResponse)
def save_pie(
    body: SavePieRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not body.pie.executable:
        raise HTTPException(
            status_code=422,
            detail="Cannot save a non-executable Pie. Resolve safety flags first.",
        )

    if user.plan == "free":
        existing = session.exec(
            select(SavedPie).where(SavedPie.user_id == user.id)
        ).all()
        if len(existing) >= 1:
            raise HTTPException(
                status_code=403,
                detail="Free users can save 1 Pie. Upgrade to Pro for unlimited history.",
            )

    pie = body.pie
    saved = SavedPie(
        user_id=user.id,
        pie_name=pie.pie_name,
        goal=pie.goal,
        risk_level=pie.risk_level,
        total_amount=pie.total_amount,
        time_horizon=pie.time_horizon,
        slices=[s.model_dump() for s in pie.slices],
        overall_rationale=pie.overall_rationale,
        risk_note=pie.risk_note,
    )
    session.add(saved)
    session.commit()
    session.refresh(saved)
    return _to_saved_response(saved)


@router.get("/history", response_model=list[SavedPieResponse])
def pie_history(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    pies = session.exec(
        select(SavedPie)
        .where(SavedPie.user_id == user.id)
        .order_by(SavedPie.created_at.desc())
    ).all()
    return [_to_saved_response(p) for p in pies]


@router.post("/deploy", response_model=PieDeployResponse)
async def deploy_pie(
    body: PieDeployRequest,
    user: User = Depends(get_current_user),
):
    """
    Create a pie in the user's live/demo T212 account.
    Requires ENABLE_ORDER_API=true in server config.
    """
    if not settings.enable_order_api:
        raise HTTPException(
            status_code=403,
            detail="Pie deployment is disabled on this server. Set ENABLE_ORDER_API=true to enable.",
        )
    if not body.slices:
        raise HTTPException(status_code=422, detail="No slices provided.")

    slices = [
        {"ticker": s.ticker, "allocation_percent": s.allocation_percent}
        for s in body.slices
    ]
    try:
        result = await trading212_service.create_pie(body.pie_name, slices, body.dividend_action)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("T212 pie creation failed for user=%s: %s", user.id, exc)
        raise HTTPException(status_code=502, detail=f"Trading 212 rejected the request: {exc}")

    pie_id = result.get("id")
    logger.info("PIE DEPLOY | user=%s | pie=%r | t212_id=%s", user.id, body.pie_name, pie_id)
    return PieDeployResponse(
        t212_pie_id=pie_id,
        pie_name=body.pie_name,
        message=f"Pie '{body.pie_name}' created in your Trading 212 account (ID {pie_id}).",
    )


def _to_saved_response(saved: SavedPie) -> SavedPieResponse:
    slices = [PieSlice(**s) for s in (saved.slices or [])]
    return SavedPieResponse(
        id=saved.id,
        pie_name=saved.pie_name,
        risk_level=saved.risk_level,
        total_amount=saved.total_amount,
        created_at=saved.created_at.isoformat(),
        slices=slices,
    )
