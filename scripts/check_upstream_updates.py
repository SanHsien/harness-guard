"""Report upstream commits, pull requests, and issues this fork has not reviewed.

Commits are only one of the places upstream work shows up. A pull request can sit
open for months with a fix in it, and an issue can describe a defect this fork also
has -- neither reaches the commit log until somebody merges it. Each axis therefore
carries its own watermark, and the report only lists what is above them.

Tickets are queried with ``--state all`` on purpose: an item opened and closed
between two scheduled runs is still an item this fork never triaged.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
BASELINE_PATH = SCRIPT_DIR / "upstream_baseline.json"
UPSTREAM_REF_PREFIX = "refs/upstream-check"
DEFAULT_DECISION_LOG = "docs/DECISIONS.md"


class UpstreamCheckError(RuntimeError):
    """Raised when the baseline or upstream Git history cannot be inspected."""


def load_baseline(path: Path = BASELINE_PATH) -> dict:
    if not path.is_file():
        raise UpstreamCheckError(f"missing baseline file: {path}")
    try:
        baseline = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UpstreamCheckError(f"invalid baseline file: {path}: {exc}") from exc
    if not isinstance(baseline, dict):
        raise UpstreamCheckError(f"invalid baseline file: {path}: not a JSON object")
    required = {"repo", "branch", "reviewed_through", "reviewed_date"}
    missing = sorted(required - baseline.keys())
    if missing:
        raise UpstreamCheckError(f"baseline missing fields: {', '.join(missing)}")
    reviewed = baseline["reviewed_through"]
    if not isinstance(reviewed, str) or re.fullmatch(r"[0-9a-fA-F]{40}", reviewed) is None:
        raise UpstreamCheckError("reviewed_through must be a full 40-character SHA")
    for key in ("repo", "branch"):
        value = baseline[key]
        # Both reach git as arguments; a value starting with "-" would be read
        # as an option (e.g. --upload-pack=...). Spaces are fine in a local repo
        # path (arguments go as a list), but never valid in a branch name.
        if not isinstance(value, str) or not value or value.startswith("-") or (
            key == "branch" and any(ch.isspace() for ch in value)
        ):
            raise UpstreamCheckError(f"{key} must be a plain, non-empty string, got {value!r}")
    for key in ("reviewed_pr_through", "reviewed_issue_through"):
        value = baseline.get(key, 0)
        # bool is an int subclass; a watermark of `true` is a typo, not #1.
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise UpstreamCheckError(f"{key} must be a non-negative integer, got {value!r}")
    return baseline


def run_git(args: list[str], repo_dir: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise UpstreamCheckError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def fetch_upstream(baseline: dict, repo_dir: Path) -> str:
    branch = baseline["branch"]
    ref = f"{UPSTREAM_REF_PREFIX}/{branch}"
    run_git(
        ["fetch", "--quiet", "--", baseline["repo"], f"+refs/heads/{branch}:{ref}"],
        repo_dir,
    )
    return ref


def require_reviewed_ancestor(reviewed: str, ref: str, repo_dir: Path) -> None:
    """Fail unless the reviewed commit is still in upstream's history.

    `git log reviewed..upstream` does not complain when upstream rewrote its
    history: it quietly lists whatever is not reachable from the old commit, so
    a force-pushed branch would read as a short, ordinary list of new commits
    while the commits this fork reviewed were no longer upstream at all.
    """
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", reviewed, ref],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode == 0:
        return
    shallow = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if shallow.stdout.strip() == "true":
        # A shallow clone cuts history off (or leaves the reviewed commit out
        # entirely), so ancestry cannot be proven either way. Saying "rewritten"
        # would send someone hunting for a force push that never happened.
        raise UpstreamCheckError(
            "this clone is shallow, so the ancestry of reviewed_through "
            f"{reviewed[:7]} cannot be checked; check out with full history "
            "(actions/checkout fetch-depth: 0)."
        )
    if result.returncode == 1:
        raise UpstreamCheckError(
            f"reviewed_through {reviewed[:7]} is not an ancestor of upstream {ref}: "
            "upstream history was rewritten. Re-review against the new history "
            "before moving the baseline."
        )
    raise UpstreamCheckError(
        f"git merge-base --is-ancestor {reviewed[:7]} {ref} failed: {result.stderr.strip()}"
    )


def collect_new_commits(baseline: dict, repo_dir: Path, ref: str) -> list[dict]:
    reviewed = baseline["reviewed_through"]
    require_reviewed_ancestor(reviewed, ref, repo_dir)
    raw = run_git(
        [
            "log",
            "--reverse",
            "--date=short",
            "--format=%H%x1f%ad%x1f%s",
            f"{reviewed}..{ref}",
        ],
        repo_dir,
    )
    commits = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        sha, date, subject = line.split("\x1f", 2)
        files = [
            item
            for item in run_git(
                ["show", "--name-only", "--format=", sha], repo_dir
            ).splitlines()
            if item.strip()
        ]
        commits.append(
            {
                "sha": sha,
                "short": sha[:7],
                "date": date,
                "subject": subject,
                "files": files,
            }
        )
    return commits


def upstream_slug(repo_url: str) -> str | None:
    """`https://github.com/owner/name.git` -> `owner/name`, or None if not GitHub."""
    match = re.search(
        r"github\.com[:/](?P<owner>[^/]+)/(?P<name>[^/]+?)(?:\.git)?$", repo_url
    )
    return f"{match['owner']}/{match['name']}" if match else None


def collect_new_tickets(baseline: dict, kind: str) -> list[dict] | None:
    """All PRs or issues numbered above the watermark, closed ones included.

    Returns ``None`` -- not an empty list -- when ``gh`` cannot answer, and the
    report says so. "Not checked" and "nothing to review" look identical in a
    green report, and only one of them is true; conflating them is how a fork
    stops noticing upstream without anybody deciding to.
    """
    slug = upstream_slug(str(baseline["repo"]))
    if not slug:
        return None
    watermark = int(baseline.get(f"reviewed_{kind}_through", 0) or 0)
    try:
        result = subprocess.run(
            [
                "gh", kind, "list", "--repo", slug, "--state", "all",
                "--limit", "1000", "--json", "number,title",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        # `gh` not installed at all. Uncaught, this was a traceback before the
        # report was written, which a --strict caller reads as exit 1, "upstream
        # has unreviewed commits" -- the wrong failure, with no report to show.
        return None
    if result.returncode != 0:
        return None
    try:
        items = json.loads(result.stdout)
    except ValueError:
        return None
    if not isinstance(items, list) or not all(
        isinstance(item, dict)
        and isinstance(item.get("number"), int)
        and isinstance(item.get("title"), str)
        for item in items
    ):
        return None  # not the shape asked for: unchecked, not "nothing new"
    return sorted(
        (item for item in items if item["number"] > watermark),
        key=lambda item: item["number"],
    )


def render_ticket_section(
    title: str, watermark: int, tickets: list[dict] | None, kind: str, decision_log: str
) -> list[str]:
    lines = [f"## {title}", "", f"Triaged through `#{watermark}`.", ""]
    if tickets is None:
        lines.extend(
            [
                "Not checked: `gh` was unavailable, unauthenticated, or the baseline does",
                "not name a GitHub repository. Reported as such rather than as \"nothing to",
                "review\" -- the difference matters.",
                "",
            ]
        )
        return lines
    if not tickets:
        lines.extend(["No new items above that number.", ""])
        return lines
    lines.extend(
        [f"{len(tickets)} new item(s) to triage.", "", "| Item | Title |", "| --- | --- |"]
    )
    for ticket in tickets:
        # The escape is computed outside the f-string: a backslash inside an
        # f-string expression is a SyntaxError before Python 3.12, and CI
        # compiles this file on 3.11.
        title = ticket["title"].replace("|", "\\|")
        lines.append(f"| #{ticket['number']} | {title} |")
    lines.extend(
        [
            "",
            f"Record the verdict in `{decision_log}`, then raise",
            f"`reviewed_{kind}_through` so the same item is never re-triaged.",
            "",
        ]
    )
    return lines


def render_markdown(
    baseline: dict,
    commits: list[dict],
    prs: list[dict] | None = None,
    issues: list[dict] | None = None,
    error: str | None = None,
) -> str:
    decision_log = baseline.get("decision_log", DEFAULT_DECISION_LOG)
    lines = [
        "# Upstream review report",
        "",
        f"- Upstream: `{baseline['repo']}` (`{baseline['branch']}`)",
        f"- Reviewed through: `{baseline['reviewed_through'][:7]}`",
        f"- Last review date: {baseline['reviewed_date']}",
        "",
    ]
    if error:
        lines.extend(["## Check failed", "", f"```text\n{error}\n```", ""])
        return "\n".join(lines)
    def with_tickets(body: list[str]) -> str:
        body = body + render_ticket_section(
            "Upstream pull requests",
            int(baseline.get("reviewed_pr_through", 0) or 0),
            prs,
            "pr",
            decision_log,
        )
        body += render_ticket_section(
            "Upstream issues",
            int(baseline.get("reviewed_issue_through", 0) or 0),
            issues,
            "issue",
            decision_log,
        )
        return "\n".join(body)

    if not commits:
        lines.extend(
            ["## Commits", "", "No new upstream commits. Nothing to review.", ""]
        )
        return with_tickets(lines)

    lines.extend(
        [
            "## Commits",
            "",
            f"{len(commits)} upstream commit(s) require review.",
            "",
            "| Commit | Date | Subject | Files |",
            "| --- | --- | --- | --- |",
        ]
    )
    for commit in commits:
        subject = commit["subject"].replace("|", "\\|")
        files = "<br>".join(item.replace("|", "\\|") for item in commit["files"][:8])
        if len(commit["files"]) > 8:
            files += f"<br>… +{len(commit['files']) - 8} more"
        lines.append(
            f"| `{commit['short']}` | {commit['date']} | {subject} | {files or '(none)'} |"
        )
    lines.extend(
        [
            "",
            f"Review each commit, record adopt/skip decisions in `{decision_log}`,",
            f"then advance `{BASELINE_PATH.parent.name}/upstream_baseline.json` only "
            "after verification.",
            "",
        ]
    )
    return with_tickets(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="upstream-review-report.md")
    parser.add_argument("--repo-dir", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero when new commits require review.",
    )
    args = parser.parse_args()

    baseline: dict
    commits: list[dict] = []
    prs: list[dict] | None = None
    issues: list[dict] | None = None
    error: str | None = None
    try:
        baseline = load_baseline()
        ref = fetch_upstream(baseline, args.repo_dir)
        commits = collect_new_commits(baseline, args.repo_dir, ref)
        prs = collect_new_tickets(baseline, "pr")
        issues = collect_new_tickets(baseline, "issue")
    except Exception as exc:  # noqa: BLE001 -- any failure is "not checked", exit 2
        # UpstreamCheckError carries its own message; anything else would
        # otherwise escape as a traceback with exit 1, which --strict callers
        # read as "unreviewed commits", and no report would be written.
        error = str(exc) if isinstance(exc, UpstreamCheckError) else (
            f"unexpected {type(exc).__name__}: {exc}"
        )
        baseline = {
            "repo": "unknown",
            "branch": "unknown",
            "reviewed_through": "0" * 40,
            "reviewed_date": "unknown",
        }

    report = render_markdown(baseline, commits, prs, issues, error)
    try:
        # errors="replace": a lone surrogate in a title still leaves a report file.
        Path(args.output).write_text(report, encoding="utf-8", errors="replace")
    except (OSError, ValueError) as exc:  # ValueError: e.g. a NUL in the output path
        # Still exit 2, not a traceback's 1: --strict reads 1 as "unreviewed".
        error = error or f"could not write the report to {args.output}: {exc}"
        report = render_markdown(baseline, commits, prs, issues, error)
    unavailable = [
        name for name, value in (("pull requests", prs), ("issues", issues)) if value is None
    ]
    if not error and unavailable:
        # Fail closed. A report that could not enumerate tickets must not be
        # allowed to read as a clean bill of health.
        report += f"\nERROR: gh could not enumerate upstream {' and '.join(unavailable)}.\n"
    # Upstream subjects are often not ASCII; a console in a legacy code page
    # must not turn printing the report into a crash with exit 1. Neither may a
    # closed or broken stdout: the exit code is the result, the print is a copy.
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    try:
        print(report)
        sys.stdout.flush()
    except (OSError, ValueError, AttributeError):
        return 2

    if error or unavailable:
        return 2
    if args.strict and (commits or prs or issues):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
