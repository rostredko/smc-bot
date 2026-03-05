#!/usr/bin/env python3
"""Generate detailed English release notes for a git commit range."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ZERO_SHA = "0" * 40
COMMIT_TYPE_PATTERN = re.compile(
    r"^(?P<kind>feat|fix|refactor|perf|docs|test|chore|build|ci|revert)(\(.+\))?!?:",
    re.IGNORECASE,
)

COMMIT_TYPE_LABELS = {
    "feat": "Features",
    "fix": "Fixes",
    "refactor": "Refactors",
    "perf": "Performance",
    "docs": "Documentation",
    "test": "Tests",
    "chore": "Maintenance",
    "build": "Build and Dependencies",
    "ci": "CI/CD",
    "revert": "Reverts",
}


@dataclass
class FileChange:
    path: str
    additions: int
    deletions: int


@dataclass
class CommitInfo:
    sha: str
    author_name: str
    author_email: str
    authored_at: str
    subject: str
    files: list[FileChange]
    additions: int
    deletions: int
    category: str

    @property
    def short_sha(self) -> str:
        return self.sha[:12]


def run_git(repo_root: Path, *args: str) -> str:
    command = ["git", *args]
    completed = subprocess.run(
        command,
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        joined = " ".join(command)
        raise RuntimeError(f"Command failed: {joined}\n{completed.stderr.strip()}")
    return completed.stdout.strip()


def resolve_repo_root() -> Path:
    completed = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError("Not inside a git repository.")
    return Path(completed.stdout.strip())


def classify_commit(subject: str) -> str:
    match = COMMIT_TYPE_PATTERN.match(subject)
    if not match:
        return "Other Changes"
    kind = match.group("kind").lower()
    return COMMIT_TYPE_LABELS.get(kind, "Other Changes")


def classify_area(path: str) -> str:
    if path.startswith("web-dashboard/src/"):
        return "Frontend UI"
    if path.startswith("web-dashboard/"):
        return "Backend API and Dashboard Runtime"
    if path.startswith("engine/"):
        return "Trading Engine"
    if path.startswith("strategies/"):
        return "Strategies and Risk"
    if path.startswith("db/"):
        return "Database Layer"
    if path.startswith("tests/"):
        return "Test Suite"
    if path.startswith(".github/"):
        return "CI/CD"
    if path.startswith("deps/") or path.endswith("requirements.txt"):
        return "Dependencies"
    if path.startswith("docs/") or path in {"README.md", "PROJECT_STRUCTURE.md"}:
        return "Documentation"
    if "/" not in path:
        return "Repository Root"
    return path.split("/", 1)[0]


def parse_numstat(raw_output: str) -> tuple[list[FileChange], int, int]:
    files: list[FileChange] = []
    total_add = 0
    total_del = 0

    for raw_line in raw_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        add_raw, del_raw, file_path = parts[0], parts[1], parts[2]

        add_count = 0 if add_raw == "-" else int(add_raw)
        del_count = 0 if del_raw == "-" else int(del_raw)
        total_add += add_count
        total_del += del_count
        files.append(FileChange(path=file_path, additions=add_count, deletions=del_count))

    return files, total_add, total_del


def collect_commits(repo_root: Path, base: str | None, head: str) -> list[CommitInfo]:
    if base and base != ZERO_SHA:
        range_spec = f"{base}..{head}"
        rev_list = run_git(repo_root, "rev-list", "--reverse", range_spec)
    else:
        rev_list = run_git(repo_root, "rev-list", "--reverse", head)

    commit_shas = [line.strip() for line in rev_list.splitlines() if line.strip()]
    commits: list[CommitInfo] = []

    for sha in commit_shas:
        metadata = run_git(
            repo_root,
            "show",
            "--format=%H%x1f%an%x1f%ae%x1f%aI%x1f%s",
            "--no-patch",
            sha,
        )
        if not metadata:
            continue

        values = metadata.split("\x1f")
        if len(values) < 5:
            raise RuntimeError(f"Unexpected commit metadata format for {sha}")
        _, author_name, author_email, authored_at, subject = values[:5]

        raw_numstat = run_git(repo_root, "show", "--numstat", "--format=", sha)
        files, additions, deletions = parse_numstat(raw_numstat)
        category = classify_commit(subject)

        commits.append(
            CommitInfo(
                sha=sha,
                author_name=author_name,
                author_email=author_email,
                authored_at=authored_at,
                subject=subject,
                files=files,
                additions=additions,
                deletions=deletions,
                category=category,
            )
        )

    return commits


def build_markdown(
    *,
    commits: list[CommitInfo],
    base: str | None,
    head: str,
    target_branch: str,
    title: str | None,
    max_files_per_commit: int,
) -> str:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    target_title = title or f"Release Notes for {target_branch} update ({head[:12]})"

    unique_files = {file_change.path for commit in commits for file_change in commit.files}
    area_counter: Counter[str] = Counter()
    for path in unique_files:
        area_counter[classify_area(path)] += 1

    category_counter: Counter[str] = Counter(commit.category for commit in commits)
    contributors = {(commit.author_name, commit.author_email) for commit in commits}
    total_additions = sum(commit.additions for commit in commits)
    total_deletions = sum(commit.deletions for commit in commits)

    lines: list[str] = []
    lines.append(f"# {target_title}")
    lines.append("")
    lines.append(f"- Generated at (UTC): {generated_at}")
    lines.append(f"- Target branch: `{target_branch}`")
    if base and base != ZERO_SHA:
        lines.append(f"- Commit range: `{base[:12]}..{head[:12]}`")
    else:
        lines.append(f"- Commit range: `initial..{head[:12]}`")
    lines.append("")

    lines.append("## Summary")
    lines.append(f"- Commits included: {len(commits)}")
    lines.append(f"- Contributors: {len(contributors)}")
    lines.append(f"- Files touched (unique): {len(unique_files)}")
    lines.append(f"- Cumulative line changes: `+{total_additions} / -{total_deletions}`")
    lines.append("")

    if area_counter:
        lines.append("## Change Areas")
        for area, count in sorted(area_counter.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- **{area}**: {count} file(s)")
        lines.append("")

    if category_counter:
        lines.append("## Change Types")
        for category, count in sorted(category_counter.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- **{category}**: {count} commit(s)")
        lines.append("")

    lines.append("## Commit-by-Commit Details")
    for commit in commits:
        commit_areas = sorted({classify_area(file_change.path) for file_change in commit.files})
        area_scope = ", ".join(commit_areas) if commit_areas else "No file changes detected"

        lines.append(f"### {commit.short_sha} - {commit.subject}")
        lines.append(f"- Author: {commit.author_name} <{commit.author_email}>")
        lines.append(f"- Date: {commit.authored_at}")
        lines.append(f"- Type: {commit.category}")
        lines.append(f"- Scope: {area_scope}")
        lines.append(
            f"- Diff footprint: {len(commit.files)} file(s), `+{commit.additions} / -{commit.deletions}`"
        )

        if commit.files:
            lines.append("- Files:")
            for file_change in commit.files[:max_files_per_commit]:
                lines.append(
                    f"  - `{file_change.path}` (`+{file_change.additions} / -{file_change.deletions}`)"
                )
            if len(commit.files) > max_files_per_commit:
                omitted = len(commit.files) - max_files_per_commit
                lines.append(f"  - ... {omitted} more file(s) omitted")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate detailed release notes for a git range."
    )
    parser.add_argument(
        "--base",
        help=(
            "Base commit for the range. If omitted, the script uses full history "
            "reachable from --head."
        ),
    )
    parser.add_argument(
        "--head",
        default="HEAD",
        help="Head commit for the range (default: HEAD).",
    )
    parser.add_argument(
        "--target-branch",
        default="master",
        help="Target branch name for metadata (default: master).",
    )
    parser.add_argument(
        "--title",
        help="Optional title for the generated markdown.",
    )
    parser.add_argument(
        "--max-files-per-commit",
        type=int,
        default=30,
        help="Maximum files listed per commit in details (default: 30).",
    )
    parser.add_argument(
        "--output",
        help="Output markdown file path. If omitted, markdown is printed to stdout.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = resolve_repo_root()

    base = args.base.strip() if args.base else None
    head = run_git(repo_root, "rev-parse", args.head).strip()
    if base:
        base = run_git(repo_root, "rev-parse", base).strip()

    commits = collect_commits(repo_root, base, head)
    if not commits:
        raise RuntimeError("No commits found for the requested range.")

    markdown = build_markdown(
        commits=commits,
        base=base,
        head=head,
        target_branch=args.target_branch,
        title=args.title,
        max_files_per_commit=max(1, args.max_files_per_commit),
    )

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = repo_root / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        print(f"Release notes written to {output_path}")
    else:
        sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
