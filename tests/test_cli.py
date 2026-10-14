import sys
from pathlib import Path
from unittest.mock import patch

from check_conflicts import parse_arguments
from src.matcher import ProblemConflictResult, RiskStatus
from src.reporter import Reporter


def test_cli_exact_only_flag():
    with patch.object(sys, "argv", ["check_conflicts.py", "--exact-only"]):
        args = parse_arguments()
        assert args.exact_only is True

    with patch.object(sys, "argv", ["check_conflicts.py", "--exact"]):
        args = parse_arguments()
        assert args.exact_only is True

    with patch.object(sys, "argv", ["check_conflicts.py", "-e"]):
        args = parse_arguments()
        assert args.exact_only is True

    with patch.object(sys, "argv", ["check_conflicts.py"]):
        args = parse_arguments()
        assert args.exact_only is False


def test_reporter_exact_only(tmp_path: Path):
    reporter = Reporter()
    result = ProblemConflictResult(
        platform="CodeChef",
        problem_id="FLOW001",
        status=RiskStatus.SAFE,
        problem_name="Add Two Numbers",
    )
    json_path = tmp_path / "result.json"
    md_path = tmp_path / "report.md"

    reporter.write_json(
        output_path=json_path,
        results=[result],
        metadata={"exact_only": True},
    )
    assert json_path.exists()
    content = json_path.read_text(encoding="utf-8")
    assert '"exact_only": true' in content

    reporter.write_markdown(
        output_path=md_path,
        results=[result],
        participants=["chokudai"],
        total_candidates=1,
        exact_only=True,
    )
    assert md_path.exists()
    md_content = md_path.read_text(encoding="utf-8")
    assert "同一ユーザー名のみ（完全一致）" in md_content
