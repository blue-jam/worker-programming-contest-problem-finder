"""Tests for team loading and simultaneous-coding contest planner."""

from pathlib import Path
import pytest
from src.team_loader import build_team_config, parse_teams_file
from src.contest_planner import (
    DEFAULT_11_PROBLEM_SPECS,
    simulate_contest,
)


def test_team_loader():
    teams_path = Path("teams.csv")
    if not teams_path.exists():
        teams_path = Path("teams.txt")

    config = build_team_config(teams_path, Path("participants.txt"))
    assert len(config.teams) == 9
    assert len(config.members) == 36
    assert "G1" in config.groups
    assert "G2" in config.groups
    assert "G3" in config.groups
    assert "G4" in config.groups
    assert len(config.groups["G1"].members) == 9
    assert len(config.all_codechef_handles) > 0


def test_contest_simulation_constraints():
    teams_path = Path("teams.csv")
    if not teams_path.exists():
        teams_path = Path("teams.txt")

    config = build_team_config(teams_path, Path("participants.txt"))
    res = simulate_contest(
        team_config=config,
        specs=DEFAULT_11_PROBLEM_SPECS,
        contest_duration=90,
        all_solved_limit=75,
    )

    # Condition 1: All members can solve at least 1 problem
    assert res.all_members_can_solve_at_least_one is True

    # Condition 2: No member runs out of problems within 90 min
    assert res.no_idle_members_within_duration is True

    # Condition 3: No team fully solves all problems within 75 min
    assert res.no_all_solved_before_limit is True
    assert res.min_time_to_all_solved >= 90
