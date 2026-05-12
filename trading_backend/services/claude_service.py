import json
import re
from typing import Optional

from anthropic import Anthropic

from config import settings
from models.schemas import ClaudeRecommendation
from services.formula_engine import ScoredCandidate

_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

_FORBIDDEN_PATTERNS = re.compile(
    r"\b(guaranteed|safe profit|can't lose|risk.?free|buy now|sell now|definitely|probability of success|success chance|moon|rocket)\b",
    re.IGNORECASE,
)

_SYSTEM_PROMPT = """You are a conservative financial risk analyst for beginner investors.

You will receive a list of pre-screened stock/ETF candidates that have passed validation.
Explain the single best candidate in plain language.

STRICT RULES:
- Select a ticker from candidates only.
- Do not calculate final Action Strength.
- Do not output probabilities of success.
- Do not use guaranteed language, or "buy now"/"sell now".
- Return JSON only.

Output schema:
{
  "ticker": "AAPL",
  "claude_confidence": 78,
  "reasoning_quality": 75,
  "key_factors": ["Factor one", "Factor two"],
  "risks": ["Risk one", "Risk two"],
  "contradiction_notes": ["Optional contradiction"],
  "plain_english_summary": "Clear summary for manual review."
}"""


def _build_user_message(
    candidates: list[ScoredCandidate],
    user_balance: float,
    max_trade_amount: float,
    mission: Optional[str],
) -> str:
    lines = [
        f"User balance: £{user_balance:.2f}",
        f"Max review amount under 10% rule: £{max_trade_amount:.2f}",
        "",
        "Validated candidates:",
    ]
    for c in candidates:
        lines.append(
            f"{c.ticker}: score={c.score}, price=£{c.current_price:.2f}, RSI={c.rsi:.1f}, vol_ratio={c.volume_ratio:.2f}."
        )
    if mission:
        lines += ["", f"Mission: {mission}"]
    return "\n".join(lines)


def _contains_forbidden(text: str) -> bool:
    return bool(_FORBIDDEN_PATTERNS.search(text))


def _clean_texts(values: list[str]) -> list[str]:
    return [v for v in values if not _contains_forbidden(v)]


def _strip_fences(text: str) -> str:
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def _fallback(candidates: list[ScoredCandidate]) -> ClaudeRecommendation:
    return ClaudeRecommendation(
        ticker=candidates[0].ticker.upper(),
        claude_confidence=50,
        reasoning_quality=50,
        key_factors=["Validated candidate passed deterministic screening."],
        risks=["Market movement can invalidate setups quickly."],
        contradiction_notes=[],
        plain_english_summary="Validated candidate identified for manual review.",
    )


async def analyse_candidates(
    candidates: list[ScoredCandidate],
    user_balance: float,
    max_trade_amount: float,
    mission: Optional[str] = None,
) -> ClaudeRecommendation:
    if not candidates:
        raise ValueError("No candidates to analyse.")

    user_message = _build_user_message(candidates, user_balance, max_trade_amount, mission)
    valid_tickers = {c.ticker.upper() for c in candidates}

    try:
        response = _client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=600,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        data = json.loads(_strip_fences(response.content[0].text))
        rec = ClaudeRecommendation(**data)
    except Exception:
        return _fallback(candidates)

    if rec.ticker.upper() not in valid_tickers:
        return _fallback(candidates)

    summary = rec.plain_english_summary
    if _contains_forbidden(summary):
        summary = "Validated candidate identified for manual review."

    return rec.model_copy(
        update={
            "ticker": rec.ticker.upper(),
            "key_factors": _clean_texts(rec.key_factors),
            "risks": _clean_texts(rec.risks),
            "contradiction_notes": _clean_texts(rec.contradiction_notes),
            "plain_english_summary": summary,
        }
    )
