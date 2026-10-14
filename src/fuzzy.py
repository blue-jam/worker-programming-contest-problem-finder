"""Fuzzy ID generator module.

Generates plausible username variations across platforms based on AtCoder IDs.
"""

from dataclasses import dataclass
import difflib
import re
from typing import Dict, List, Set


@dataclass(frozen=True)
class CandidateUser:
    username: str
    original_id: str
    is_exact: bool
    match_type: str
    similarity: float


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def compute_similarity(s1: str, s2: str) -> float:
    """Compute string similarity ratio between 0.0 and 1.0."""
    # Combine Levenshtein-based and SequenceMatcher ratio
    dist = levenshtein_distance(s1.lower(), s2.lower())
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    lev_ratio = 1.0 - (dist / max_len)
    seq_ratio = difflib.SequenceMatcher(None, s1.lower(), s2.lower()).ratio()
    return round((lev_ratio + seq_ratio) / 2.0, 3)


def generate_candidate_ids(
    original_id: str,
    include_levenshtein: bool = True,
    max_candidates: int = 50,
    exact_only: bool = False,
) -> List[CandidateUser]:
    """Generate candidate usernames across platforms based on original AtCoder ID.

    Variations include:
    - Exact match (case variations: lower, upper, title)
    - Prefix/suffix symbols (_, -, .)
    - Common developer/CP suffixes (_dev, -dev, _cp, -cp)
    - Numeric modifications (append 0/1/2, strip trailing digits)
    - Levenshtein distance 1~2 typos and common keyboard slips

    If exact_only is True, returns only the exact original ID.
    """
    cleaned = original_id.strip()
    if not cleaned:
        return []

    if exact_only:
        return [
            CandidateUser(
                username=cleaned,
                original_id=cleaned,
                is_exact=True,
                match_type="exact",
                similarity=1.0,
            )
        ]

    candidates: Dict[str, CandidateUser] = {}

    def add_candidate(username: str, is_exact: bool, match_type: str):
        u = username.strip()
        if not u or len(u) < 2:
            return
        sim = 1.0 if is_exact else compute_similarity(cleaned, u)
        # Avoid very low similarity noise unless it's a direct rule variant
        if not is_exact and sim < 0.50:
            return

        # If already present, keep exact or higher similarity
        if u in candidates:
            existing = candidates[u]
            if existing.is_exact:
                return
            if is_exact or sim > existing.similarity:
                candidates[u] = CandidateUser(
                    username=u,
                    original_id=cleaned,
                    is_exact=is_exact,
                    match_type=match_type,
                    similarity=sim,
                )
        else:
            candidates[u] = CandidateUser(
                username=u,
                original_id=cleaned,
                is_exact=is_exact,
                match_type=match_type,
                similarity=sim,
            )

    # 1. Exact match (case variations)
    add_candidate(cleaned, is_exact=True, match_type="exact")
    add_candidate(cleaned.lower(), is_exact=True, match_type="exact_lower")
    if cleaned != cleaned.lower():
        add_candidate(cleaned.title(), is_exact=True, match_type="exact_title")

    lower = cleaned.lower()

    # 2. High-priority Symbol Variations: Swap _ and - (very common across platforms like Kattis vs AtCoder)
    if "_" in lower:
        add_candidate(lower.replace("_", "-"), is_exact=False, match_type="symbol_swap")
        add_candidate(lower.replace("_", ""), is_exact=False, match_type="symbol_removed")
    if "-" in lower:
        add_candidate(lower.replace("-", "_"), is_exact=False, match_type="symbol_swap")
        add_candidate(lower.replace("-", ""), is_exact=False, match_type="symbol_removed")

    # Stripped symbols
    stripped = re.sub(r"^[_.\-]+|[_.\-]+$", "", lower)
    if stripped and stripped != lower:
        add_candidate(stripped, is_exact=False, match_type="symbol_stripped")

    # 3. Numeric modifications (common variations)
    # If ends with digits, try removing them
    m = re.search(r"^(.*?)(\d+)$", lower)
    if m:
        base, num_str = m.group(1), m.group(2)
        if base:
            add_candidate(base, is_exact=False, match_type="number_removed")
            val = int(num_str)
            for diff in [-1, 1]:
                if val + diff >= 0:
                    add_candidate(f"{base}{val + diff}", is_exact=False, match_type="number_shifted")
    else:
        # Add small digits commonly appended
        for digit in ["1", "0", "2"]:
            add_candidate(f"{lower}{digit}", is_exact=False, match_type="number_appended")
            add_candidate(f"{lower}_{digit}", is_exact=False, match_type="number_appended")

    # 4. Common CP/Dev tags and Handle prefixes
    for tag in ["dev", "cp"]:
        add_candidate(f"{lower}_{tag}", is_exact=False, match_type=f"suffix_{tag}")
        add_candidate(f"{lower}-{tag}", is_exact=False, match_type=f"suffix_{tag}")

    for pref in ["one", "real", "the"]:
        add_candidate(f"{pref}_{lower}", is_exact=False, match_type=f"prefix_{pref}")
        add_candidate(f"{pref}-{lower}", is_exact=False, match_type=f"prefix_{pref}")

    # 5. Affix symbols (_, -, .)
    for p in ["_", "-", "."]:
        add_candidate(f"{p}{lower}", is_exact=False, match_type="symbol_prefix")
        add_candidate(f"{lower}{p}", is_exact=False, match_type="symbol_suffix")


    # 4. Levenshtein variations (distance 1~2: single deletion, double letter, transposition)
    if include_levenshtein and len(lower) >= 3:
        # Deletions of single char
        for i in range(len(lower)):
            var = lower[:i] + lower[i + 1:]
            if len(var) >= 3:
                add_candidate(var, is_exact=False, match_type="char_deleted")

        # Adjacent transpositions
        for i in range(len(lower) - 1):
            var = lower[:i] + lower[i + 1] + lower[i] + lower[i + 2:]
            add_candidate(var, is_exact=False, match_type="char_transposed")

        # Duplicate character (or deduplicate consecutive duplicate)
        for i in range(len(lower)):
            var = lower[:i] + lower[i] + lower[i:]
            add_candidate(var, is_exact=False, match_type="char_duplicated")

        # Common vowel substitution/omission
        vowels = "aeiou"
        no_vowels = re.sub(r"[aeiou]", "", lower[1:])
        if len(no_vowels) >= 3:
            add_candidate(lower[0] + no_vowels, is_exact=False, match_type="vowels_dropped")

    # Sort results: exact first, then by priority tier, then similarity descending
    def get_tier(match_type: str) -> int:
        if match_type.startswith("exact"):
            return 5
        if match_type in ("symbol_swap", "symbol_stripped"):
            return 4
        if match_type in ("number_removed", "number_shifted", "number_appended"):
            return 3
        if match_type in ("symbol_prefix", "symbol_suffix"):
            return 2
        return 1

    res = list(candidates.values())
    res.sort(key=lambda c: (get_tier(c.match_type), c.similarity), reverse=True)

    if max_candidates and len(res) > max_candidates:
        # Always keep exact matches up to max_candidates + top candidates
        exacts = [c for c in res if c.is_exact]
        fuzzies = [c for c in res if not c.is_exact]
        remaining = max(0, max_candidates - len(exacts))
        res = exacts[:max_candidates] if remaining == 0 else exacts + fuzzies[:remaining]

    return res
