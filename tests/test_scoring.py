from etf_theme_radar.models import ThemeMetrics
from etf_theme_radar.scoring import opportunity_score, white_space_score
def test_score_is_deterministic_and_gated():
    m=ThemeMetrics("t", {"research_momentum":100}, ("official",), 1, 2, ())
    assert opportunity_score(m)["confidence"] == "low"
    assert opportunity_score(m)["opportunity_score"] == 20
def test_white_space(): assert white_space_score([.2,.8]) == 20

