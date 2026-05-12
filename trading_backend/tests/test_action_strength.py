from services.action_strength_engine import (
    calculate_buy_action_strength,
    calculate_sell_action_strength,
)
from models.schemas import label_for_action_strength


def test_buy_action_strength_high_enables_review_threshold():
    score = calculate_buy_action_strength(90, 85, 80)
    assert score >= 70


def test_buy_action_strength_clamps_to_range():
    score = calculate_buy_action_strength(300, 300, 300)
    assert score == 100


def test_sell_action_strength_clamps_to_range():
    score = calculate_sell_action_strength(-20, -30, -10, -50)
    assert score == 0


def test_label_bands():
    assert label_for_action_strength(10) == "Ignore"
    assert label_for_action_strength(35) == "Watch Only"
    assert label_for_action_strength(55) == "Review"
    assert label_for_action_strength(72) == "Strong Review"
    assert label_for_action_strength(90) == "High-Priority Review"
