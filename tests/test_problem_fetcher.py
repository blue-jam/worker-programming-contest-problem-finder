"""Tests for problem_fetcher module."""

from unittest.mock import MagicMock, patch
import pytest

from src.problem_fetcher import (
    AutoProblemSelector,
    CandidateProblem,
    CodeChefProblemFetcher,
    DEFAULT_TIERS,
    DifficultyTier,
    KattisProblemFetcher,
)
from src.matcher import ProblemConflictResult, RiskStatus
from src.reporter import Reporter


def test_default_tiers_structure():
    """Verify DEFAULT_TIERS coverage and monotonic rating order."""
    assert len(DEFAULT_TIERS) == 5
    for i in range(len(DEFAULT_TIERS) - 1):
        assert DEFAULT_TIERS[i].tier < DEFAULT_TIERS[i + 1].tier
        assert DEFAULT_TIERS[i].codechef_min_rating < DEFAULT_TIERS[i + 1].codechef_min_rating
        assert DEFAULT_TIERS[i].kattis_min_diff < DEFAULT_TIERS[i + 1].kattis_min_diff


def test_codechef_problem_fetcher():
    """Test CodeChef candidate problem parsing and rating filtering with mock."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "success",
        "data": [
            {
                "code": "PROB_EASY",
                "name": "Easy Problem",
                "difficulty_rating": "1250",
                "distinct_successful_submissions": "500",
            },
            {
                "code": "PROB_HARD",
                "name": "Hard Problem",
                "difficulty_rating": "2600",
                "distinct_successful_submissions": "80",
            },
            {
                "code": "PROB_INVALID",
                "name": "Unrated",
                "difficulty_rating": "-1",
                "distinct_successful_submissions": "20",
            },
            {
                "code": "PROB_TOO_FEW_SOLVES",
                "name": "Obscure Problem",
                "difficulty_rating": "1250",
                "distinct_successful_submissions": "2",  # Less than min_solves=15
            },
        ],
    }
    mock_session.get.return_value = mock_resp

    fetcher = CodeChefProblemFetcher(session=mock_session)
    tier1 = DEFAULT_TIERS[0]  # Tier 1 (1000 - 1399)

    candidates = fetcher.fetch_tier_candidates(tier=tier1, min_solves=15, sample_pages=1)
    assert len(candidates) == 1
    prob = candidates[0]
    assert prob.platform == "codechef"
    assert prob.code == "PROB_EASY"
    assert prob.rating == 1250
    assert prob.tier == 1


def test_kattis_problem_fetcher():
    """Test Kattis candidate problem parsing and difficulty filtering with mock."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = """
    <html><body>
    <table class="table2"><tr><th>Header</th></tr></table>
    <table class="table2">
        <tr><th>Name</th><th>Fastest</th><th>Shortest</th><th>Authors</th><th>Full Solves</th><th>Ratio</th><th>Difficulty</th></tr>
        <tr>
            <td><a href="/problems/kattis_prob1">Kattis Problem 1</a></td>
            <td>0.01</td><td>100</td><td>100</td><td>250</td><td>50%</td><td>2.2 Easy</td>
        </tr>
        <tr>
            <td><a href="/problems/kattis_prob_hard">Kattis Hard Problem</a></td>
            <td>0.05</td><td>200</td><td>200</td><td>15</td><td>10%</td><td>7.5 Hard</td>
        </tr>
    </table>
    </body></html>
    """
    mock_session.get.return_value = mock_resp

    fetcher = KattisProblemFetcher(session=mock_session)
    tier1 = DEFAULT_TIERS[0]  # Kattis diff: 1.8 - 2.8

    candidates = fetcher.fetch_tier_candidates(tier=tier1, min_solves=10)
    assert len(candidates) == 1
    prob = candidates[0]
    assert prob.platform == "kattis"
    assert prob.code == "kattis_prob1"
    assert prob.kattis_diff == 2.2
    assert prob.tier == 1


def test_auto_problem_selector_next_candidate():
    """Test AutoProblemSelector returns next available candidate excluding seen ones."""
    tier1 = DEFAULT_TIERS[0]
    selector = AutoProblemSelector(tiers=[tier1], use_kattis_fallback=False)

    # Pre-populate pool with mock problems
    selector._pools[1] = [
        CandidateProblem(platform="codechef", code="PROB1", name="P1", tier=1, tier_name="Tier 1", atcoder_target="茶色"),
        CandidateProblem(platform="codechef", code="PROB2", name="P2", tier=1, tier_name="Tier 1", atcoder_target="茶色"),
    ]

    p1 = selector.get_next_candidate(tier1, excluded_codes=set())
    assert p1 is not None
    assert p1.code == "PROB1"

    p2 = selector.get_next_candidate(tier1, excluded_codes={"prob1"})
    assert p2 is not None
    assert p2.code == "PROB2"

    p_none = selector.get_next_candidate(tier1, excluded_codes={"prob1", "prob2"})
    assert p_none is None


def test_reporter_markdown_and_json_with_tiers(tmp_path):
    """Test Reporter correctly writes tier and rating metadata to markdown and json."""
    reporter = Reporter()
    results = [
        ProblemConflictResult(
            platform="CodeChef",
            problem_id="FLOW001",
            status=RiskStatus.SAFE,
            problem_name="Add Two Numbers",
            tier=1,
            tier_name="Tier 1 (Easy)",
            atcoder_target="茶色相当",
            difficulty_info="Rating 1050",
            url="https://www.codechef.com/problems/FLOW001",
        )
    ]

    json_path = tmp_path / "result.json"
    reporter.write_json(json_path, results)
    assert json_path.exists()
    content_json = json_path.read_text()
    assert "FLOW001" in content_json
    assert "Tier 1 (Easy)" in content_json
    assert "Rating 1050" in content_json

    md_path = tmp_path / "report.md"
    reporter.write_markdown(md_path, results, participants=["chokudai"], total_candidates=5)
    assert md_path.exists()
    content_md = md_path.read_text()
    assert "Tier 1 (Easy)" in content_md
    assert "茶色相当" in content_md
    assert "Add Two Numbers" in content_md
    assert "Rating 1050" in content_md
    assert "SAFE" in content_md
