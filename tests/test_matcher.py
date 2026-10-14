from src.fuzzy import CandidateUser
from src.matcher import evaluate_problem_conflicts, RiskStatus

def test_matcher_safe():
    candidate = CandidateUser(
        username="user_a",
        original_id="user_a",
        is_exact=True,
        match_type="exact",
        similarity=1.0,
    )
    user_map = {candidate: {"prob1", "prob2"}}
    res = evaluate_problem_conflicts("Kattis", "prob3", user_map)
    assert res.status == RiskStatus.SAFE
    assert len(res.conflicts) == 0
    assert res.details_string == "-"

def test_matcher_collision():
    candidate = CandidateUser(
        username="user_a",
        original_id="user_a",
        is_exact=True,
        match_type="exact",
        similarity=1.0,
    )
    user_map = {candidate: {"prob1", "prob2"}}
    res = evaluate_problem_conflicts("Kattis", "prob1", user_map)
    assert res.status == RiskStatus.COLLISION
    assert len(res.conflicts) == 1
    assert "Exact Match" in res.conflicts[0].formatted_detail

def test_matcher_suspicious():
    candidate = CandidateUser(
        username="user_a_",
        original_id="user_a",
        is_exact=False,
        match_type="symbol_suffix",
        similarity=0.9,
    )
    user_map = {candidate: {"prob1"}}
    res = evaluate_problem_conflicts("CodeChef", "prob1", user_map)
    assert res.status == RiskStatus.SUSPICIOUS
    assert len(res.conflicts) == 1
    assert "Origin: user_a" in res.conflicts[0].formatted_detail
