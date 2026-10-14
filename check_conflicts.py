#!/usr/bin/env python3
"""Main CLI script to check problem conflicts against CodeChef and Kattis.

Supports both:
1. Manual candidate list evaluation (via problems.json)
2. Automatic problem candidate selection (--auto) across balanced AtCoder rating tiers (Brown to Red)
   primarily using CodeChef with automatic Kattis fallback.

Usage:
    # Auto-find balanced problems across Brown to Red levels:
    uv run python check_conflicts.py --auto

    # Specify 2 problems per tier (total 10 problems):
    uv run python check_conflicts.py --auto --count-per-tier 2

    # Manual mode checking existing problems.json:
    uv run python check_conflicts.py --problems problems.json
"""

import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
import sys
from typing import Dict, List, Optional, Set

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from src.fuzzy import CandidateUser, generate_candidate_ids
from src.kattis import KattisScraper
from src.codechef import CodeChefScraper
from src.matcher import ProblemConflictResult, evaluate_problem_conflicts, RiskStatus
from src.problem_fetcher import AutoProblemSelector, CandidateProblem, DEFAULT_TIERS, DifficultyTier
from src.reporter import Reporter

# Setup rich console
console = Console()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check problem collisions on CodeChef and Kattis for contest problem selection.",
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
        help="Path to candidate problems JSON file (used in manual mode).",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Automatically search and select conflict-free candidate problems across balanced difficulty tiers.",
    )
    parser.add_argument(
        "--count-per-tier",
        type=int,
        default=1,
        help="In --auto mode: number of SAFE problems to find per difficulty tier (default: 1, total 5 problems).",
    )
    parser.add_argument(
        "--include-kattis",
        action="store_true",
        help="In --auto mode: allow Kattis problems as supplement/fallback if CodeChef pool is insufficient.",
    )
    parser.add_argument(
        "--save-problems",
        type=Path,
        default=Path("problems.json"),
        help="In --auto mode: path to save the selected conflict-free problem set as JSON.",
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
        "-e", "--exact-only", "--exact",
        action="store_true",
        dest="exact_only",
        help="Only check exact participant usernames without fuzzy variations (avoids 429 rate limits and speeds up search).",
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
            "kattis": ["bijele", "quadrant", "carrots", "cold"],
            "codechef": ["FLOW001", "TEST", "MAXHAMDIST", "ANTIPALQ"],
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
    if args.auto:
        console.print("[bold green]Mode:[/bold green] Automatic Problem Finder across Balanced Tiers (茶色 〜 赤色)")
    else:
        console.print("[bold yellow]Mode:[/bold yellow] Manual Problem Evaluation (checking problems.json)")

    if args.exact_only:
        console.print("[bold cyan]Search Scope:[/bold cyan] Exact Usernames Only [green](Rate-limit safe: fuzzy variations disabled)[/green]")
    else:
        console.print(f"[bold cyan]Search Scope:[/bold cyan] Fuzzy Candidate Variations (up to {args.max_candidates} per participant)")

    # 1. Load participants
    participants = load_participants(args.participants)
    console.print(f"[bold green]Participants ({len(participants)}):[/bold green] {', '.join(participants)}")

    # 2. Generate Candidate User IDs
    all_candidates: List[CandidateUser] = []
    candidate_set_per_original: Dict[str, List[CandidateUser]] = {}
    for p in participants:
        cands = generate_candidate_ids(
            p,
            max_candidates=args.max_candidates,
            exact_only=args.exact_only,
        )
        candidate_set_per_original[p] = cands
        all_candidates.extend(cands)

    # Deduplicate candidate usernames across participants (keeping highest similarity)
    unique_candidates: Dict[str, CandidateUser] = {}
    for c in all_candidates:
        u_lower = c.username.lower()
        if u_lower not in unique_candidates or (c.is_exact and not unique_candidates[u_lower].is_exact):
            unique_candidates[u_lower] = c

    distinct_candidates = list(unique_candidates.values())
    if args.exact_only:
        console.print(
            f"Checking [bold green]{len(distinct_candidates)}[/bold green] exact participant username(s) "
            f"across {len(participants)} participant(s)."
        )
    else:
        console.print(
            f"Generated [bold yellow]{len(distinct_candidates)}[/bold yellow] unique candidate usernames "
            f"across {len(participants)} participants."
        )
    console.print()

    # Initialize scrapers
    kattis_scraper = KattisScraper(base_delay=args.delay)
    codechef_scraper = CodeChefScraper(base_delay=args.delay)

    codechef_user_solved: Dict[CandidateUser, Set[str]] = {}
    kattis_user_solved: Dict[CandidateUser, Set[str]] = {}

    # 3. Check CodeChef Accounts (Primary Platform)
    console.print("[bold cyan]Step 1/2: Checking participant accounts on CodeChef...[/bold cyan]")
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

    # Check Kattis if manual problems list has Kattis problems or auto mode allows Kattis
    should_check_kattis = False
    if not args.auto:
        manual_problems = load_problems(args.problems)
        if manual_problems.get("kattis"):
            should_check_kattis = True
    elif args.include_kattis:
        should_check_kattis = True

    if should_check_kattis:
        console.print("\n[bold cyan]Step 2/2: Checking participant accounts on Kattis...[/bold cyan]")
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

    all_results: List[ProblemConflictResult] = []

    # 4. Problem Evaluation
    if args.auto:
        console.print("\n[bold cyan]Step 2/2: Finding SAFE balanced problems across difficulty tiers...[/bold cyan]")
        selector = AutoProblemSelector(
            tiers=DEFAULT_TIERS,
            prefer_codechef=True,
            use_kattis_fallback=args.include_kattis,
        )

        selected_problems_for_export = {"codechef": [], "kattis": []}
        tested_codes: Set[str] = set()

        for tier in DEFAULT_TIERS:
            console.print(f"\n[bold magenta]Searching {tier.name}[/bold magenta] ({tier.atcoder_target})...")
            found_count = 0
            attempts = 0
            max_attempts = 40

            while found_count < args.count_per_tier and attempts < max_attempts:
                attempts += 1
                cand_prob = selector.get_next_candidate(tier, excluded_codes=tested_codes)
                if not cand_prob:
                    console.print(f"  [yellow]No more candidate problems found in {tier.name} pool.[/yellow]")
                    break

                tested_codes.add(cand_prob.code.lower())

                # Check conflict
                if cand_prob.platform == "codechef":
                    solved_map = codechef_user_solved
                    diff_info = f"Rating {cand_prob.rating}" if cand_prob.rating else "-"
                else:
                    solved_map = kattis_user_solved
                    diff_info = f"Diff {cand_prob.kattis_diff:.1f}" if cand_prob.kattis_diff else "-"

                res = evaluate_problem_conflicts(
                    platform=cand_prob.platform.capitalize(),
                    problem_id=cand_prob.code,
                    user_solved_map=solved_map,
                    problem_name=cand_prob.name,
                    tier=tier.tier,
                    tier_name=tier.name,
                    atcoder_target=tier.atcoder_target,
                    difficulty_info=diff_info,
                    url=cand_prob.url,
                )

                if res.status == RiskStatus.SAFE:
                    all_results.append(res)
                    found_count += 1
                    selected_problems_for_export[cand_prob.platform].append(cand_prob.code)
                    console.print(
                        f"  [bold green]✓ SAFE:[/bold green] [{cand_prob.platform}] "
                        f"[bold]{cand_prob.name}[/bold] (`{cand_prob.code}`, {diff_info}) "
                        f"[dim]({found_count}/{args.count_per_tier})[/dim]"
                    )
                else:
                    status_badge = "[red]COLLISION[/red]" if res.status == RiskStatus.COLLISION else "[yellow]SUSPICIOUS[/yellow]"
                    console.print(
                        f"  [dim]✗ {status_badge}: [{cand_prob.platform}] `{cand_prob.code}` "
                        f"skipped ({res.details_string})[/dim]"
                    )

            if found_count < args.count_per_tier:
                console.print(
                    f"  [bold yellow]Notice:[/bold yellow] Found {found_count}/{args.count_per_tier} safe problems for {tier.name}."
                )

        # Save selected problems to JSON for future use
        if args.save_problems:
            args.save_problems.write_text(
                json.dumps(selected_problems_for_export, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            console.print(f"\n[bold green]Saved auto-selected problem set to:[/bold green] {args.save_problems}")

    else:
        # Manual Mode
        console.print("\n[bold cyan]Step 2/2: Evaluating conflict risk levels for provided problems...[/bold cyan]")
        manual_problems = load_problems(args.problems)
        kattis_problems = manual_problems.get("kattis", [])
        codechef_problems = manual_problems.get("codechef", [])

        # Evaluate Kattis
        for prob in kattis_problems:
            res = evaluate_problem_conflicts("Kattis", prob, kattis_user_solved)
            all_results.append(res)

        # Evaluate CodeChef
        for prob in codechef_problems:
            res = evaluate_problem_conflicts("CodeChef", prob, codechef_user_solved)
            all_results.append(res)

    # 5. Report outputs
    reporter = Reporter(console=console)
    reporter.print_console_summary(
        results=all_results,
        total_participants=len(participants),
        total_candidates=len(distinct_candidates),
        exact_only=args.exact_only,
    )

    reporter.write_json(
        output_path=args.output_json,
        results=all_results,
        metadata={
            "participants": participants,
            "total_candidates": len(distinct_candidates),
            "exact_only": args.exact_only,
            "mode": "auto" if args.auto else "manual",
            "tier_count": args.count_per_tier if args.auto else None,
        },
    )
    console.print(f"[bold green]Saved JSON output to:[/bold green] {args.output_json}")

    reporter.write_markdown(
        output_path=args.output_report,
        results=all_results,
        participants=participants,
        total_candidates=len(distinct_candidates),
        exact_only=args.exact_only,
    )
    console.print(f"[bold green]Saved Markdown report to:[/bold green] {args.output_report}")
    console.print()


if __name__ == "__main__":
    main()
