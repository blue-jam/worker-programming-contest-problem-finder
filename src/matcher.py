"""Conflict matching engine module.

Cross-references candidate problems against participants and their fuzzy username variations.
Evaluates risk levels: SAFE, SUSPICIOUS, COLLISION.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set
from src.fuzzy import CandidateUser


class RiskStatus(str, Enum):
    SAFE = "SAFE"
    SUSPICIOUS = "SUSPICIOUS"
    COLLISION = "COLLISION"


@dataclass
class ConflictDetail:
    username: str
    original_id: str
    is_exact: bool
    similarity: float
    match_type: str
    formatted_detail: str


@dataclass
class ProblemConflictResult:
    platform: str
    problem_id: str
    status: RiskStatus
    conflicts: List[ConflictDetail] = field(default_factory=list)
    problem_name: str = ""
    tier: Optional[int] = None
    tier_name: str = ""
    atcoder_target: str = ""
    difficulty_info: str = ""
    url: str = ""

    @property
    def details_string(self) -> str:
        """Format conflict details for display in report."""
        if not self.conflicts:
            return "-"
        # Sort conflicts: exact first, then highest similarity
        sorted_conflicts = sorted(
            self.conflicts,
            key=lambda c: (1 if c.is_exact else 0, c.similarity),
            reverse=True,
        )
        return ", ".join(c.formatted_detail for c in sorted_conflicts)


def evaluate_problem_conflicts(
    platform: str,
    problem_id: str,
    user_solved_map: Dict[CandidateUser, Set[str]],
    problem_name: str = "",
    tier: Optional[int] = None,
    tier_name: str = "",
    atcoder_target: str = "",
    difficulty_info: str = "",
    url: str = "",
) -> ProblemConflictResult:
    """Evaluate conflict risk for a specific problem given candidate users and their solved problems.

    user_solved_map: mapping from CandidateUser -> set of solved problem identifiers.
    """
    conflicts: List[ConflictDetail] = []
    target = problem_id.strip()
    target_lower = target.lower()

    for candidate, solved_set in user_solved_map.items():
        # Check case-insensitive match against solved problem set
        solved_lower = {p.lower() for p in solved_set}
        if target_lower in solved_lower:
            if candidate.is_exact:
                formatted = f"{candidate.original_id} (Exact Match)"
            else:
                formatted = (
                    f"{candidate.username} (Origin: {candidate.original_id}, "
                    f"Similarity: {candidate.similarity:.2f}, {candidate.match_type})"
                )

            conflicts.append(
                ConflictDetail(
                    username=candidate.username,
                    original_id=candidate.original_id,
                    is_exact=candidate.is_exact,
                    similarity=candidate.similarity,
                    match_type=candidate.match_type,
                    formatted_detail=formatted,
                )
            )

    # Determine status
    if any(c.is_exact for c in conflicts):
        status = RiskStatus.COLLISION
    elif conflicts:
        status = RiskStatus.SUSPICIOUS
    else:
        status = RiskStatus.SAFE

    return ProblemConflictResult(
        platform=platform,
        problem_id=problem_id,
        status=status,
        conflicts=conflicts,
        problem_name=problem_name,
        tier=tier,
        tier_name=tier_name,
        atcoder_target=atcoder_target,
        difficulty_info=difficulty_info,
        url=url,
    )
