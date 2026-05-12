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

_SYSTEM_PROMPT = """You are a conservative financial assistant helping beginner investors review opportunities.

You will receive pre-screened Trading 212 Invest candidates (stocks and/or ETFs).
Write for someone with NO prior investing experience. Use plain, simple English.

STRICT RULES:
- Select a ticker from the candidates list only.
- Do not calculate Action Strength.
- Do not output probabilities of success.
- Do not use "guaranteed", "buy now", "sell now", "definitely", or "risk-free".
- For ETFs: explain as a diversified fund, not a single stock pick.
- Return JSON only — no extra text.

Output schema:
{
  "ticker": "VHYLL",
  "claude_confidence": 78,
  "reasoning_quality": 75,
  "what_is_this": "One sentence: what this instrument IS, in plain English. E.g. 'VHYLL is a fund that holds hundreds of dividend-paying companies from around the world — it spreads risk and pays regular income.'",
  "plain_english_summary": "2-3 sentences explaining WHY this setup looks interesting right now, written for a beginner. No jargon. E.g. 'The price has been moving steadily upward and trading volume is healthy. The trend looks positive and there are no obvious warning signs at this moment.'",
  "key_factors": ["Short plain-English reason 1", "Short plain-English reason 2"],
  "risks": ["Plain-English risk 1", "Plain-English risk 2"],
  "contradiction_notes": []
}"""


def _build_user_message(
    candidates: list[ScoredCandidate],
    user_balance: float,
    max_trade_amount: float,
    mission: Optional[str],
    instrument_types: Optional[dict[str, str]] = None,
) -> str:
    lines = [
        f"User balance: £{user_balance:.2f}",
        f"Max review amount under 10% rule: £{max_trade_amount:.2f}",
        "",
        "Validated candidates:",
    ]
    for c in candidates:
        inst_type = (instrument_types or {}).get(c.ticker.upper(), "")
        type_tag = f" [{inst_type}]" if inst_type else ""
        lines.append(
            f"{c.ticker}{type_tag}: score={c.score}, price=£{c.current_price:.2f}, "
            f"RSI={c.rsi:.1f}, vol_ratio={c.volume_ratio:.2f}, signals={c.signal_summary}."
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
    ticker = candidates[0].ticker.upper()
    return ClaudeRecommendation(
        ticker=ticker,
        claude_confidence=50,
        reasoning_quality=50,
        what_is_this=f"{ticker} is a Trading 212 Invest instrument that passed automated screening.",
        key_factors=["Passed automated technical screening."],
        risks=["Market conditions can change quickly — always review before acting."],
        contradiction_notes=[],
        plain_english_summary=(
            f"{ticker} was flagged by the formula scan. "
            "Review the chart in Trading 212 before deciding anything."
        ),
    )


async def analyse_candidates(
    candidates: list[ScoredCandidate],
    user_balance: float,
    max_trade_amount: float,
    mission: Optional[str] = None,
    instrument_types: Optional[dict[str, str]] = None,
) -> ClaudeRecommendation:
    if not candidates:
        raise ValueError("No candidates to analyse.")

    user_message = _build_user_message(candidates, user_balance, max_trade_amount, mission, instrument_types)
    valid_tickers = {c.ticker.upper() for c in candidates}

    try:
        response = _client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=800,
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
        summary = f"{rec.ticker.upper()} was flagged by the formula scan. Review the chart before deciding anything."

    what_is_this = rec.what_is_this
    if _contains_forbidden(what_is_this):
        what_is_this = ""

    return rec.model_copy(
        update={
            "ticker": rec.ticker.upper(),
            "what_is_this": what_is_this,
            "key_factors": _clean_texts(rec.key_factors),
            "risks": _clean_texts(rec.risks),
            "contradiction_notes": _clean_texts(rec.contradiction_notes),
            "plain_english_summary": summary,
        }
    )
