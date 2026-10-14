"""Reporter module.

Generates console summary (Rich), result.json, and report.md.
Supports balanced difficulty tier display when available.
"""

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from src.matcher import ProblemConflictResult, RiskStatus


class Reporter:
    def __init__(self, console: Console = None):
        self.console = console or Console()

    def print_console_summary(
        self,
        results: List[ProblemConflictResult],
        total_participants: int,
        total_candidates: int,
        exact_only: bool = False,
    ):
        """Print rich colored summary table to terminal."""
        has_tiers = any(r.tier is not None for r in results)

        table = Table(title="[bold blue]Problem Conflict Cross-Check Summary[/bold blue]")
        if has_tiers:
            table.add_column("Tier", style="magenta", no_wrap=True)
            table.add_column("Target Level", style="cyan")
            table.add_column("Platform", style="dim", no_wrap=True)
            table.add_column("Problem", style="bold white")
            table.add_column("Rating / Diff", justify="right", style="yellow")
            table.add_column("Status", justify="center")
            table.add_column("Conflict Details / Solvers", style="dim")
        else:
            table.add_column("Platform", style="cyan", no_wrap=True)
            table.add_column("Problem ID", style="bold white")
            table.add_column("Status", justify="center")
            table.add_column("Conflict Details / Users", style="dim")

        safe_cnt = 0
        suspicious_cnt = 0
        collision_cnt = 0

        # Sort by tier if present
        sorted_results = sorted(results, key=lambda r: (r.tier or 99, r.platform, r.problem_id))

        for r in sorted_results:
            if r.status == RiskStatus.SAFE:
                status_str = "[bold green]SAFE[/bold green]"
                safe_cnt += 1
            elif r.status == RiskStatus.SUSPICIOUS:
                status_str = "[bold yellow]SUSPICIOUS[/bold yellow]"
                suspicious_cnt += 1
            else:
                status_str = "[bold red on white]COLLISION[/bold red on white]"
                collision_cnt += 1

            if has_tiers:
                tier_str = f"Tier {r.tier}" if r.tier else "-"
                target_str = r.atcoder_target or "-"
                prob_title = f"{r.problem_name} ({r.problem_id})" if r.problem_name else r.problem_id
                diff_str = r.difficulty_info or "-"
                table.add_row(
                    tier_str,
                    target_str,
                    r.platform,
                    prob_title,
                    diff_str,
                    status_str,
                    r.details_string,
                )
            else:
                table.add_row(
                    r.platform,
                    r.problem_id,
                    status_str,
                    r.details_string,
                )

        self.console.print()
        self.console.print(table)
        self.console.print()

        mode_str = "Exact IDs Only" if exact_only else "Fuzzy Variations"
        summary_text = (
            f"[bold]Participants:[/bold] {total_participants} | "
            f"[bold]Accounts Checked:[/bold] {total_candidates} ({mode_str}) | "
            f"[bold green]Safe Problems:[/bold green] {safe_cnt} | "
            f"[bold yellow]Suspicious Problems:[/bold yellow] {suspicious_cnt} | "
            f"[bold red]Collision Problems:[/bold red] {collision_cnt}"
        )
        self.console.print(Panel(summary_text, title="Overall Verdict", expand=False))

    def write_json(
        self,
        output_path: Path,
        results: List[ProblemConflictResult],
        metadata: Dict[str, Any] = None,
    ):
        """Write structured result to JSON file."""
        data = {
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
            "summary": {
                "total_problems": len(results),
                "safe_count": sum(1 for r in results if r.status == RiskStatus.SAFE),
                "suspicious_count": sum(1 for r in results if r.status == RiskStatus.SUSPICIOUS),
                "collision_count": sum(1 for r in results if r.status == RiskStatus.COLLISION),
            },
            "problems": [
                {
                    "platform": r.platform,
                    "problem_id": r.problem_id,
                    "problem_name": r.problem_name,
                    "tier": r.tier,
                    "tier_name": r.tier_name,
                    "atcoder_target": r.atcoder_target,
                    "difficulty_info": r.difficulty_info,
                    "url": r.url,
                    "status": r.status.value,
                    "details": r.details_string,
                    "conflicts": [
                        {
                            "username": c.username,
                            "original_id": c.original_id,
                            "is_exact": c.is_exact,
                            "similarity": c.similarity,
                            "match_type": c.match_type,
                            "formatted": c.formatted_detail,
                        }
                        for c in r.conflicts
                    ],
                }
                for r in results
            ],
        }

        output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def write_markdown(
        self,
        output_path: Path,
        results: List[ProblemConflictResult],
        participants: List[str],
        total_candidates: int,
        exact_only: bool = False,
    ):
        """Generate high quality, clear report.md."""
        safe_cnt = sum(1 for r in results if r.status == RiskStatus.SAFE)
        suspicious_cnt = sum(1 for r in results if r.status == RiskStatus.SUSPICIOUS)
        collision_cnt = sum(1 for r in results if r.status == RiskStatus.COLLISION)
        has_tiers = any(r.tier is not None for r in results)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        scope_str = "同一ユーザー名のみ（完全一致）" if exact_only else f"類似ID探索（最大 {total_candidates} アカウント）"

        md_lines = [
            "# 企業プログラミングコンテスト 候補問題 既AC・競合調査レポート",
            "",
            f"**調査日時**: {now_str}  ",
            f"**対象参加者数**: {len(participants)} 名（探索スコープ: {scope_str}）  ",
            f"**調査対象候補問題数**: {len(results)} 問  ",
            "",
            "## 1. 総合サマリー",
            "",
            "| 判定ステータス | 問題数 | 説明 |",
            "| :--- | :---: | :--- |",
            f"| 🟢 **SAFE** | {safe_cnt} | 参加者によるAC履歴なし（選定推奨） |",
            f"| 🟡 **SUSPICIOUS** | {suspicious_cnt} | 類似IDまたは関連アカウントによるAC履歴あり（要確認） |",
            f"| 🔴 **COLLISION** | {collision_cnt} | 参加者本人（完全一致ID）によるAC履歴あり（選定非推奨・衝突） |",
            "",
        ]

        if has_tiers:
            md_lines.extend([
                "## 2. 難易度別（茶〜赤）問題選定 & 突合判定マトリクス",
                "",
                "チーム戦において実力差のあるメンバー全員が活躍できるよう、各難易度帯（AtCoder 茶色〜赤色）からバランスよく構成されています。",
                "",
                "| 難易度階層 | 想定レベル | プラットフォーム | 問題コード / 問題名 | 難易度指標 | 判定 | 衝突詳細 / アカウント |",
                "| :--- | :--- | :--- | :--- | :---: | :---: | :--- |",
            ])
            sorted_results = sorted(results, key=lambda r: (r.tier or 99, r.platform, r.problem_id))
            for r in sorted_results:
                if r.status == RiskStatus.SAFE:
                    badge = "🟢 `SAFE`"
                elif r.status == RiskStatus.SUSPICIOUS:
                    badge = "🟡 `SUSPICIOUS`"
                else:
                    badge = "🔴 **`COLLISION`**"

                tier_name = r.tier_name or f"Tier {r.tier}"
                target = r.atcoder_target or "-"
                prob_link = f"[{r.problem_name or r.problem_id}]({r.url})" if r.url else f"`{r.problem_id}`"
                diff_info = r.difficulty_info or "-"

                md_lines.append(
                    f"| {tier_name} | {target} | {r.platform} | {prob_link} (`{r.problem_id}`) | {diff_info} | {badge} | {r.details_string} |"
                )
        else:
            md_lines.extend([
                "## 2. 問題別 突合判定マトリクス",
                "",
                "| Platform | Problem ID | Status | Conflict Users / Details |",
                "| :--- | :--- | :---: | :--- |",
            ])
            for r in results:
                if r.status == RiskStatus.SAFE:
                    badge = "🟢 `SAFE`"
                elif r.status == RiskStatus.SUSPICIOUS:
                    badge = "🟡 `SUSPICIOUS`"
                else:
                    badge = "🔴 **`COLLISION`**"

                md_lines.append(
                    f"| {r.platform} | `{r.problem_id}` | {badge} | {r.details_string} |"
                )

        md_lines.extend([
            "",
            "## 3. 調査対象データ詳細",
            "",
            f"- **対象参加者（AtCoder ID）**: {', '.join(f'`{p}`' for p in participants)}",
            "- **判定基準**:",
            "  - **COLLISION**: 参加者と完全一致（大文字小文字正規化含む）のアカウントが当該問題をすでにACしている状態。",
            "  - **SUSPICIOUS**: 記号付加（例: `user_`, `user-dev`）、数字追加（例: `user1`）、レーベンシュタイン距離1〜2以内の類似IDがACしている状態。",
            "  - **SAFE**: 上記いずれのアカウントからもAC履歴が確認されなかった状態。",
            "",
            "---",
            "*Report generated by `worker-programming-contest-problem-finder`*",
        ])

        output_path.write_text("\n".join(md_lines), encoding="utf-8")
