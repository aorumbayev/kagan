"""Unit tests for WorktreeManager.merge_to_main()."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from kagan.agents.worktree import WorktreeError, slugify
from tests.helpers.mocks import MergeScenarioBuilder

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.unit


class TestMergeToMain:
    """Tests for WorktreeManager.merge_to_main() method."""

    @pytest.fixture
    def scenario(self, tmp_path: Path) -> MergeScenarioBuilder:
        return MergeScenarioBuilder(tmp_path)

    async def test_successful_squash_merge(self, scenario: MergeScenarioBuilder):
        s = (
            scenario.with_worktree("ticket-123")
            .with_branch("kagan/ticket-123-fix-bug")
            .with_commits(["abc123 Fix the bug", "def456 Add tests"])
        )
        s.mock_run_git.side_effect = s.build_success_responses()
        success, message = await s.manager.merge_to_main(s.ticket_id)
        assert success is True
        assert "Successfully merged" in message and s.branch_name in message

    async def test_successful_regular_merge(self, scenario: MergeScenarioBuilder):
        s = (
            scenario.with_worktree("ticket-456")
            .with_branch("kagan/ticket-456-feature")
            .with_commits(["abc123 Add feature"])
        )
        s.mock_run_git.side_effect = s.build_regular_merge_responses()
        success, message = await s.manager.merge_to_main(s.ticket_id, squash=False)
        assert success is True and "Successfully merged" in message

    async def test_worktree_not_found(self, scenario: MergeScenarioBuilder):
        success, message = await scenario.manager.merge_to_main("nonexistent-ticket")
        assert success is False and "Worktree not found" in message
        scenario.mock_run_git.assert_not_called()

    async def test_branch_not_found(self, scenario: MergeScenarioBuilder):
        scenario.with_worktree("ticket-789")
        scenario.mock_run_git.return_value = ("", "")
        success, message = await scenario.manager.merge_to_main(scenario.ticket_id)
        assert success is False and "Could not determine branch" in message

    async def test_no_commits_to_merge(self, scenario: MergeScenarioBuilder):
        s = scenario.with_worktree("ticket-empty").with_branch("kagan/ticket-empty-branch")
        s.mock_run_git.side_effect = [
            (s.branch_name, ""),  # rev-parse (get branch)
            ("", ""),  # status --porcelain (clean)
            ("", ""),  # log (no commits)
        ]
        success, message = await s.manager.merge_to_main(s.ticket_id)
        assert success is False and "No commits to merge" in message

    @pytest.mark.parametrize("marker", ["UU", "AA", "DD"])
    async def test_squash_merge_conflict_markers(self, scenario: MergeScenarioBuilder, marker: str):
        s = (
            scenario.with_worktree(f"ticket-{marker.lower()}")
            .with_branch(f"kagan/ticket-{marker.lower()}-branch")
            .with_commits(["abc123 Changes"])
            .with_conflict(marker)
        )
        s.mock_run_git.side_effect = s.build_conflict_responses()
        success, message = await s.manager.merge_to_main(s.ticket_id)
        assert success is False and "Merge conflict" in message
        assert len([c for c in s.mock_run_git.call_args_list if "--abort" in c[0]]) == 1

    @pytest.mark.parametrize("in_stderr", [False, True])
    async def test_regular_merge_conflict_detection(
        self, scenario: MergeScenarioBuilder, in_stderr: bool
    ):
        s = (
            scenario.with_worktree(f"ticket-{'stderr' if in_stderr else 'stdout'}")
            .with_branch("kagan/ticket-conflict-branch")
            .with_commits(["abc123 Changes"])
        )
        s.mock_run_git.side_effect = s.build_regular_conflict_responses(in_stderr=in_stderr)
        success, message = await s.manager.merge_to_main(s.ticket_id, squash=False)
        assert success is False and "Merge conflict" in message

    async def test_checkout_error_no_abort(self, scenario: MergeScenarioBuilder):
        s = scenario.with_worktree("ticket-checkout-error").with_branch("kagan/branch")
        s.mock_run_git.side_effect = [
            (s.branch_name, ""),  # rev-parse (get branch)
            ("", ""),  # status --porcelain (uncommitted check - clean)
            ("abc123 Commit", ""),  # log (get commits)
            WorktreeError("Failed to checkout main"),  # checkout fails
        ]
        success, message = await s.manager.merge_to_main(s.ticket_id)
        assert success is False and "Merge failed" in message
        assert len([c for c in s.mock_run_git.call_args_list if "--abort" in c[0]]) == 0

    async def test_error_after_merge_calls_abort(self, scenario: MergeScenarioBuilder):
        s = scenario.with_worktree("ticket-post-merge-error").with_branch("kagan/branch")
        call_count = 0

        async def mock_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Order: rev-parse, status (clean), log, checkout, merge, status (conflict), commit
            if call_count <= 6:
                return [
                    (s.branch_name, ""),  # 1. rev-parse
                    ("", ""),  # 2. status --porcelain (clean)
                    ("abc123 Commit", ""),  # 3. log
                    ("", ""),  # 4. checkout
                    ("", ""),  # 5. merge --squash
                    ("M file.py", ""),  # 6. status (no conflict)
                ][call_count - 1]
            if call_count == 7:
                raise WorktreeError("Commit hook failed")
            return ("", "")

        s.mock_run_git.side_effect = mock_side_effect
        success, message = await s.manager.merge_to_main(s.ticket_id)
        assert success is False and "Merge failed" in message and call_count >= 8

    async def test_unexpected_exception_aborts(self, scenario: MergeScenarioBuilder):
        s = scenario.with_worktree("ticket-unexpected").with_branch("kagan/branch")
        call_count = 0

        async def mock_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Order: rev-parse, status (clean), log, checkout, merge --squash
            if call_count <= 5:
                return [
                    (s.branch_name, ""),  # 1. rev-parse
                    ("", ""),  # 2. status --porcelain (clean)
                    ("abc123 Commit", ""),  # 3. log
                    ("", ""),  # 4. checkout
                    ("", ""),  # 5. merge --squash
                ][call_count - 1]
            if call_count == 6:
                raise RuntimeError("Unexpected I/O error")
            return ("", "")

        s.mock_run_git.side_effect = mock_side_effect
        success, message = await s.manager.merge_to_main(s.ticket_id)
        assert success is False and "Unexpected error during merge" in message and call_count >= 7

    async def test_abort_failure_silently_ignored(self, scenario: MergeScenarioBuilder):
        s = scenario.with_worktree("ticket-abort-fail").with_branch("kagan/branch")
        call_count = 0

        async def mock_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Order: rev-parse, status (clean), log, checkout, merge --squash
            if call_count <= 5:
                return [
                    (s.branch_name, ""),  # 1. rev-parse
                    ("", ""),  # 2. status --porcelain (clean)
                    ("abc123 Commit", ""),  # 3. log
                    ("", ""),  # 4. checkout
                    ("", ""),  # 5. merge --squash
                ][call_count - 1]
            if call_count == 6:
                raise RuntimeError("Status check failed")
            raise Exception("Abort also failed")

        s.mock_run_git.side_effect = mock_side_effect
        success, message = await s.manager.merge_to_main(s.ticket_id)
        assert success is False and "Unexpected error during merge" in message

    async def test_merge_started_flag_tracks_state(self, scenario: MergeScenarioBuilder):
        s = scenario.with_worktree("ticket-flag").with_branch("kagan/branch")
        s.mock_run_git.side_effect = [
            (s.branch_name, ""),  # rev-parse (get branch)
            ("", ""),  # status --porcelain (clean)
            ("abc123 Commit", ""),  # log (get commits)
            WorktreeError("Checkout failed"),  # checkout fails
        ]
        success, _ = await s.manager.merge_to_main(s.ticket_id)
        assert success is False and s.mock_run_git.call_count == 4

    async def test_semantic_commit_message_generated(self, scenario: MergeScenarioBuilder):
        s = scenario.with_worktree("ticket-semantic").with_branch("kagan/ticket-semantic-fix")
        captured_commit_msg = None
        status_call_count = 0

        async def capture_commit(*args, **kwargs):
            nonlocal captured_commit_msg, status_call_count
            if args[0] == "rev-parse":
                return (s.branch_name, "")
            elif args[0] == "status":
                status_call_count += 1
                # First status call: uncommitted check (return clean)
                # Second status call: conflict check after merge (return modified)
                return ("", "") if status_call_count == 1 else ("M file.py", "")
            elif args[0] == "log":
                return ("abc123 Fix null pointer", "")
            elif args[0] == "commit":
                captured_commit_msg = args[2]
                return ("", "")
            return ("", "")

        s.mock_run_git.side_effect = capture_commit
        success, _ = await s.manager.merge_to_main(s.ticket_id)
        assert success is True and captured_commit_msg is not None
        assert any(t in captured_commit_msg.lower() for t in ["fix", "feat", "chore"])

    async def test_merge_with_custom_base_branch(self, scenario: MergeScenarioBuilder):
        s = scenario.with_worktree("ticket-develop").with_branch("kagan/ticket-develop-feature")
        checkout_branch = None
        status_call_count = 0

        async def track_checkout(*args, **kwargs):
            nonlocal checkout_branch, status_call_count
            if args[0] == "rev-parse":
                return (s.branch_name, "")
            elif args[0] == "log":
                return ("abc123 Feature", "")
            elif args[0] == "checkout":
                checkout_branch = args[1]
                return ("", "")
            elif args[0] == "status":
                status_call_count += 1
                # First status call: uncommitted check (return clean)
                # Second status call: conflict check after merge (return modified)
                return ("", "") if status_call_count == 1 else ("M file.py", "")
            elif args[0] in ("merge", "commit"):
                return ("", "")
            return ("", "")

        s.mock_run_git.side_effect = track_checkout
        success, message = await s.manager.merge_to_main(s.ticket_id, base_branch="develop")
        assert success is True and checkout_branch == "develop" and "develop" in message

    async def test_branch_name_without_title_slug(self, scenario: MergeScenarioBuilder):
        s = (
            scenario.with_worktree("ticket-no-slug")
            .with_branch("kagan/ticket-no-slug")
            .with_commits(["abc123 Some work"])
        )
        s.mock_run_git.side_effect = s.build_success_responses()
        success, _ = await s.manager.merge_to_main(s.ticket_id)
        assert success is True

    async def test_uncommitted_changes_blocks_merge(self, scenario: MergeScenarioBuilder):
        """Merge fails when main repo has uncommitted changes."""
        s = scenario.with_worktree("ticket-dirty").with_branch("kagan/ticket-dirty-branch")
        s.mock_run_git.side_effect = s.build_uncommitted_changes_response()
        success, message = await s.manager.merge_to_main(s.ticket_id)
        assert success is False
        assert "uncommitted changes" in message
        # Should have stopped after status check (2 calls: rev-parse, status)
        assert s.mock_run_git.call_count == 2


class TestRebaseOntoBase:
    """Tests for WorktreeManager.rebase_onto_base() method."""

    @pytest.fixture
    def scenario(self, tmp_path: Path) -> MergeScenarioBuilder:
        return MergeScenarioBuilder(tmp_path)

    async def test_successful_rebase(self, scenario: MergeScenarioBuilder):
        """Rebase succeeds when no conflicts."""
        s = scenario.with_worktree("ticket-rebase").with_branch("kagan/ticket-rebase-feature")

        s.mock_run_git.side_effect = [
            ("", ""),  # fetch origin main
            (s.branch_name, ""),  # rev-parse (get branch)
            ("", ""),  # status --porcelain (clean)
            ("Rebasing...", ""),  # rebase origin/main (success)
        ]

        success, message, conflicts = await s.manager.rebase_onto_base(s.ticket_id, "main")
        assert success is True
        assert "Successfully rebased" in message
        assert conflicts == []

    async def test_rebase_with_conflicts(self, scenario: MergeScenarioBuilder):
        """Rebase fails and returns conflict files when conflicts occur."""
        s = scenario.with_worktree("ticket-conflict").with_branch("kagan/ticket-conflict-feature")

        s.mock_run_git.side_effect = [
            ("", ""),  # fetch origin main
            (s.branch_name, ""),  # rev-parse (get branch)
            ("", ""),  # status --porcelain (clean before rebase)
            ("", "CONFLICT in file.py"),  # rebase origin/main (conflict)
            ("UU src/file.py\nUU tests/test.py", ""),  # status --porcelain (show conflicts)
            ("", ""),  # rebase --abort
        ]

        success, message, conflicts = await s.manager.rebase_onto_base(s.ticket_id, "main")
        assert success is False
        assert "conflict" in message.lower()
        assert "src/file.py" in conflicts
        assert "tests/test.py" in conflicts

    async def test_rebase_worktree_not_found(self, scenario: MergeScenarioBuilder):
        """Rebase fails gracefully when worktree doesn't exist."""
        success, message, conflicts = await scenario.manager.rebase_onto_base(
            "nonexistent-ticket", "main"
        )
        assert success is False
        assert "Worktree not found" in message
        assert conflicts == []

    async def test_rebase_with_uncommitted_changes(self, scenario: MergeScenarioBuilder):
        """Rebase fails when worktree has uncommitted changes."""
        s = scenario.with_worktree("ticket-dirty").with_branch("kagan/ticket-dirty-feature")

        s.mock_run_git.side_effect = [
            ("", ""),  # fetch origin main
            (s.branch_name, ""),  # rev-parse (get branch)
            ("M dirty_file.py", ""),  # status --porcelain (uncommitted changes)
        ]

        success, message, conflicts = await s.manager.rebase_onto_base(s.ticket_id, "main")
        assert success is False
        assert "uncommitted changes" in message
        assert conflicts == []


class TestGetFilesChangedOnBase:
    """Tests for WorktreeManager.get_files_changed_on_base() method."""

    @pytest.fixture
    def scenario(self, tmp_path: Path) -> MergeScenarioBuilder:
        return MergeScenarioBuilder(tmp_path)

    async def test_returns_changed_files(self, scenario: MergeScenarioBuilder):
        """Returns list of files changed on base branch."""
        s = scenario.with_worktree("ticket-changes").with_branch("kagan/ticket-changes-feature")

        s.mock_run_git.side_effect = [
            ("abc123def456", ""),  # merge-base HEAD origin/main
            ("src/app.py\nsrc/utils.py\nREADME.md", ""),  # diff --name-only
        ]

        files = await s.manager.get_files_changed_on_base(s.ticket_id, "main")
        assert "src/app.py" in files
        assert "src/utils.py" in files
        assert "README.md" in files

    async def test_returns_empty_for_no_changes(self, scenario: MergeScenarioBuilder):
        """Returns empty list when no files changed on base."""
        s = scenario.with_worktree("ticket-no-changes").with_branch("kagan/ticket-no-changes")

        s.mock_run_git.side_effect = [
            ("abc123def456", ""),  # merge-base
            ("", ""),  # diff --name-only (empty)
        ]

        files = await s.manager.get_files_changed_on_base(s.ticket_id, "main")
        assert files == []

    async def test_returns_empty_for_nonexistent_worktree(self, scenario: MergeScenarioBuilder):
        """Returns empty list when worktree doesn't exist."""
        files = await scenario.manager.get_files_changed_on_base("nonexistent", "main")
        assert files == []


class TestSlugify:
    """Tests for slugify helper function."""

    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            ("Hello World", "hello-world"),
            ("Fix bug #123!", "fix-bug-123"),
            ("", ""),
            ("!@#$%^", ""),
        ],
    )
    def test_slugify(self, input_text: str, expected: str):
        assert slugify(input_text) == expected


class TestCleanupOrphans:
    """Tests for WorktreeManager.cleanup_orphans() method."""

    @pytest.fixture
    def scenario(self, tmp_path: Path) -> MergeScenarioBuilder:
        return MergeScenarioBuilder(tmp_path)

    async def test_removes_orphan_worktrees(self, scenario: MergeScenarioBuilder):
        """Orphan worktrees are deleted."""
        from unittest.mock import AsyncMock

        s = scenario.with_worktree("ticket-1")

        # Mock list_all to return worktrees including an orphan
        s.manager.list_all = AsyncMock(return_value=["ticket-1", "ticket-2", "orphan-1"])  # type: ignore[method-assign]

        # Track delete calls
        deleted = []

        async def track_delete(ticket_id: str, delete_branch: bool = False) -> None:
            deleted.append((ticket_id, delete_branch))

        s.manager.delete = track_delete  # type: ignore[method-assign]

        # Only ticket-1 and ticket-2 are valid
        cleaned = await s.manager.cleanup_orphans({"ticket-1", "ticket-2"})

        assert cleaned == ["orphan-1"]
        assert deleted == [("orphan-1", True)]

    async def test_keeps_valid_worktrees(self, scenario: MergeScenarioBuilder):
        """Valid worktrees are not touched."""
        from unittest.mock import AsyncMock

        s = scenario.with_worktree("ticket-1")

        s.manager.list_all = AsyncMock(return_value=["ticket-1", "ticket-2"])  # type: ignore[method-assign]

        deleted = []

        async def track_delete(ticket_id: str, delete_branch: bool = False) -> None:
            deleted.append(ticket_id)

        s.manager.delete = track_delete  # type: ignore[method-assign]

        cleaned = await s.manager.cleanup_orphans({"ticket-1", "ticket-2"})

        assert cleaned == []
        assert deleted == []

    async def test_returns_all_cleaned_ids(self, scenario: MergeScenarioBuilder):
        """Returns list of all cleaned up ticket IDs."""
        from unittest.mock import AsyncMock

        s = scenario.with_worktree("valid")

        s.manager.list_all = AsyncMock(return_value=["valid", "orphan-1", "orphan-2", "orphan-3"])  # type: ignore[method-assign]

        async def noop_delete(ticket_id: str, delete_branch: bool = False) -> None:
            pass

        s.manager.delete = noop_delete  # type: ignore[method-assign]

        cleaned = await s.manager.cleanup_orphans({"valid"})

        assert set(cleaned) == {"orphan-1", "orphan-2", "orphan-3"}

    async def test_empty_worktrees_returns_empty(self, scenario: MergeScenarioBuilder):
        """Returns empty list when no worktrees exist."""
        from unittest.mock import AsyncMock

        s = scenario.with_worktree("ticket-1")

        s.manager.list_all = AsyncMock(return_value=[])  # type: ignore[method-assign]

        cleaned = await s.manager.cleanup_orphans({"ticket-1"})

        assert cleaned == []
