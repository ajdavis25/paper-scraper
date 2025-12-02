import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from filters import score_paper


def test_author_initial_matches_full_name():
    prefs = {"authors": ["A. Davis"]}
    score, details = score_paper("New paper", "abstract text", ["Ashton Davis"], prefs)
    assert "A. Davis" in details["matched_authors"]
    assert score >= 3.0


def test_full_name_matches_initial_author():
    prefs = {"authors": ["Ashton Davis"]}
    score, details = score_paper("Title", "abstract text", ["A. Davis"], prefs)
    assert "Ashton Davis" in details["matched_authors"]
    assert score >= 3.0


def test_author_weight_outweighs_keywords():
    kw_prefs = {"any_keywords": ["black hole", "jet"]}
    kw_score, kw_details = score_paper("Title", "black hole jet", [], kw_prefs)
    assert kw_details["any_hits"] == 2
    author_prefs = {"authors": ["Ashton Davis"]}
    author_score, _ = score_paper("Title", "no keywords here", ["Ashton Davis"], author_prefs)
    assert author_score > kw_score
