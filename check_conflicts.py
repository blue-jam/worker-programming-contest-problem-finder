#!/usr/bin/env python3
"""Main CLI script to check problem conflicts against Kattis and CodeChef.

Usage:
    uv run python check_conflicts.py [--participants participants.txt] [--problems problems.json]
"""

import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
import sys
from typing import Dict, List, Set

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from src.fuzzy import CandidateUser, generate_candidate_ids
from src.kattis import KattisScraper
from src.codechef import CodeChefScraper
from src.matcher import ProblemConflictResult, evaluate_problem_conflicts, RiskStatus
from src.reporter import Reporter

# Setup rich console
console = Console()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check problem collisions on Kattis and CodeChef for contest problem selection.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-p", "--participants",
        type=Path,
        default=Path("participants.txt"),
        help="Path to participants list file (one AtCoder ID per line).",
    )
    parser.add_argument(
        "-q", "--problems",
        type=Path,
        default=Path("problems.json"),
        help="Path to candidate problems JSON file.",
    )
    parser.add_argument(
        "-d", "--delay",
        type=float,
        default=1.2,
        help="Base delay in seconds between scraping requests (jitter is automatically added).",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=25,
        help="Maximum number of fuzzy candidate usernames to generate per participant.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("result.json"),
        help="Path for output JSON results.",
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=Path("report.md"),
        help="Path for output markdown report.",
    )
    parser.add_argument(
        "--skip-kattis-solvers-check",
        action="store_true",
        help="Skip checking Kattis problem statistics page for solvers list.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose debug logging.",
    )
    return parser.parse_args()


def load_participants(path: Path) -> List[str]:
    """Load list of AtCoder IDs from text file."""
    if not path.exists():
        console.print(f"[bold yellow]Warning:[/bold yellow] {path} not found. Using default sample participants.")
        return ["chokudai", "tourist", "one_deepak"]

    participants: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            participants.append(line)
    return participants


def load_problems(path: Path) -> Dict[str, List[str]]:
    """Load candidate problems from JSON file."""
    if not path.exists():
        console.print(f"[bold yellow]Warning:[/bold yellow] {path} not found. Using default sample problems.")
        return {
            "kattis": ["bijele", "quadrant", "carrots", "cold", "non_existent_prob_xyz"],
            "codechef": ["FLOW001", "TEST", "MAXHAMDIST", "ANTIPALQ", "NON_EXISTENT_PROB_999"],
        }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "kattis": data.get("kattis", []),
            "codechef": data.get("codechef", []),
        }
    except json.JSONDecodeError as e:
        console.print(f"[bold red]Error parsing {path}:[/bold red] {e}")
        sys.exit(1)


def main():
    args = parse_arguments()

    # Logging setup
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )
    logger = logging.getLogger("conflict_checker")

    console.rule("[bold cyan]Programming Contest Problem Conflict Checker[/bold cyan]")
    console.print(f"Start time: [dim]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]")

    # 1. Load inputs
    participants = load_participants(args.participants)
    problems_map = load_problems(args.problems)
    kattis_problems = problems_map.get("kattis", [])
    codechef_problems = problems_map.get("codechef", [])

    console.print(f"[bold green]Participants ({len(participants)}):[/bold green] {', '.join(participants)}")
    console.print(f"[bold cyan]Kattis Problems ({len(kattis_problems)}):[/bold cyan] {', '.join(kattis_problems)}")
    console.print(f"[bold cyan]CodeChef Problems ({len(codechef_problems)}):[/bold cyan] {', '.join(codechef_problems)}")
    console.print()

    # 2. Generate Fuzzy Candidate User IDs
    all_candidates: List[CandidateUser] = []
    candidate_set_per_original: Dict[str, List[CandidateUser]] = {}
    for p in participants:
        cands = generate_candidate_ids(p, max_candidates=args.max_candidates)
        candidate_set_per_original[p] = cands
        all_candidates.extend(cands)

    # Deduplicate candidate usernames across participants (keeping highest similarity)
    unique_candidates: Dict[str, CandidateUser] = {}
    for c in all_candidates:
        u_lower = c.username.lower()
        if u_lower not in unique_candidates or (c.is_exact and not unique_candidates[u_lower].is_exact):
            unique_candidates[u_lower] = c

    distinct_candidates = list(unique_candidates.values())
    console.print(
        f"Generated [bold yellow]{len(distinct_candidates)}[/bold yellow] unique candidate usernames "
        f"across {len(participants)} participants."
    )
    console.print()

    # Initialize scrapers
    kattis_scraper = KattisScraper(base_delay=args.delay)
    codechef_scraper = CodeChefScraper(base_delay=args.delay)

    kattis_user_solved: Dict[CandidateUser, Set[str]] = {}
    codechef_user_solved: Dict[CandidateUser, Set[str]] = {}

    # 3. Scrape Kattis Users
    if kattis_problems:
        console.print("[bold cyan]Step 1/3: Checking accounts on Kattis...[/bold cyan]")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Checking Kattis...", total=len(distinct_candidates))
            for cand in distinct_candidates:
                progress.update(task, description=f"Kattis: Checking [bold]{cand.username}[/bold]")
                res = kattis_scraper.fetch_user(cand.username)
                if res.exists:
                    kattis_user_solved[cand] = set(res.solved_problems)
                progress.advance(task)

        # Dual-check: check problem statistics page for candidate problems to catch solves
        if not args.skip_kattis_solvers_check:
            console.print("[dim]Cross-referencing candidate problems against solver lists on Kattis...[/dim]")
            for prob in kattis_problems:
                solvers = kattis_scraper.fetch_problem_solvers(prob)
                for cand in distinct_candidates:
                    if cand.username.lower() in solvers:
                        if cand not in kattis_user_solved:
                            kattis_user_solved[cand] = set()
                        kattis_user_solved[cand].add(prob.lower())

    # 4. Scrape CodeChef Users
    if codechef_problems:
        console.print("\n[bold cyan]Step 2/3: Checking accounts on CodeChef...[/bold cyan]")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Checking CodeChef...", total=len(distinct_candidates))
            for cand in distinct_candidates:
                progress.update(task, description=f"CodeChef: Checking [bold]{cand.username}[/bold]")
                res = codechef_scraper.fetch_user(cand.username)
                if res.exists:
                    codechef_user_solved[cand] = set(res.solved_problems)
                progress.advance(task)

    # 5. Cross-reference conflicts
    console.print("\n[bold cyan]Step 3/3: Evaluating conflict risk levels...[/bold cyan]")
    all_results: List[ProblemConflictResult] = []

    # Evaluate Kattis
    for prob in kattis_problems:
        res = evaluate_problem_conflicts("Kattis", prob, kattis_user_solved)
        all_results.append(res)

    # Evaluate CodeChef
    for prob in codechef_problems:
        res = evaluate_problem_conflicts("CodeChef", prob, codechef_user_solved)
        all_results.append(res)

    # 6. Report outputs
    reporter = Reporter(console=console)
    reporter.print_console_summary(
        results=all_results,
        total_participants=len(participants),
        total_candidates=len(distinct_candidates),
    )

    reporter.write_json(
        output_path=args.output_json,
        results=all_results,
        metadata={
            "participants": participants,
            "total_candidates": len(distinct_candidates),
            "kattis_problems_count": len(kattis_problems),
            "codechef_problems_count": len(codechef_problems),
        },
    )
    console.print(f"[bold green]Saved JSON output to:[/bold green] {args.output_json}")

    reporter.write_markdown(
        output_path=args.output_report,
        results=all_results,
        participants=participants,
        total_candidates=len(distinct_candidates),
    )
    console.print(f"[bold green]Saved Markdown report to:[/bold green] {args.output_report}")
    console.print()


if __name__ == "__main__":
    main()
