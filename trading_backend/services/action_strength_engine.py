from models.schemas import (
    ACTION_STRENGTH_DISCLAIMER,
    interpretation_for_score,
    label_for_action_strength,
)


def _clamp_score(value: float) -> int:
    return max(0, min(100, round(value)))


def calculate_buy_action_strength(
    formula_score: int,
    claude_confidence: int,
    portfolio_fit_score: int | None = None,
) -> int:
    fit = 50 if portfolio_fit_score is None else portfolio_fit_score
    score = (formula_score * 0.65) + (claude_confidence * 0.20) + (fit * 0.15)
    return _clamp_score(score)


def calculate_sell_action_strength(
    weakness_score: int,
    drawdown_risk_score: int,
    claude_confidence: int,
    exposure_risk_score: int | None = None,
) -> int:
    exposure = 50 if exposure_risk_score is None else exposure_risk_score
    score = (
        (weakness_score * 0.45)
        + (drawdown_risk_score * 0.25)
        + (claude_confidence * 0.15)
        + (exposure * 0.15)
    )
    return _clamp_score(score)


def build_strength_metadata(score: int) -> tuple[str, str, str]:
    score = _clamp_score(score)
    return (
        label_for_action_strength(score),
        interpretation_for_score(score),
        ACTION_STRENGTH_DISCLAIMER,
    )
