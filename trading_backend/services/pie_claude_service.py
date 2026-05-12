"""
Claude Pie explanation service.
Claude receives only the already-validated, already-allocated slices.
It writes names and rationale — it does NOT select tickers.
If Claude output is invalid, deterministic fallback wording is used.
"""
import json
import logging
from typing import Optional

from anthropic import Anthropic

from config import settings
from services.allocation_engine import AllocationSlice

logger = logging.getLogger(__name__)

_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = """You are a plain-English financial educator writing explanations for beginner investors.

You will receive a list of ETF/stock slices that have ALREADY been selected and allocated by a deterministic algorithm.
Your job is to:
1. Write a short, compelling pie_name (max 6 words, e.g. "AI Balanced Growth Portfolio")
2. Write an overall_rationale (2-3 sentences explaining the portfolio strategy)
3. Write a per-slice rationale (1 sentence per slice, max 20 words each)
4. Write a risk_note (1-2 sentences on relevant risks — honest and balanced)

RULES:
- Do NOT suggest different tickers or percentages — the allocation is final.
- Do NOT use hype language: no "guaranteed", "safe profit", "risk-free", "moon", "rocket".
- Use plain English. Assume the reader has no finance background.
- risk_note must acknowledge that past performance is not a guarantee.

Respond with ONLY valid JSON — no markdown, no extra text:
{
  "pie_name": "Balanced Growth Portfolio",
  "overall_rationale": "...",
  "slice_rationales": {"TICKER1": "...", "TICKER2": "..."},
  "risk_note": "..."
}"""


def _build_message(
    slices: list[AllocationSlice],
    goal: str,
    risk_level: str,
    time_horizon: str,
    total_amount: float,
) -> str:
    lines = [
        f"Goal: {goal}  |  Risk: {risk_level}  |  Horizon: {time_horizon}  |  Total: £{total_amount:.2f}",
        "",
        "Confirmed slices (do not change tickers or percentages):",
    ]
    for s in slices:
        lines.append(
            f"  {s.candidate.ticker} ({s.candidate.instrument_type}, {s.candidate.market_theme}): "
            f"{s.allocation_pct}% = £{s.amount:.2f}  "
            f"[score {s.candidate.opportunity_score}]"
        )
    lines += ["", "Write the JSON explanation now."]
    return "\n".join(lines)


def _fallback_rationale(slices: list[AllocationSlice], goal: str) -> dict:
    """Deterministic fallback if Claude output is invalid."""
    etf_pct = sum(s.allocation_pct for s in slices if s.candidate.instrument_type == "ETF")
    return {
        "pie_name": f"{goal.replace('_', ' ').title()} Portfolio",
        "overall_rationale": (
            f"This portfolio allocates {etf_pct:.0f}% to ETFs for broad diversification "
            f"and stability, with the remainder in targeted sector exposure."
        ),
        "slice_rationales": {
            s.candidate.ticker: f"Provides exposure to {s.candidate.market_theme.replace('_', ' ')}."
            for s in slices
        },
        "risk_note": (
            "All investments carry risk and the value of your portfolio can go down as well as up. "
            "Past performance is not a reliable indicator of future results."
        ),
    }


def _strip_fences(text: str) -> str:
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


async def explain_pie(
    slices: list[AllocationSlice],
    goal: str,
    risk_level: str,
    time_horizon: str,
    total_amount: float,
) -> dict:
    """
    Ask Claude to name and explain the portfolio.
    Returns a dict with: pie_name, overall_rationale, slice_rationales, risk_note.
    Falls back to deterministic wording on any failure.
    """
    user_message = _build_message(slices, goal, risk_level, time_horizon, total_amount)

    try:
        response = _client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=600,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = _strip_fences(response.content[0].text)
        data = json.loads(raw)

        # Validate required keys
        required = {"pie_name", "overall_rationale", "slice_rationales", "risk_note"}
        if not required.issubset(data.keys()):
            raise ValueError("Missing required keys in Claude response")

        # Validate slice_rationales covers all tickers
        for s in slices:
            if s.candidate.ticker not in data["slice_rationales"]:
                data["slice_rationales"][s.candidate.ticker] = (
                    f"Provides {s.candidate.market_theme.replace('_', ' ')} exposure."
                )

        return data

    except Exception as exc:
        logger.warning("Claude pie explanation failed (%s) — using fallback.", exc)
        return _fallback_rationale(slices, goal)
