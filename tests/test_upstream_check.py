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

    def test_a_clean_check_succeeds(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            code = self.run_main([[], []], f"{directory}/report.md")

        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
