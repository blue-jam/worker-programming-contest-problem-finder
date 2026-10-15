"""Module for loading team configurations, participant ratings, and platform handles.

Supports reading teams CSV/text files and participant handle lists without hardcoding.
"""

from dataclasses import dataclass, field
import csv
import logging
from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class TeamMember:
    team_id: str
    atcoder_id: str
    group: str  # e.g., "G1", "G2", "G3", "G4"
    max_rating: int
    current_rating: int
    codechef_id: Optional[str] = None


@dataclass
class GroupStats:
    group_name: str
    members: List[TeamMember]
    min_rating: int
    max_rating: int
    avg_rating: float
    median_rating: float


@dataclass
class TeamConfig:
    teams: Dict[str, List[TeamMember]]  # team_id -> members
    members: List[TeamMember]
    groups: Dict[str, GroupStats]  # group_name -> stats
    all_codechef_handles: List[str]


def parse_teams_file(path: Path) -> List[TeamMember]:
    """Parse teams CSV or TSV or formatted text file."""
    if not path.exists():
        raise FileNotFoundError(f"Teams file not found: {path}")

    content = path.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]

    if not lines:
        return []

    # Detect delimiter
    first_line = lines[0]
    delimiter = "," if "," in first_line else ("\t" if "\t" in first_line else None)

    reader = csv.reader(lines, delimiter=delimiter) if delimiter else csv.reader(lines)
    header = [h.strip().lower() for h in next(reader)]

    # Map column positions
    col_team = -1
    col_atcoder = -1
    col_group = -1
    col_max_r = -1
    col_cur_r = -1

    for idx, col in enumerate(header):
        if any(k in col for k in ("チーム", "team")):
            col_team = idx
        elif any(k in col for k in ("atcoder", "user", "id", "handle")):
            col_atcoder = idx
        elif any(k in col for k in ("グループ", "group")):
            col_group = idx
        elif any(k in col for k in ("最高", "max", "highest")):
            col_max_r = idx
        elif any(k in col for k in ("現在", "current", "rating", "レート")):
            col_cur_r = idx

    # Fallbacks if columns were not matched by header text
    if col_atcoder == -1 and len(header) >= 2:
        col_atcoder = 1
    if col_team == -1 and len(header) >= 1:
        col_team = 0
    if col_group == -1 and len(header) >= 3:
        col_group = 2
    if col_cur_r == -1 and len(header) >= 5:
        col_cur_r = 4
    elif col_cur_r == -1 and len(header) >= 4:
        col_cur_r = 3

    members: List[TeamMember] = []
    for row in reader:
        if not row or len(row) <= max(col_atcoder, col_team):
            continue

        team_id = row[col_team].strip() if col_team != -1 and col_team < len(row) else "1"
        atcoder_id = row[col_atcoder].strip() if col_atcoder != -1 and col_atcoder < len(row) else ""
        if not atcoder_id:
            continue

        group = row[col_group].strip() if col_group != -1 and col_group < len(row) else "G1"

        def _parse_int(val: str, default: int = 1500) -> int:
            nums = re.findall(r"\d+", val)
            return int(nums[0]) if nums else default

        cur_r = _parse_int(row[col_cur_r]) if col_cur_r != -1 and col_cur_r < len(row) else 1500
        max_r = _parse_int(row[col_max_r]) if col_max_r != -1 and col_max_r < len(row) else cur_r

        member = TeamMember(
            team_id=team_id,
            atcoder_id=atcoder_id,
            group=group,
            max_rating=max_r,
            current_rating=cur_r,
        )
        members.append(member)

    return members


def load_participants_handles(path: Optional[Path]) -> List[str]:
    """Load explicit CodeChef or contest platform handles from text file."""
    if not path or not path.exists():
        return []

    handles: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            handles.append(line)
    return handles


def build_team_config(
    teams_path: Path,
    participants_path: Optional[Path] = None,
) -> TeamConfig:
    """Load and correlate team members and platform handles dynamically."""
    members = parse_teams_file(teams_path)
    explicit_handles = load_participants_handles(participants_path)

    # Match explicit CodeChef handles with AtCoder members
    # Case-insensitive and normalized check
    matched_handles: Set[str] = set()
    explicit_map = {h.lower(): h for h in explicit_handles}

    for m in members:
        at_clean = m.atcoder_id.lower().replace("_", "").replace("-", "")
        # 1. Exact match
        if m.atcoder_id.lower() in explicit_map:
            h = explicit_map[m.atcoder_id.lower()]
            m.codechef_id = h
            matched_handles.add(h)
        else:
            # 2. Normalized prefix/suffix match (e.g., fuppy0716 -> fuppy, haruki4936 -> haruki_k)
            for raw_h in explicit_handles:
                h_clean = raw_h.lower().replace("_", "").replace("-", "")
                if (h_clean in at_clean or at_clean in h_clean) and len(h_clean) >= 4:
                    m.codechef_id = raw_h
                    matched_handles.add(raw_h)
                    break

        if not m.codechef_id:
            # Default to AtCoder ID as primary candidate on CodeChef
            m.codechef_id = m.atcoder_id

    # Collect all unique handles to check on platform
    all_handles: List[str] = []
    seen = set()

    # Add all explicit handles first
    for h in explicit_handles:
        if h.lower() not in seen:
            seen.add(h.lower())
            all_handles.append(h)

    # Add any remaining member IDs
    for m in members:
        if m.codechef_id and m.codechef_id.lower() not in seen:
            seen.add(m.codechef_id.lower())
            all_handles.append(m.codechef_id)
        if m.atcoder_id.lower() not in seen:
            seen.add(m.atcoder_id.lower())
            all_handles.append(m.atcoder_id)

    # Organize by teams
    teams: Dict[str, List[TeamMember]] = {}
    for m in members:
        teams.setdefault(m.team_id, []).append(m)

    # Organize and compute stats by groups
    groups_dict: Dict[str, List[TeamMember]] = {}
    for m in members:
        groups_dict.setdefault(m.group, []).append(m)

    group_stats: Dict[str, GroupStats] = {}
    for g_name, g_members in groups_dict.items():
        ratings = [m.current_rating for m in g_members]
        ratings.sort()
        mid = len(ratings) // 2
        median = (ratings[mid] if len(ratings) % 2 != 0 else (ratings[mid - 1] + ratings[mid]) / 2) if ratings else 1500
        group_stats[g_name] = GroupStats(
            group_name=g_name,
            members=g_members,
            min_rating=min(ratings) if ratings else 0,
            max_rating=max(ratings) if ratings else 0,
            avg_rating=sum(ratings) / len(ratings) if ratings else 0.0,
            median_rating=median,
        )

    return TeamConfig(
        teams=teams,
        members=members,
        groups=group_stats,
        all_codechef_handles=all_handles,
    )
