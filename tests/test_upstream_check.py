"""Contract tests for the upstream review report.

The one property that matters most is negative: the report must never let
"could not check" read as "nothing to review". A commit-only checker made that
mistake structurally -- it could not see pull requests or issues at all, so a
green report meant nothing about those two axes.
"""

import json
import subprocess
import unittest
from unittest import mock

from scripts import check_upstream_updates as checker


BASELINE = {
    "repo": "https://github.com/agentcrew-academy/harness-starter-kit.git",
    "branch": "main",
    "reviewed_through": "0" * 40,
    "reviewed_date": "2026-08-23",
    "decision_log": "FORK.md",
    "reviewed_pr_through": 2,
    "reviewed_issue_through": 1,
}


def gh_result(returncode=0, stdout="[]"):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


class SlugParsing(unittest.TestCase):
    def test_https_and_ssh_forms_resolve_to_the_same_slug(self):
        for url in (
            "https://github.com/agentcrew-academy/harness-starter-kit.git",
            "https://github.com/agentcrew-academy/harness-starter-kit",
            "git@github.com:agentcrew-academy/harness-starter-kit.git",
        ):
            self.assertEqual(
                checker.upstream_slug(url), "agentcrew-academy/harness-starter-kit"
            )

    def test_a_non_github_remote_has_no_slug(self):
        self.assertIsNone(checker.upstream_slug("https://gitlab.com/owner/name.git"))


class TicketCollection(unittest.TestCase):
    def test_only_items_above_the_watermark_are_listed(self):
        payload = json.dumps(
            [{"number": 1, "title": "old"}, {"number": 3, "title": "new"}, {"number": 2, "title": "at"}]
        )
        with mock.patch.object(subprocess, "run", return_value=gh_result(stdout=payload)):
            tickets = checker.collect_new_tickets(BASELINE, "pr")

        self.assertEqual([item["number"] for item in tickets], [3])

    def test_closed_items_are_still_requested(self):
        """An item opened and closed between two runs was never triaged here."""
        with mock.patch.object(subprocess, "run", return_value=gh_result()) as run:
            checker.collect_new_tickets(BASELINE, "issue")

        self.assertIn("--state", run.call_args.args[0])
        self.assertIn("all", run.call_args.args[0])

    def test_a_failed_gh_call_returns_none_not_an_empty_list(self):
        with mock.patch.object(subprocess, "run", return_value=gh_result(returncode=1)):
            self.assertIsNone(checker.collect_new_tickets(BASELINE, "pr"))

    def test_unparsable_output_returns_none(self):
        with mock.patch.object(subprocess, "run", return_value=gh_result(stdout="not json")):
            self.assertIsNone(checker.collect_new_tickets(BASELINE, "pr"))

    def test_output_of_the_wrong_shape_returns_none(self):
        for stdout in ('{"number": 3}', '[{"title": "no number"}]', '[3]', '[{"number": "3", "title": "x"}]'):
            with self.subTest(stdout=stdout), \
                 mock.patch.object(subprocess, "run", return_value=gh_result(stdout=stdout)):
                self.assertIsNone(checker.collect_new_tickets(BASELINE, "pr"))

    def test_a_missing_gh_binary_returns_none_instead_of_raising(self):
        missing = FileNotFoundError(2, "No such file or directory", "gh")
        with mock.patch.object(subprocess, "run", side_effect=missing):
            self.assertIsNone(checker.collect_new_tickets(BASELINE, "pr"))


class RewrittenHistory(unittest.TestCase):
    """A reviewed commit that upstream no longer contains must stop the check."""

    def setUp(self):
        import tempfile
        from pathlib import Path

        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "upstream"
        self.repo.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "test")
        self.git("config", "commit.gpgsign", "false")

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.repo, check=True, capture_output=True, text=True
        ).stdout.strip()

    def commit(self, message):
        self.git("commit", "--quiet", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def test_new_commits_on_top_of_the_reviewed_one_are_listed(self):
        reviewed = self.commit("reviewed")
        self.commit("new upstream work")
        baseline = dict(BASELINE, reviewed_through=reviewed)

        commits = checker.collect_new_commits(baseline, self.repo, "HEAD")

        self.assertEqual([c["subject"] for c in commits], ["new upstream work"])

    def test_a_force_pushed_branch_is_an_error_not_a_short_list(self):
        base = self.commit("base")
        reviewed = self.commit("reviewed, later rewritten away")
        self.git("reset", "--quiet", "--hard", base)
        self.commit("rewritten history")
        baseline = dict(BASELINE, reviewed_through=reviewed)

        with self.assertRaisesRegex(checker.UpstreamCheckError, "rewritten"):
            checker.collect_new_commits(baseline, self.repo, "HEAD")

    def test_a_shallow_clone_is_reported_as_shallow_not_rewritten(self):
        reviewed = self.commit("reviewed")
        self.commit("next")
        self.commit("tip")
        shallow = self.repo.parent / "shallow"  # inside the temp dir, removed with it
        subprocess.run(["git", "clone", "--quiet", "--depth", "1",
                        self.repo.as_uri(), str(shallow)],
                       check=True, capture_output=True)
        # The reviewed commit object exists but its link to the tip is cut off.
        subprocess.run(["git", "fetch", "--quiet", "--depth", "1", "origin", reviewed],
                       cwd=shallow, check=True, capture_output=True)
        baseline = dict(BASELINE, reviewed_through=reviewed)

        with self.assertRaisesRegex(checker.UpstreamCheckError, "shallow"):
            checker.collect_new_commits(baseline, shallow, "HEAD")

    def test_an_unknown_reviewed_commit_is_an_error(self):
        self.commit("only commit")
        baseline = dict(BASELINE, reviewed_through="1" * 40)

        with self.assertRaises(checker.UpstreamCheckError):
            checker.collect_new_commits(baseline, self.repo, "HEAD")


class ReportWording(unittest.TestCase):
    def test_an_unavailable_check_is_reported_as_not_checked(self):
        report = checker.render_markdown(BASELINE, [], None, None)

        self.assertIn("Not checked", report)
        self.assertNotIn("No new items above that number.", report)

    def test_an_empty_result_is_reported_as_nothing_new(self):
        report = checker.render_markdown(BASELINE, [], [], [])

        self.assertIn("No new items above that number.", report)
        self.assertNotIn("Not checked", report)

    def test_both_ticket_axes_appear_even_when_there_are_no_commits(self):
        report = checker.render_markdown(BASELINE, [], [], [])

        self.assertIn("## Upstream pull requests", report)
        self.assertIn("## Upstream issues", report)

    def test_pipes_in_a_title_cannot_break_the_table(self):
        report = checker.render_markdown(
            BASELINE, [], [{"number": 9, "title": "fix: a | b"}], []
        )

        self.assertIn("fix: a \\| b", report)


class ExitCodes(unittest.TestCase):
    def run_main(self, tickets, tmp):
        with mock.patch.object(checker, "load_baseline", return_value=dict(BASELINE)), \
             mock.patch.object(checker, "fetch_upstream", return_value="ref"), \
             mock.patch.object(checker, "collect_new_commits", return_value=[]), \
             mock.patch.object(checker, "collect_new_tickets", side_effect=tickets), \
             mock.patch("sys.argv", ["check", "--output", str(tmp)]):
            return checker.main()

    def test_unavailable_tickets_fail_closed(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            code = self.run_main([None, None], f"{directory}/report.md")

        self.assertEqual(code, 2)

    def test_an_unexpected_error_fails_closed_with_a_report(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(checker, "load_baseline", return_value=BASELINE), \
             mock.patch.object(checker, "fetch_upstream", return_value="ref"), \
             mock.patch.object(checker, "collect_new_commits", side_effect=KeyError("x")), \
             mock.patch("sys.argv", ["check", "--strict", "--output", f"{directory}/report.md"]):
            code = checker.main()
            report = Path(directory, "report.md").read_text(encoding="utf-8")

        self.assertEqual(code, 2)
        self.assertIn("Check failed", report)
        self.assertIn("KeyError", report)

    def test_an_unwritable_report_path_still_exits_2(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(checker, "load_baseline", return_value=BASELINE), \
             mock.patch.object(checker, "fetch_upstream", return_value="ref"), \
             mock.patch.object(checker, "collect_new_commits", return_value=[]), \
             mock.patch.object(checker, "collect_new_tickets", side_effect=[[], []]), \
             mock.patch("sys.argv", ["check", "--strict", "--output", f"{directory}/missing/r.md"]):
            self.assertEqual(checker.main(), 2)

    def test_a_non_utf8_console_does_not_crash_the_report(self):
        import io
        import tempfile

        commit = {"sha": "a" * 40, "short": "aaaaaaa", "date": "2026-10-25",
                  "subject": "\u4fee\u6b63 hook", "files": []}
        console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(checker, "load_baseline", return_value=BASELINE), \
             mock.patch.object(checker, "fetch_upstream", return_value="ref"), \
             mock.patch.object(checker, "collect_new_commits", return_value=[commit]), \
             mock.patch.object(checker, "collect_new_tickets", side_effect=[[], []]), \
             mock.patch("sys.stdout", console), \
             mock.patch("sys.argv", ["check", "--strict", "--output", f"{directory}/r.md"]):
            self.assertEqual(checker.main(), 1)  # a new commit under --strict, not a crash

    def test_a_broken_stdout_exits_2_not_1(self):
        import tempfile

        class Broken:
            def write(self, _text):
                raise BrokenPipeError(32, "Broken pipe")

            def flush(self):
                raise BrokenPipeError(32, "Broken pipe")

        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(checker, "load_baseline", return_value=BASELINE), \
             mock.patch.object(checker, "fetch_upstream", return_value="ref"), \
             mock.patch.object(checker, "collect_new_commits", return_value=[]), \
             mock.patch.object(checker, "collect_new_tickets", side_effect=[[], []]), \
             mock.patch("sys.stdout", Broken()), \
             mock.patch("sys.argv", ["check", "--output", f"{directory}/r.md"]):
            self.assertEqual(checker.main(), 2)

    def test_a_clean_check_succeeds(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            code = self.run_main([[], []], f"{directory}/report.md")

        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
