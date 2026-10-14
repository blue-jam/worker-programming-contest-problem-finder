#!/usr/bin/env python3
"""CLI utility to automatically fetch balanced contest problem candidates across difficulty tiers.

Primarily uses CodeChef, falling back to Kattis if specified or if pool is insufficient.

Usage:
    # Generate 1 problem per tier (5 problems across Brown to Red levels) to problems.json:
    uv run python find_problems.py

    # Generate 2 problems per tier (10 problems) with Kattis supplement:
    uv run python find_problems.py --count-per-tier 2 --include-kattis --output problems.json
"""

import argparse
import json
import logging
from pathlib import Path
from rich.console import Console
from rich.table import Table

from src.problem_fetcher import AutoProblemSelector, DEFAULT_TIERS

console = Console()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Auto-fetch balanced programming contest problems across AtCoder Brown to Red rating tiers."
    )
    parser.add_argument(
        "--count-per-tier",
        type=int,
        default=1,
        help="Number of problem candidates to select per tier (default: 1).",
    )
    parser.add_argument(
        "--include-kattis",
        action="store_true",
        help="Include/fallback to Kattis problems if CodeChef pool is insufficient.",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("problems.json"),
        help="Output path for problems JSON file.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    console.rule("[bold cyan]Automatic Contest Problem Candidate Finder[/bold cyan]")
    console.print(f"Finding [bold yellow]{args.count_per_tier}[/bold yellow] problem(s) for each of the 5 difficulty tiers (AtCoder 茶色 〜 赤色)...")

    selector = AutoProblemSelector(
        tiers=DEFAULT_TIERS,
        prefer_codechef=True,
        use_kattis_fallback=args.include_kattis,
    )

    selected_problems = {"codechef": [], "kattis": []}
    table = Table(title="Selected Balanced Problem Set")
    table.add_column("Tier", style="magenta")
    table.add_column("Target Level", style="cyan")
    table.add_column("Platform", style="dim")
    table.add_column("Problem Name", style="bold white")
    table.add_column("Code", style="green")
    table.add_column("Rating / Diff", justify="right", style="yellow")
    table.add_column("URL", style="dim")

    for tier in DEFAULT_TIERS:
        pool = selector.get_candidate_pool_for_tier(tier)
        picked = pool[:args.count_per_tier]
        for prob in picked:
            selected_problems[prob.platform].append(prob.code)
            diff_str = f"Rating {prob.rating}" if prob.rating else f"Diff {prob.kattis_diff:.1f}"
            table.add_row(
                tier.name,
                tier.atcoder_target,
                prob.platform.capitalize(),
                prob.name,
                prob.code,
                diff_str,
                prob.url,
            )

    console.print()
    console.print(table)
    console.print()

    args.output.write_text(
        json.dumps(selected_problems, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    console.print(f"[bold green]Successfully saved candidate problems to:[/bold green] {args.output}")


if __name__ == "__main__":
    main()
