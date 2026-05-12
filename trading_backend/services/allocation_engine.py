"""
Allocation engine.
Determines slice percentages from scored candidates based on risk rules.
Enforces:
  - Risk-level ETF minimums
  - Max slices (8)
  - Min slice (5%)
  - Max single-slice caps
  - Total must equal 100%
  - No slice £-amount below practical minimum (£1)
"""
from dataclasses import dataclass
from typing import Optional

from models.pie_schemas import ScoredPieCandidate

# ── Risk rules ────────────────────────────────────────────────────────────────

@dataclass
class RiskRule:
    min_etf_pct: float          # minimum % that must be ETFs
    max_thematic_pct: float     # max % allowed in thematic/sector plays
    max_single_slice_pct: float # cap on any one slice
    max_single_stock_pct: float # cap on any one individual stock

RISK_RULES: dict[str, RiskRule] = {
    "low": RiskRule(
        min_etf_pct=90.0,
        max_thematic_pct=10.0,
        max_single_slice_pct=60.0,
        max_single_stock_pct=5.0,
    ),
    "medium": RiskRule(
        min_etf_pct=70.0,
        max_thematic_pct=25.0,
        max_single_slice_pct=50.0,
        max_single_stock_pct=10.0,
    ),
    "high": RiskRule(
        min_etf_pct=50.0,
        max_thematic_pct=40.0,
        max_single_slice_pct=40.0,
        max_single_stock_pct=10.0,
    ),
}

MAX_SLICES = 8
MIN_SLICE_PCT = 5.0
PRACTICAL_MIN_AMOUNT = 1.0  # £


@dataclass
class AllocationSlice:
    candidate: ScoredPieCandidate
    allocation_pct: float
    amount: float


def _score_weighted_pcts(
    candidates: list[ScoredPieCandidate], budget_pct: float
) -> list[float]:
    """Distribute budget_pct proportionally by opportunity_score."""
    if not candidates:
        return []
    total_score = sum(c.opportunity_score for c in candidates)
    if total_score == 0:
        equal = budget_pct / len(candidates)
        return [equal] * len(candidates)
    return [(c.opportunity_score / total_score) * budget_pct for c in candidates]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _normalise_to_100(pcts: list[float]) -> list[float]:
    total = sum(pcts)
    if total == 0:
        return pcts
    return [p / total * 100 for p in pcts]


def _round_pcts(pcts: list[float]) -> list[float]:
    """Round to 1 dp and adjust last element so total == 100.0 exactly."""
    rounded = [round(p, 1) for p in pcts]
    diff = round(100.0 - sum(rounded), 1)
    if rounded:
        rounded[-1] = round(rounded[-1] + diff, 1)
    return rounded


def build_allocation(
    scored_candidates: list[ScoredPieCandidate],
    risk_level: str,
    total_amount: float,
) -> tuple[list[AllocationSlice], list[str]]:
    """
    Build final allocation from scored, validated candidates.
    Returns (slices, safety_flags).
    """
    rules = RISK_RULES.get(risk_level, RISK_RULES["medium"])
    safety_flags: list[str] = []

    etfs   = [c for c in scored_candidates if c.instrument_type == "ETF"]
    stocks = [c for c in scored_candidates if c.instrument_type == "STOCK"]

    # -- Select candidates ------------------------------------------------
    # Fill ETF slots first, then stocks up to max_slices
    max_stock_slots = max(0, int((100 - rules.min_etf_pct) / MIN_SLICE_PCT))
    max_etf_slots   = MAX_SLICES - min(len(stocks), max_stock_slots)

    selected_etfs   = etfs[:max_etf_slots]
    remaining_slots = MAX_SLICES - len(selected_etfs)
    selected_stocks = stocks[:min(remaining_slots, max_stock_slots)]

    selected = selected_etfs + selected_stocks

    if not selected:
        return [], ["No candidates passed scoring and validation filters."]

    # -- Distribute budget ------------------------------------------------
    etf_budget   = rules.min_etf_pct if selected_stocks else 100.0
    stock_budget = 100.0 - etf_budget

    etf_pcts   = _score_weighted_pcts(selected_etfs, etf_budget)
    stock_pcts = _score_weighted_pcts(selected_stocks, stock_budget)

    raw_pcts = etf_pcts + stock_pcts

    # -- Enforce single-slice caps ----------------------------------------
    for i, (c, pct) in enumerate(zip(selected, raw_pcts)):
        cap = (
            rules.max_single_stock_pct if c.instrument_type == "STOCK"
            else rules.max_single_slice_pct
        )
        if pct > cap:
            safety_flags.append(
                f"{c.ticker} capped at {cap}% (was {pct:.1f}%)"
            )
            raw_pcts[i] = cap

    # -- Re-normalise after capping ---------------------------------------
    raw_pcts = _normalise_to_100(raw_pcts)

    # -- Enforce minimum slice size --------------------------------------
    for i, (c, pct) in enumerate(zip(selected, raw_pcts)):
        if pct < MIN_SLICE_PCT:
            safety_flags.append(
                f"{c.ticker} removed: allocation {pct:.1f}% < {MIN_SLICE_PCT}% minimum"
            )
            raw_pcts[i] = 0.0

    # Filter out zeroed slices
    filtered = [(c, p) for c, p in zip(selected, raw_pcts) if p > 0]
    if not filtered:
        return [], safety_flags + ["All candidates fell below minimum slice size."]

    selected, raw_pcts = zip(*filtered)
    selected = list(selected)
    raw_pcts = list(raw_pcts)

    # Final normalise and round
    raw_pcts = _normalise_to_100(raw_pcts)
    raw_pcts = _round_pcts(raw_pcts)

    # -- Compute £ amounts -----------------------------------------------
    slices: list[AllocationSlice] = []
    for candidate, pct in zip(selected, raw_pcts):
        amount = round(total_amount * pct / 100, 2)
        if amount < PRACTICAL_MIN_AMOUNT:
            safety_flags.append(
                f"{candidate.ticker}: £{amount:.2f} below practical minimum — increase total amount"
            )
        slices.append(AllocationSlice(candidate=candidate, allocation_pct=pct, amount=amount))

    # Validate ETF % of result
    etf_actual_pct = sum(s.allocation_pct for s in slices if s.candidate.instrument_type == "ETF")
    if etf_actual_pct < rules.min_etf_pct - 1.0:  # 1% tolerance
        safety_flags.append(
            f"ETF allocation {etf_actual_pct:.1f}% is below {rules.min_etf_pct}% minimum for {risk_level} risk"
        )

    return slices, safety_flags
