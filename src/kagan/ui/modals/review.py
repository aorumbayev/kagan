"""Modal for reviewing task changes."""

from __future__ import annotations

import asyncio
import inspect
import re
from typing import TYPE_CHECKING, cast

from textual import on
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Label,
    LoadingIndicator,
    RichLog,
    Rule,
    Static,
    TabbedContent,
    TabPane,
)

from kagan.acp import messages
from kagan.agents.agent_factory import AgentFactory, create_agent
from kagan.constants import DIFF_MAX_LENGTH, MODAL_TITLE_MAX_LENGTH
from kagan.core.models.enums import StreamPhase, TaskStatus, TaskType
from kagan.keybindings import REVIEW_BINDINGS
from kagan.limits import AGENT_TIMEOUT
from kagan.ui.utils.animation import WAVE_FRAMES, WAVE_INTERVAL_MS
from kagan.ui.utils.clipboard import copy_with_notification
from kagan.ui.utils.diff import colorize_diff_line
from kagan.ui.widgets import ChatPanel, StreamingOutput

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.timer import Timer

    from kagan.acp.agent import Agent
    from kagan.app import KaganApp
    from kagan.config import AgentConfig
    from kagan.core.models.entities import Task
    from kagan.services.diffs import FileDiff, RepoDiff
    from kagan.services.executions import ExecutionService
    from kagan.services.follow_ups import FollowUpService
    from kagan.services.queued_messages import QueuedMessageService
    from kagan.services.workspaces import WorkspaceService


class ReviewModal(ModalScreen[str | None]):
    """Modal for reviewing task changes."""

    BINDINGS = REVIEW_BINDINGS

    def __init__(
        self,
        task: Task,
        worktree_manager: WorkspaceService,
        agent_config: AgentConfig,
        base_branch: str = "main",
        agent_factory: AgentFactory = create_agent,
        execution_service: ExecutionService | None = None,
        execution_id: str | None = None,
        run_count: int = 0,
        running_agent: Agent | None = None,
        review_agent: Agent | None = None,
        is_reviewing: bool = False,
        is_running: bool = False,
        read_only: bool = False,
        initial_tab: str = "review-summary",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._task_model = task
        self._worktree = worktree_manager
        self._agent_config = agent_config
        self._base_branch = base_branch
        self._agent_factory = agent_factory
        self._execution_service = execution_service
        self._agent: Agent | None = None
        self._execution_id = execution_id
        self._run_count = run_count
        self._live_output_agent = running_agent
        self._live_review_agent = review_agent
        self._is_reviewing = is_reviewing
        self._is_running = is_running
        self._read_only = read_only
        self._initial_tab = initial_tab
        self._live_output_attached = False
        self._live_review_attached = False
        self._review_log_loaded = False
        self._phase: StreamPhase = StreamPhase.IDLE
        self._diff_stats: str = ""
        self._diff_text: str = ""
        self._file_diffs: dict[str, FileDiff] = {}
        self._no_changes: bool = False
        self._anim_timer: Timer | None = None
        self._anim_frame: int = 0
        self._prompt_task: asyncio.Task[None] | None = None
        self._session_id: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="review-modal-container"):
            yield Label(
                f"Review: {self._task_model.title[:MODAL_TITLE_MAX_LENGTH]}",
                id="review-title",
                classes="modal-title",
            )
            yield Label(
                f"Branch: task-{self._task_model.short_id} → {self._base_branch}",
                id="branch-info",
                classes="branch-info",
            )
            yield Rule()

            yield LoadingIndicator(id="review-loading", classes="review-loading")

            with TabbedContent(id="review-tabs", classes="hidden"):
                with TabPane("Summary", id="review-summary"):
                    with VerticalScroll(id="review-summary-scroll"):
                        yield Label("Overview", classes="section-title")
                        with Horizontal(id="review-stats", classes="hidden"):
                            yield Static(id="stat-additions", classes="stat-card")
                            yield Static(id="stat-deletions", classes="stat-card")
                            yield Static(id="stat-files", classes="stat-card")

                        yield Label("Commits", classes="section-title")
                        yield DataTable(id="commits-table")

                        yield Label("Changes", classes="section-title")
                        yield Static(id="diff-stats")

                        if self._task_model.description.strip():
                            yield Label("Description", classes="section-title")
                            yield Static(
                                self._task_model.description.strip(),
                                id="review-description",
                            )

                with TabPane("Diff", id="review-diff"):
                    with Horizontal(id="diff-pane"):
                        yield DataTable(id="diff-files", classes="hidden")
                        yield RichLog(id="diff-log", wrap=False, markup=True)

                with TabPane("AI Review", id="review-ai"):
                    with Vertical(id="ai-review-section", classes="hidden"):
                        with Horizontal(id="ai-review-header"):
                            yield Label("AI Review", classes="section-title")
                            yield Static("", classes="spacer")
                            yield Static(
                                "○ Ready", id="phase-badge", classes="phase-badge phase-idle"
                            )
                            yield Button(
                                "↻ Regenerate",
                                id="regenerate-btn",
                                variant="default",
                                classes="hidden",
                            )
                        with Horizontal(id="ai-review-controls"):
                            yield Button(
                                "Generate Review (g)", id="generate-btn", variant="primary"
                            )
                            yield Button(
                                "Cancel", id="cancel-btn", variant="warning", classes="hidden"
                            )
                        yield ChatPanel(
                            None,
                            allow_input=True,
                            input_placeholder="Send a follow-up message...",
                            output_id="ai-review-output",
                            id="ai-review-chat",
                            classes="hidden",
                        )
                with TabPane("Agent Output", id="review-agent-output"):
                    yield ChatPanel(
                        self._execution_id,
                        allow_input=False,
                        output_id="review-agent-output",
                        id="review-agent-output-chat",
                    )

            yield Rule()

            with Horizontal(classes="button-row hidden"):
                if self._task_model.task_type == TaskType.PAIR:
                    yield Button("Attach", variant="default", id="attach-btn")
                yield Button("Rebase (R)", variant="default", id="rebase-btn")
                yield Button("Approve (Enter)", variant="success", id="approve-btn")
                yield Button("Reject (r)", variant="error", id="reject-btn")

        yield Footer(show_command_palette=False)

    async def on_mount(self) -> None:
        """Load commits and diff immediately."""
        from kagan.debug_log import log

        branch_info = self.query_one("#branch-info", Label)
        workspaces = await self._worktree.list_workspaces(task_id=self._task_model.id)
        if workspaces:
            actual_branch = workspaces[0].branch_name
            branch_info.update(f"Branch: {actual_branch} → {self._base_branch}")

        log.info(f"[ReviewModal] Opening for task {self._task_model.id[:8]}")
        commits = await self._worktree.get_commit_log(self._task_model.id, self._base_branch)

        diff_stats = await self._worktree.get_diff_stats(self._task_model.id, self._base_branch)
        self._diff_text = await self._worktree.get_diff(self._task_model.id, self._base_branch)

        await self.query_one("#review-loading", LoadingIndicator).remove()
        self.query_one("#review-tabs").remove_class("hidden")
        self.query_one("#ai-review-section").remove_class("hidden")
        if not self._read_only:
            self.query_one(".button-row").remove_class("hidden")

        self._populate_commits(commits)

        self.query_one("#diff-stats", Static).update(diff_stats or "[dim](No changes)[/dim]")
        self._diff_stats = diff_stats or ""
        self._no_changes = not commits and not self._diff_stats

        await self._populate_diff_pane(workspaces)

        from kagan.debug_log import log as debug_log

        debug_log.info(
            f"[ReviewModal] Loaded {len(commits or [])} commits, "
            f"diff_length={len(self._diff_stats)}"
        )

        if self._no_changes:
            approve_btn = self.query_one("#approve-btn", Button)
            approve_btn.label = "Close as Exploratory"

        await self._load_agent_output_history()
        await self._configure_follow_up_chat()
        if self._read_only:
            self.query_one("#ai-review-controls", Horizontal).add_class("hidden")
            self.query_one("#regenerate-btn", Button).add_class("hidden")

        if self._execution_service is not None:
            await self._load_prior_review()
        await self._attach_live_output_stream_if_available()
        await self._attach_live_review_stream_if_available()
        auto_started = await self._maybe_auto_start_pair_review()
        self._set_active_tab("review-ai" if auto_started else self._initial_tab)

    def _populate_commits(self, commits: list[str]) -> None:
        table = self.query_one("#commits-table", DataTable)
        table.clear()
        if not table.columns:
            table.add_columns("Repo", "Hash", "Message")
        table.cursor_type = "row"
        table.zebra_stripes = True

        if not commits:
            table.add_row("—", "—", "No commits found")
            return

        for line in commits:
            repo, sha, message = self._parse_commit_line(line)
            table.add_row(repo or "—", sha or "—", message or "—")

    async def _populate_diff_pane(self, workspaces: list) -> None:
        app = cast("KaganApp", self.app)
        diff_service = getattr(app.ctx, "diff_service", None)

        if workspaces and diff_service is not None:
            diffs = await diff_service.get_all_diffs(workspaces[0].id)
            self._populate_file_diffs(diffs)
            total_additions = sum(diff.total_additions for diff in diffs)
            total_deletions = sum(diff.total_deletions for diff in diffs)
            total_files = sum(len(diff.files) for diff in diffs)
            self._set_stats(total_additions, total_deletions, total_files)
            return

        total_additions, total_deletions, total_files = self._parse_diff_totals(self._diff_stats)
        self._set_stats(total_additions, total_deletions, total_files)
        self._render_diff_text(self._diff_text)

    def _populate_file_diffs(self, diffs: list[RepoDiff]) -> None:
        table = self.query_one("#diff-files", DataTable)
        table.clear()
        if not table.columns:
            table.add_columns("File", "+", "-")
        table.cursor_type = "row"
        table.zebra_stripes = True

        self._file_diffs.clear()
        multi_repo = len(diffs) > 1
        for diff in diffs:
            for file in diff.files:
                key = f"{diff.repo_name}:{file.path}"
                self._file_diffs[key] = file
                label = f"{diff.repo_name}/{file.path}" if multi_repo else file.path
                table.add_row(label, str(file.additions), str(file.deletions), key=key)

        if not self._file_diffs:
            table.add_class("hidden")
            self._render_diff_text(self._diff_text)
            return

        table.remove_class("hidden")
        first_key = next(iter(self._file_diffs))
        self._show_file_diff(first_key)

    def _show_file_diff(self, key: str) -> None:
        file_diff = self._file_diffs.get(key)
        if file_diff is None:
            self._render_diff_text(self._diff_text)
            return
        self._render_diff_text(file_diff.diff_content)

    def _render_diff_text(self, diff_text: str) -> None:
        diff_log = self.query_one("#diff-log", RichLog)
        diff_log.clear()
        for line in diff_text.splitlines() or ["(No diff available)"]:
            diff_log.write(colorize_diff_line(line))

    def _set_stats(self, additions: int, deletions: int, files: int) -> None:
        self.query_one("#review-stats", Horizontal).remove_class("hidden")
        self.query_one("#stat-additions", Static).update(f"+ {additions} Additions")
        self.query_one("#stat-deletions", Static).update(f"- {deletions} Deletions")
        self.query_one("#stat-files", Static).update(f"{files} Files Changed")

    def _parse_diff_totals(self, diff_stats: str) -> tuple[int, int, int]:
        if not diff_stats:
            return 0, 0, 0
        pattern = re.compile(r"\+(\d+)\s+-(\d+)\s+\((\d+)\s+file")
        total_line = ""
        for line in diff_stats.splitlines():
            if line.lower().startswith("total:"):
                total_line = line
                break
        if total_line:
            match = pattern.search(total_line)
            if match:
                return int(match.group(1)), int(match.group(2)), int(match.group(3))
        additions = deletions = files = 0
        for line in diff_stats.splitlines():
            match = pattern.search(line)
            if match:
                additions += int(match.group(1))
                deletions += int(match.group(2))
                files += int(match.group(3))
        return additions, deletions, files

    def _parse_commit_line(self, line: str) -> tuple[str, str, str]:
        repo = ""
        rest = line.strip()
        if rest.startswith("["):
            end = rest.find("]")
            if end != -1:
                repo = rest[1:end]
                rest = rest[end + 1 :].strip()
        parts = rest.split(" ", 1)
        sha = parts[0] if parts else ""
        message = parts[1] if len(parts) > 1 else ""
        return repo, sha, message

    async def _resolve_execution_id(self) -> str | None:
        if self._execution_id is not None:
            return self._execution_id
        if self._execution_service is None:
            return None
        execution = await self._execution_service.get_latest_execution_for_task(self._task_model.id)
        if execution is None:
            return None
        self._execution_id = execution.id
        return self._execution_id

    def _get_agent_output_panel(self) -> ChatPanel:
        return self.query_one("#review-agent-output-chat", ChatPanel)

    async def _load_agent_output_history(self) -> None:
        execution_id = await self._resolve_execution_id()
        panel = self._get_agent_output_panel()
        if execution_id is None:
            await panel.output.post_note("No execution logs available", classes="warning")
            return

        app = cast("KaganApp", self.app)
        entries = await app.ctx.execution_service.get_log_entries(execution_id)
        if not entries:
            await panel.output.post_note("No execution logs available", classes="warning")
            return

        has_review_result = False
        execution = await app.ctx.execution_service.get_execution(execution_id)
        if execution and execution.metadata_:
            has_review_result = "review_result" in execution.metadata_

        review_entries = entries[-1:] if has_review_result and len(entries) > 1 else []
        impl_entries = entries[:-1] if review_entries else entries
        for entry in impl_entries:
            if not entry.logs:
                continue
            panel.set_execution_id(None)
            for line in entry.logs.splitlines():
                await panel._render_log_line(line)

        if review_entries:
            chat_panel = self._get_chat_panel()
            chat_panel.remove_class("hidden")
            for entry in review_entries:
                if not entry.logs:
                    continue
                for line in entry.logs.splitlines():
                    await chat_panel._render_log_line(line)
            self._review_log_loaded = True
            self._set_phase(StreamPhase.COMPLETE)

    async def _attach_live_review_stream_if_available(self) -> None:
        if not self._is_reviewing or self._live_review_agent is None:
            return
        chat_panel = self._get_chat_panel()
        chat_panel.remove_class("hidden")
        self._live_review_agent.set_message_target(self)
        self._live_review_attached = True
        await chat_panel.output.post_note("Connected to live review stream", classes="info")
        self._set_phase(StreamPhase.STREAMING)

    async def _attach_live_output_stream_if_available(self) -> None:
        if self._is_reviewing or not self._is_running or self._live_output_agent is None:
            return
        panel = self._get_agent_output_panel()
        self._live_output_agent.set_message_target(self)
        self._live_output_attached = True
        await panel.output.post_note("Connected to live agent stream", classes="info")

    async def _maybe_auto_start_pair_review(self) -> bool:
        if self._read_only or self._live_review_attached or self._review_log_loaded:
            return False
        if self._task_model.task_type != TaskType.PAIR:
            return False
        if self._task_model.status != TaskStatus.REVIEW:
            return False
        if self._phase != StreamPhase.IDLE:
            return False
        app = cast("KaganApp", self.app)
        if not app.ctx.config.general.auto_review:
            return False
        await self.action_generate_review()
        return True

    async def _load_prior_review(self) -> None:
        """Load auto-review results from execution metadata if available."""
        if self._execution_service is None:
            return
        if self._review_log_loaded:
            return
        execution_id = await self._resolve_execution_id()
        if execution_id is None:
            return
        execution = await self._execution_service.get_execution(execution_id)
        if execution is None or not execution.metadata_:
            return
        review_result = execution.metadata_.get("review_result")
        if review_result is None:
            return

        status = review_result.get("status", "")
        summary = review_result.get("summary", "")

        chat_panel = self._get_chat_panel()
        chat_panel.remove_class("hidden")
        output = chat_panel.output

        if status == "approved":
            await output.post_note("Auto-review passed", classes="success")
        else:
            await output.post_note("Auto-review flagged issues", classes="warning")

        if summary:
            await output.post_response(summary)

        self._set_phase(StreamPhase.COMPLETE)

    def _set_phase(self, phase: StreamPhase) -> None:
        """Update phase and UI state."""
        self._phase = phase
        badge = self.query_one("#phase-badge", Static)
        badge.update(f"{phase.icon} {phase.label}")
        badge.set_classes(f"phase-badge phase-{phase.value}")

        gen_btn = self.query_one("#generate-btn", Button)
        cancel_btn = self.query_one("#cancel-btn", Button)
        regen_btn = self.query_one("#regenerate-btn", Button)

        if phase == StreamPhase.IDLE:
            self._stop_animation()
            gen_btn.remove_class("hidden")
            gen_btn.disabled = False
            cancel_btn.add_class("hidden")
            regen_btn.add_class("hidden")
        elif phase in (StreamPhase.THINKING, StreamPhase.STREAMING):
            self._start_animation()
            gen_btn.add_class("hidden")
            cancel_btn.remove_class("hidden")
            regen_btn.add_class("hidden")
        else:
            self._stop_animation()
            gen_btn.add_class("hidden")
            cancel_btn.add_class("hidden")
            regen_btn.remove_class("hidden")

    def _get_chat_panel(self) -> ChatPanel:
        return self.query_one("#ai-review-chat", ChatPanel)

    def _get_stream_output(self) -> StreamingOutput:
        if self._live_review_attached or self._agent is not None:
            return self._get_chat_panel().output
        if self._live_output_attached:
            return self._get_agent_output_panel().output
        return self._get_chat_panel().output

    async def _configure_follow_up_chat(self) -> None:
        panel = self._get_chat_panel()
        panel.set_send_handler(self._send_follow_up)

    def _get_queue_service(self) -> QueuedMessageService | None:
        app = cast("KaganApp", self.app)
        service = getattr(app.ctx, "queued_message_service", None)
        if service is None:
            return None
        return cast("QueuedMessageService", service)

    def _get_follow_up_service(self) -> FollowUpService | None:
        app = cast("KaganApp", self.app)
        service = getattr(app.ctx, "follow_up_service", None)
        if service is None:
            return None
        return cast("FollowUpService", service)

    async def _resolve_session_id(self) -> str | None:
        if self._session_id is not None:
            return self._session_id
        app = cast("KaganApp", self.app)
        latest = await app.ctx.execution_service.get_latest_execution_for_task(self._task_model.id)
        if latest is None:
            return None
        self._session_id = latest.session_id
        return self._session_id

    async def _send_follow_up(self, content: str) -> None:
        service = self._get_queue_service()
        session_id = await self._resolve_session_id()
        if service is None or session_id is None:
            raise RuntimeError("Follow-up queue unavailable")
        result = service.queue_message(session_id, content)
        if inspect.isawaitable(result):
            await result

        follow_up = self._get_follow_up_service()
        if follow_up is None or session_id is None:
            return
        try:
            if hasattr(follow_up, "resume_follow_up"):
                result = follow_up.resume_follow_up(session_id)
            elif hasattr(follow_up, "start_follow_up"):
                result = follow_up.start_follow_up(session_id)
            else:
                return
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            self.notify(f"Follow-up start failed: {exc}", severity="warning")

    def _start_animation(self) -> None:
        """Start wave animation for thinking/streaming state."""
        if self._anim_timer is None:
            self._anim_frame = 0
            self._anim_timer = self.set_interval(WAVE_INTERVAL_MS / 1000, self._next_frame)

    def _stop_animation(self) -> None:
        """Stop wave animation."""
        if self._anim_timer is not None:
            self._anim_timer.stop()
            self._anim_timer = None

    def _next_frame(self) -> None:
        """Advance to next animation frame."""
        self._anim_frame = (self._anim_frame + 1) % len(WAVE_FRAMES)
        badge = self.query_one("#phase-badge", Static)
        badge.update(f"{WAVE_FRAMES[self._anim_frame]} {self._phase.label}")

    @on(DataTable.RowHighlighted, "#diff-files")
    def on_diff_file_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._show_file_diff(str(event.row_key))

    @on(Button.Pressed, "#generate-btn")
    async def on_generate_btn(self) -> None:
        await self.action_generate_review()

    @on(Button.Pressed, "#regenerate-btn")
    async def on_regenerate_btn(self) -> None:
        await self.action_regenerate_review()

    @on(Button.Pressed, "#cancel-btn")
    async def on_cancel_btn(self) -> None:
        await self.action_cancel_review()

    @on(Button.Pressed, "#rebase-btn")
    async def on_rebase_btn(self) -> None:
        await self.action_rebase()

    @on(Button.Pressed, "#attach-btn")
    async def on_attach_btn(self) -> None:
        await self.action_attach_session()

    @on(Button.Pressed, "#approve-btn")
    def on_approve_btn(self) -> None:
        self.action_approve()

    @on(Button.Pressed, "#reject-btn")
    def on_reject_btn(self) -> None:
        self.action_reject()

    def action_show_summary(self) -> None:
        self._set_active_tab("review-summary")

    def action_show_diff(self) -> None:
        self._set_active_tab("review-diff")

    def action_show_ai_review(self) -> None:
        self._set_active_tab("review-ai")

    def action_show_agent_output(self) -> None:
        self._set_active_tab("review-agent-output")

    def _set_active_tab(self, tab_id: str) -> None:
        tabs = self.query_one("#review-tabs", TabbedContent)
        tabs.active = tab_id

    async def action_attach_session(self) -> None:
        if self._task_model.task_type != TaskType.PAIR:
            return
        app = cast("KaganApp", self.app)
        if not await app.ctx.session_service.session_exists(self._task_model.id):
            self.notify("No active session for this task", severity="warning")
            return
        with self.app.suspend():
            await app.ctx.session_service.attach_session(self._task_model.id)

    async def action_generate_review(self) -> None:
        """Generate or regenerate AI review."""
        from kagan.debug_log import log

        if self._read_only:
            self.notify("Read-only history view", severity="warning")
            return
        if self._live_review_attached:
            self.notify("Review is already running", severity="information")
            return

        log.info(f"[ReviewModal] Starting AI review (phase={self._phase})")

        if self._phase == StreamPhase.COMPLETE:
            await self.action_regenerate_review()
            return
        if self._phase != StreamPhase.IDLE:
            return

        self._set_phase(StreamPhase.THINKING)
        chat_panel = self._get_chat_panel()
        chat_panel.remove_class("hidden")
        output = chat_panel.output
        await self._generate_ai_review(output)

    async def action_regenerate_review(self) -> None:
        """Regenerate AI review."""
        if self._phase != StreamPhase.COMPLETE:
            return

        if self._agent:
            await self._agent.stop()
            self._agent = None

        output = self._get_chat_panel().output
        await output.clear()
        self._set_phase(StreamPhase.THINKING)
        await self._generate_ai_review(output)

    async def action_cancel_review(self) -> None:
        """Cancel ongoing review."""
        if self._live_review_attached and self._agent is None:
            self.notify("Review is managed by automation", severity="warning")
            return
        if self._phase not in (StreamPhase.THINKING, StreamPhase.STREAMING):
            return

        if self._prompt_task and not self._prompt_task.done():
            self._prompt_task.cancel()
        if self._agent:
            await self._agent.stop()
            self._agent = None

        output = self._get_chat_panel().output
        await output.post_note("Review cancelled", classes="dismissed")
        self._set_phase(StreamPhase.IDLE)

    async def action_view_diff(self) -> None:
        """Open the diff modal for the current task."""
        await self._open_diff_modal()

    async def _open_diff_modal(self) -> None:
        from kagan.ui.modals import DiffModal

        app = cast("KaganApp", self.app)
        workspaces = await self._worktree.list_workspaces(task_id=self._task_model.id)
        title = (
            f"Diff: {self._task_model.short_id} {self._task_model.title[:MODAL_TITLE_MAX_LENGTH]}"
        )
        diff_service = getattr(app.ctx, "diff_service", None)

        if not workspaces or diff_service is None:
            diff_text = self._diff_text or await self._worktree.get_diff(
                self._task_model.id, self._base_branch
            )
            await self.app.push_screen(
                DiffModal(title=title, diff_text=diff_text, task=self._task_model),
                callback=self._on_diff_result,
            )
            return

        diffs = await diff_service.get_all_diffs(workspaces[0].id)
        await self.app.push_screen(
            DiffModal(title=title, diffs=diffs, task=self._task_model),
            callback=self._on_diff_result,
        )

    def _on_diff_result(self, result: str | None) -> None:
        if result == "approve":
            self.action_approve()
        elif result == "reject":
            self.action_reject()

    async def _generate_ai_review(self, output: StreamingOutput) -> None:
        """Spawn agent to generate code review."""
        from kagan.debug_log import log

        wt_path = await self._worktree.get_path(self._task_model.id)
        if not wt_path:
            await output.post_note("Error: Worktree not found", classes="error")
            self._set_phase(StreamPhase.IDLE)
            return

        diff = self._diff_text or await self._worktree.get_diff(
            self._task_model.id, self._base_branch
        )
        if not diff:
            await output.post_note("No diff to review", classes="info")
            self._set_phase(StreamPhase.IDLE)
            return

        self._agent = self._agent_factory(wt_path, self._agent_config, read_only=True)
        self._agent.start(self)

        await output.post_note("Analyzing changes...", classes="info")
        log.info("[ReviewModal] Agent started, waiting for response")

        try:
            await self._agent.wait_ready(timeout=AGENT_TIMEOUT)
        except Exception as e:
            await output.post_note(f"Review failed: {e}", classes="error")
            self._set_phase(StreamPhase.IDLE)
            return

        review_prompt = f"""You are a Code Review Specialist providing feedback on changes.

## Core Principles

- Iterative refinement: inspect, re-check, then summarize.
- Clarity & specificity: concise, unambiguous, actionable.
- Learning by example: follow the example format below.
- Structured reasoning: let's think step by step for complex changes.
- Separate reasoning from the final summary.

## Safety & Secrets

Never access or request secrets/credentials/keys (e.g., `.env`, `.env.*`, `id_rsa`,
`*.pem`, `*.key`, `credentials.json`). If a recommendation requires secrets, ask
for redacted values or suggest safe mocks.

## Context

**Task:** {self._task_model.title}

## Changes to Review

```diff
{diff[:DIFF_MAX_LENGTH]}
```

## Output Format

Reasoning:
- 2-5 brief steps that justify your assessment

Findings:
- Specific issues or improvements (if any)

Summary:
- Concise recommendation(s)

## Examples

Example 1: Minor improvement needed
Reasoning:
- Validation was added, but the error message is vague.
Findings:
- Suggest clearer error copy for invalid input.
Summary:
- Solid change; improve error messaging clarity.

Example 2: Potential bug
Reasoning:
- New logic uses `or` where `and` is required for all conditions.
Findings:
- This could bypass required validation in edge cases.
Summary:
- Fix boolean condition before shipping.

Example 3: Missing tests
Reasoning:
- Feature adds a new branch with no coverage.
Findings:
- Add unit tests for the new branch behavior.
Summary:
- Add tests to cover new logic.

Keep your review brief and actionable."""

        self._prompt_task = asyncio.create_task(self._run_prompt(review_prompt, output))

    async def _run_prompt(self, prompt: str, output: StreamingOutput) -> None:
        """Run prompt in background, handle errors."""
        if self._agent is None:
            return
        try:
            await self._agent.send_prompt(prompt)
        except Exception as e:
            await output.post_note(f"Review failed: {e}", classes="error")
            self._set_phase(StreamPhase.IDLE)

    @on(messages.AgentUpdate)
    async def on_agent_update(self, message: messages.AgentUpdate) -> None:
        """Handle agent text output."""
        if self._phase == StreamPhase.THINKING:
            self._set_phase(StreamPhase.STREAMING)
        output = self._get_stream_output()
        await output.post_response(message.text)

    @on(messages.Thinking)
    async def on_agent_thinking(self, message: messages.Thinking) -> None:
        """Handle agent thinking."""
        output = self._get_stream_output()
        await output.post_thought(message.text)

    @on(messages.ToolCall)
    async def on_tool_call(self, message: messages.ToolCall) -> None:
        tool_id = message.tool_call.tool_call_id
        title = message.tool_call.title
        kind = message.tool_call.kind or ""
        await self._get_stream_output().post_tool_call(tool_id, title, kind)

    @on(messages.ToolCallUpdate)
    async def on_tool_call_update(self, message: messages.ToolCallUpdate) -> None:
        tool_id = message.update.tool_call_id
        status = message.update.status or ""
        if status:
            self._get_stream_output().update_tool_status(tool_id, status)

    @on(messages.AgentReady)
    async def on_agent_ready(self, _: messages.AgentReady) -> None:
        await self._get_stream_output().post_note("Agent ready", classes="success")

    @on(messages.Plan)
    async def on_plan(self, message: messages.Plan) -> None:
        await self._get_stream_output().post_plan(message.entries)

    @on(messages.AgentComplete)
    async def on_agent_complete(self, _: messages.AgentComplete) -> None:
        """Handle agent completion."""
        if self._live_output_attached and self._agent is None:
            self._live_output_attached = False
        if self._live_review_attached and self._agent is None:
            self._live_review_attached = False
        self._set_phase(StreamPhase.COMPLETE)

    @on(messages.AgentFail)
    async def on_agent_fail(self, message: messages.AgentFail) -> None:
        """Handle agent failure."""
        output = self._get_stream_output()
        await output.post_note(f"Error: {message.message}", classes="error")
        if self._live_output_attached and self._agent is None:
            self._live_output_attached = False
        if self._live_review_attached and self._agent is None:
            self._live_review_attached = False
        self._set_phase(StreamPhase.IDLE)

    async def action_rebase(self) -> None:
        """Rebase the task branch onto the base branch."""
        if self._read_only:
            self.notify("Read-only history view", severity="warning")
            return
        self.notify("Rebasing...", severity="information")
        success, message, conflict_files = await self._worktree.rebase_onto_base(
            self._task_model.id, self._base_branch
        )
        if success:
            # Refresh diff pane
            self._diff_text = await self._worktree.get_diff(self._task_model.id, self._base_branch)
            self._render_diff_text(self._diff_text)
            diff_stats = await self._worktree.get_diff_stats(self._task_model.id, self._base_branch)
            self.query_one("#diff-stats", Static).update(diff_stats or "[dim](No changes)[/dim]")
            self.notify("Rebase successful", severity="information")
        elif conflict_files:
            self.dismiss("rebase_conflict")
        else:
            self.notify(f"Rebase failed: {message}", severity="error")

    def action_approve(self) -> None:
        """Approve the review."""
        if self._read_only:
            self.notify("Read-only history view", severity="warning")
            return
        if self._no_changes:
            self.dismiss("exploratory")
        else:
            self.dismiss("approve")

    def action_reject(self) -> None:
        """Reject the review."""
        if self._read_only:
            self.notify("Read-only history view", severity="warning")
            return
        self.dismiss("reject")

    async def action_close_or_cancel(self) -> None:
        """Cancel review if in progress, otherwise close."""
        if self._phase in (StreamPhase.THINKING, StreamPhase.STREAMING):
            await self.action_cancel_review()
        else:
            self.dismiss(None)

    def action_copy(self) -> None:
        """Copy review content to clipboard."""
        output = self._get_chat_panel().output
        review_text = output._agent_response._markdown if output._agent_response else ""

        content_parts = [f"# Review: {self._task_model.title}"]
        if self._diff_stats:
            content_parts.append(f"\n## Changes\n{self._diff_stats}")
        if review_text:
            content_parts.append(f"\n## AI Review\n{review_text}")

        copy_with_notification(self.app, "\n".join(content_parts), "Review")

    async def on_unmount(self) -> None:
        """Cleanup agent and animation on close."""
        self._stop_animation()
        if self._prompt_task and not self._prompt_task.done():
            self._prompt_task.cancel()
        if self._agent:
            await self._agent.stop()
        if self._live_output_agent:
            self._live_output_agent.set_message_target(None)
        if self._live_review_agent:
            self._live_review_agent.set_message_target(None)
