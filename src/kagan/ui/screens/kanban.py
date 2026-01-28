"""Main Kanban board screen."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from textual import getters
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import Footer, Static

from kagan.agents.worktree import WorktreeError
from kagan.constants import COLUMN_ORDER
from kagan.database.models import Ticket, TicketCreate, TicketStatus, TicketType, TicketUpdate
from kagan.sessions.tmux import TmuxError
from kagan.ui.modals import (
    ConfirmModal,
    DiffModal,
    ModalAction,
    RejectionInputModal,
    ReviewModal,
    TicketDetailsModal,
)
from kagan.ui.screens.base import KaganScreen
from kagan.ui.screens.planner import PlannerScreen
from kagan.ui.widgets.card import TicketCard
from kagan.ui.widgets.column import KanbanColumn
from kagan.ui.widgets.header import KaganHeader

if TYPE_CHECKING:
    from textual import events
    from textual.app import ComposeResult

    from kagan.messages import TicketChanged


# Minimum terminal size for proper display
MIN_WIDTH = 80
MIN_HEIGHT = 20

# Warning message for small terminal
SIZE_WARNING_MESSAGE = (
    f"Terminal too small\n\nMinimum size: {MIN_WIDTH}x{MIN_HEIGHT}\nPlease resize your terminal"
)


class KanbanScreen(KaganScreen):
    """Main Kanban board screen with 4 columns."""

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("h", "focus_left", "Left column", show=False),
        Binding("l", "focus_right", "Right column", show=False),
        Binding("j", "focus_down", "Down", show=False),
        Binding("k", "focus_up", "Up", show=False),
        Binding("n", "new_ticket", "New ticket"),
        Binding("e", "edit_ticket", "Edit ticket"),
        Binding("x", "delete_ticket", "Delete ticket"),
        Binding("right_square_bracket", "move_forward", "Move->"),
        Binding("left_square_bracket", "move_backward", "Move<-"),
        Binding("enter", "open_session", "Open Session"),
        Binding("v", "view_details", "View details"),
        Binding("t", "toggle_type", "Toggle Type"),
        Binding("w", "watch_agent", "Watch", show=False),
        Binding("m", "merge", "Merge", show=False),
        Binding("d", "view_diff", "View Diff", show=False),
        Binding("R", "open_review", "Review", show=False),
        Binding("s", "rerun_checks", "Re-run checks", show=False),
        Binding("escape", "deselect", "Deselect", show=False),
        Binding("c", "open_chat", "Chat"),
    ]

    header = getters.query_one(KaganHeader)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tickets: list[Ticket] = []
        self._pending_delete_ticket: Ticket | None = None
        self._pending_merge_ticket: Ticket | None = None
        self._editing_ticket_id: str | None = None

    def compose(self) -> ComposeResult:
        """Compose the Kanban board layout."""
        yield KaganHeader(ticket_count=0)

        with Container(classes="board-container"):
            with Horizontal(classes="board"):
                for status in COLUMN_ORDER:
                    yield KanbanColumn(status=status, tickets=[])

        with Container(classes="size-warning"):
            yield Static(
                SIZE_WARNING_MESSAGE,
                classes="size-warning-text",
            )

        yield Footer()

    async def on_mount(self) -> None:
        self._check_screen_size()
        await self._refresh_board()
        self._focus_first_card()
        # Subscribe to ticket changes from any source (UI, MCP, external)
        self.kagan_app.ticket_changed_signal.subscribe(self, self._on_ticket_changed)
        # Fetch git branch for header
        from kagan.ui.widgets.header import _get_git_branch

        config_path = self.kagan_app.config_path
        repo_root = config_path.parent.parent
        branch = await _get_git_branch(repo_root)
        self.header.update_branch(branch)

    async def _on_ticket_changed(self, _ticket_id: str) -> None:
        """Handle ticket change signal - refresh the board."""
        await self._refresh_board()

    def on_resize(self, event: events.Resize) -> None:
        """Handle terminal resize."""
        self._check_screen_size()

    async def on_screen_resume(self) -> None:
        """Refresh board when returning from another screen."""
        await self._refresh_board()

    def _check_screen_size(self) -> None:
        """Check if terminal is large enough and show warning if not."""
        size = self.app.size
        if size.width < MIN_WIDTH or size.height < MIN_HEIGHT:
            self.add_class("too-small")
        else:
            self.remove_class("too-small")

    async def _refresh_board(self) -> None:
        self._tickets = await self.kagan_app.state_manager.get_all_tickets()
        for status in COLUMN_ORDER:
            column = self.query_one(f"#column-{status.value.lower()}", KanbanColumn)
            column.update_tickets([t for t in self._tickets if t.status == status])
        self.header.update_count(len(self._tickets))
        active_sessions = sum(1 for ticket in self._tickets if ticket.session_active)
        self.header.update_sessions(active_sessions)

    def _get_columns(self) -> list[KanbanColumn]:
        return [self.query_one(f"#column-{s.value.lower()}", KanbanColumn) for s in COLUMN_ORDER]

    def _get_focused_card(self) -> TicketCard | None:
        focused = self.app.focused
        return focused if isinstance(focused, TicketCard) else None

    def _focus_first_card(self) -> None:
        for col in self._get_columns():
            if col.focus_first_card():
                return

    def _focus_column(self, status: TicketStatus) -> None:
        col = self.query_one(f"#column-{status.value.lower()}", KanbanColumn)
        col.focus_first_card()

    # Navigation actions

    def _focus_horizontal(self, direction: int) -> None:
        card = self._get_focused_card()
        if not card or not card.ticket:
            return
        columns = self._get_columns()
        col_idx = next((i for i, s in enumerate(COLUMN_ORDER) if s == card.ticket.status), -1)
        target_idx = col_idx + direction
        if target_idx < 0 or target_idx >= len(COLUMN_ORDER):
            return
        card_idx = columns[col_idx].get_focused_card_index() or 0
        cards = columns[target_idx].get_cards()
        if cards:
            columns[target_idx].focus_card(min(card_idx, len(cards) - 1))

    def action_focus_left(self) -> None:
        self._focus_horizontal(-1)

    def action_focus_right(self) -> None:
        self._focus_horizontal(1)

    def _focus_vertical(self, direction: int) -> None:
        card = self._get_focused_card()
        if not card or not card.ticket:
            return
        status = card.ticket.status
        status_str = status.value if isinstance(status, TicketStatus) else status
        col = self.query_one(f"#column-{status_str.lower()}", KanbanColumn)
        idx = col.get_focused_card_index()
        cards = col.get_cards()
        if idx is not None:
            new_idx = idx + direction
            if 0 <= new_idx < len(cards):
                col.focus_card(new_idx)

    def action_focus_up(self) -> None:
        self._focus_vertical(-1)

    def action_focus_down(self) -> None:
        self._focus_vertical(1)

    def action_deselect(self) -> None:
        """Deselect current card."""
        self.app.set_focus(None)

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()

    # Ticket operations

    def action_new_ticket(self) -> None:
        """Open modal to create a new ticket."""
        self.app.push_screen(TicketDetailsModal(), callback=self._on_ticket_modal_result)

    async def _on_ticket_modal_result(
        self, result: ModalAction | TicketCreate | TicketUpdate | None
    ) -> None:
        """Handle ticket modal result (create, edit, delete actions)."""
        if isinstance(result, TicketCreate):
            await self.kagan_app.state_manager.create_ticket(result)
            await self._refresh_board()
            self.notify(f"Created ticket: {result.title}")
        elif isinstance(result, TicketUpdate) and self._editing_ticket_id is not None:
            await self.kagan_app.state_manager.update_ticket(self._editing_ticket_id, result)
            await self._refresh_board()
            self.notify("Ticket updated")
            self._editing_ticket_id = None
        elif result == ModalAction.DELETE:
            self.action_delete_ticket()

    def action_edit_ticket(self) -> None:
        """Open modal to edit the selected ticket (directly in edit mode)."""
        card = self._get_focused_card()
        if card and card.ticket:
            self._editing_ticket_id = card.ticket.id
            self.app.push_screen(
                TicketDetailsModal(ticket=card.ticket, start_editing=True),
                callback=self._on_ticket_modal_result,
            )

    def action_delete_ticket(self) -> None:
        """Delete the selected ticket with confirmation."""
        card = self._get_focused_card()
        if card and card.ticket:
            self._pending_delete_ticket = card.ticket
            self.app.push_screen(
                ConfirmModal(title="Delete Ticket?", message=f'"{card.ticket.title}"'),
                callback=self._on_delete_confirmed,
            )

    async def _on_delete_confirmed(self, confirmed: bool | None) -> None:
        if confirmed and self._pending_delete_ticket:
            ticket = self._pending_delete_ticket

            # Stop agent if running (AUTO tickets)
            scheduler = self.kagan_app.scheduler
            if scheduler.is_running(ticket.id):
                agent = scheduler.get_running_agent(ticket.id)
                if agent:
                    await agent.stop()

            # Kill tmux session if exists
            await self.kagan_app.session_manager.kill_session(ticket.id)

            # Delete worktree if exists
            worktree = self.kagan_app.worktree_manager
            if await worktree.get_path(ticket.id):
                await worktree.delete(ticket.id, delete_branch=True)

            # Delete ticket from database
            await self.kagan_app.state_manager.delete_ticket(ticket.id)
            await self._refresh_board()
            self.notify(f"Deleted ticket: {ticket.title}")
            self._focus_first_card()
        self._pending_delete_ticket = None

    async def _move_ticket(self, forward: bool) -> None:
        card = self._get_focused_card()
        if not card or not card.ticket:
            return
        status = TicketStatus(card.ticket.status)
        new_status = (
            TicketStatus.next_status(status) if forward else TicketStatus.prev_status(status)
        )
        if new_status:
            # REVIEW -> DONE requires merge confirmation
            if status == TicketStatus.REVIEW and new_status == TicketStatus.DONE:
                self._pending_merge_ticket = card.ticket
                title = card.ticket.title[:40]
                msg = f"Merge '{title}' and move to DONE?\n\nCleanup worktree and session."
                self.app.push_screen(
                    ConfirmModal(title="Complete Ticket?", message=msg),
                    callback=self._on_merge_confirmed,
                )
                return

            await self.kagan_app.state_manager.move_ticket(card.ticket.id, new_status)
            await self._refresh_board()
            self.notify(f"Moved #{card.ticket.id} to {new_status.value}")
            self._focus_column(new_status)
        else:
            self.notify(f"Already in {'final' if forward else 'first'} status", severity="warning")

    async def _on_merge_confirmed(self, confirmed: bool | None) -> None:
        """Handle merge confirmation from ] key on REVIEW ticket."""
        if confirmed and self._pending_merge_ticket:
            ticket = self._pending_merge_ticket
            worktree = self.kagan_app.worktree_manager
            base = self.kagan_app.config.general.default_base_branch

            success, message = await worktree.merge_to_main(ticket.id, base_branch=base)
            if success:
                # Cleanup resources but KEEP the ticket (move to DONE)
                await worktree.delete(ticket.id, delete_branch=True)
                await self.kagan_app.session_manager.kill_session(ticket.id)
                await self.kagan_app.state_manager.move_ticket(ticket.id, TicketStatus.DONE)
                await self._refresh_board()
                self.notify(f"Merged and completed: {ticket.title}")
            else:
                self.notify(message, severity="error")
        self._pending_merge_ticket = None

    async def action_move_forward(self) -> None:
        await self._move_ticket(forward=True)

    async def action_move_backward(self) -> None:
        await self._move_ticket(forward=False)

    def action_view_details(self) -> None:
        """View details of selected ticket."""
        card = self._get_focused_card()
        if card and card.ticket:
            self._editing_ticket_id = card.ticket.id
            self.app.push_screen(
                TicketDetailsModal(ticket=card.ticket),
                callback=self._on_ticket_modal_result,
            )

    async def action_open_session(self) -> None:
        """Open session for selected ticket (tmux for PAIR, modal for AUTO, review for REVIEW)."""
        card = self._get_focused_card()
        if not card or not card.ticket:
            return

        ticket = card.ticket

        # REVIEW tickets always open the review modal
        if ticket.status == TicketStatus.REVIEW:
            await self.action_open_review()
            return

        raw_type = ticket.ticket_type
        ticket_type = TicketType(raw_type) if isinstance(raw_type, str) else raw_type

        if ticket_type == TicketType.AUTO:
            await self._open_auto_session(ticket)
        else:
            await self._open_pair_session(ticket)

    async def _open_auto_session(self, ticket: Ticket) -> None:
        """Handle Enter key for AUTO tickets - show agent output modal."""
        scheduler = self.kagan_app.scheduler
        config = self.kagan_app.config

        # Check if auto_start is enabled - if not, show helpful message
        if not config.general.auto_start:
            self.notify(
                "AUTO mode requires auto_start=true in .kagan/config.toml",
                severity="warning",
            )
            return

        # If in BACKLOG, move to IN_PROGRESS (scheduler will pick it up)
        if ticket.status == TicketStatus.BACKLOG:
            await self.kagan_app.state_manager.move_ticket(ticket.id, TicketStatus.IN_PROGRESS)
            await self._refresh_board()
            self.notify(f"Started AUTO ticket: {ticket.short_id}")
            return

        # If agent is running, open the watch modal
        if scheduler.is_running(ticket.id):
            from kagan.ui.modals.agent_output import AgentOutputModal

            agent = scheduler.get_running_agent(ticket.id)
            iteration = scheduler.get_iteration_count(ticket.id)
            await self.app.push_screen(
                AgentOutputModal(ticket=ticket, agent=agent, iteration=iteration)
            )
        else:
            self.notify(
                "Agent not running yet. Will start on next scheduler tick.",
                severity="warning",
            )

    async def _open_pair_session(self, ticket: Ticket) -> None:
        """Handle Enter key for PAIR tickets - open tmux session."""
        worktree = self.kagan_app.worktree_manager

        try:
            wt_path = await worktree.get_path(ticket.id)
            if wt_path is None:
                base = self.kagan_app.config.general.default_base_branch
                wt_path = await worktree.create(ticket.id, ticket.title, base)

            session_manager = self.kagan_app.session_manager
            if not await session_manager.session_exists(ticket.id):
                await session_manager.create_session(ticket, wt_path)

            if ticket.status == TicketStatus.BACKLOG:
                await self.kagan_app.state_manager.move_ticket(ticket.id, TicketStatus.IN_PROGRESS)

            # Suspend TUI, attach to tmux, resume TUI when detached
            with self.app.suspend():
                session_manager.attach_session(ticket.id)

            # Refresh board after returning from tmux
            await self._refresh_board()
        except (TmuxError, WorktreeError) as exc:
            self.notify(f"Failed to open session: {exc}", severity="error")

    def action_open_chat(self) -> None:
        """Open the planner chat screen."""
        self.app.push_screen(PlannerScreen())

    async def action_toggle_type(self) -> None:
        """Toggle ticket type between AUTO and PAIR."""
        card = self._get_focused_card()
        if not card or not card.ticket:
            return

        ticket = card.ticket
        current_type = ticket.ticket_type
        if isinstance(current_type, str):
            current_type = TicketType(current_type)

        # Toggle between AUTO and PAIR
        new_type = TicketType.PAIR if current_type == TicketType.AUTO else TicketType.AUTO

        await self.kagan_app.state_manager.update_ticket(
            ticket.id, TicketUpdate(ticket_type=new_type)
        )
        await self._refresh_board()
        type_label = "AUTO ⚡" if new_type == TicketType.AUTO else "PAIR 👤"
        self.notify(f"Changed {ticket.short_id} to {type_label}")

    async def action_watch_agent(self) -> None:
        """Watch an AUTO ticket's agent progress."""
        card = self._get_focused_card()
        if not card or not card.ticket:
            return

        ticket = card.ticket

        # Check if it's an AUTO ticket
        ticket_type = ticket.ticket_type
        if isinstance(ticket_type, str):
            ticket_type = TicketType(ticket_type)
        if ticket_type != TicketType.AUTO:
            self.notify("Watch is only for AUTO tickets", severity="warning")
            return

        # Check if agent is running
        scheduler = self.kagan_app.scheduler
        if not scheduler.is_running(ticket.id):
            self.notify("No agent running for this ticket", severity="warning")
            return

        # Open the agent output modal
        from kagan.ui.modals.agent_output import AgentOutputModal

        agent = scheduler.get_running_agent(ticket.id)
        iteration = scheduler.get_iteration_count(ticket.id)
        await self.app.push_screen(
            AgentOutputModal(ticket=ticket, agent=agent, iteration=iteration)
        )

    def _get_review_ticket(self) -> Ticket | None:
        """Get the focused ticket if in REVIEW."""
        card = self._get_focused_card()
        if not card or not card.ticket:
            return None
        if card.ticket.status != TicketStatus.REVIEW:
            self.notify("Ticket is not in REVIEW", severity="warning")
            return None
        return card.ticket

    async def action_merge(self) -> None:
        """Merge ticket worktree to main branch."""
        ticket = self._get_review_ticket()
        if not ticket:
            return

        worktree = self.kagan_app.worktree_manager
        base = self.kagan_app.config.general.default_base_branch
        success, message = await worktree.merge_to_main(ticket.id, base_branch=base)
        if success:
            await worktree.delete(ticket.id, delete_branch=True)
            await self.kagan_app.session_manager.kill_session(ticket.id)
            await self.kagan_app.state_manager.move_ticket(ticket.id, TicketStatus.DONE)
            await self._refresh_board()
            self.notify(f"Merged and completed: {ticket.title}")
        else:
            self.notify(message, severity="error")

    async def action_view_diff(self) -> None:
        """View diff for a review ticket."""
        ticket = self._get_review_ticket()
        if not ticket:
            return

        worktree = self.kagan_app.worktree_manager
        base = self.kagan_app.config.general.default_base_branch
        diff_text = await worktree.get_diff(ticket.id, base_branch=base)
        title = f"Diff: {ticket.short_id} {ticket.title[:40]}"
        await self.app.push_screen(DiffModal(title=title, diff_text=diff_text))

    async def action_open_review(self) -> None:
        """Open review modal for REVIEW ticket."""
        ticket = self._get_review_ticket()
        if not ticket:
            return

        # Get agent config
        from kagan.config import get_fallback_agent_config
        from kagan.data.builtin_agents import get_builtin_agent

        agent_config = None
        default_agent = self.kagan_app.config.general.default_worker_agent
        if builtin := get_builtin_agent(default_agent):
            agent_config = builtin.config
        if not agent_config:
            agent_config = get_fallback_agent_config()

        await self.app.push_screen(
            ReviewModal(
                ticket=ticket,
                worktree_manager=self.kagan_app.worktree_manager,
                agent_config=agent_config,
                base_branch=self.kagan_app.config.general.default_base_branch,
            ),
            callback=self._on_review_result,
        )

    async def _on_review_result(self, result: str | None) -> None:
        """Handle review modal result."""
        ticket = self._get_review_ticket()
        if not ticket:
            return

        if result == "approve":
            await self._do_merge(ticket)
        elif result == "reject":
            await self._handle_reject_with_feedback(ticket)

    async def _do_merge(self, ticket: Ticket) -> None:
        """Merge ticket and move to DONE."""
        worktree = self.kagan_app.worktree_manager
        base = self.kagan_app.config.general.default_base_branch

        success, message = await worktree.merge_to_main(ticket.id, base_branch=base)
        if success:
            await worktree.delete(ticket.id, delete_branch=True)
            await self.kagan_app.session_manager.kill_session(ticket.id)
            await self.kagan_app.state_manager.move_ticket(ticket.id, TicketStatus.DONE)
            await self._refresh_board()
            self.notify(f"Merged and completed: {ticket.title}")
        else:
            self.notify(message, severity="error")

    async def _handle_reject_with_feedback(self, ticket: Ticket) -> None:
        """Handle rejection based on ticket type."""
        ticket_type = ticket.ticket_type
        if isinstance(ticket_type, str):
            ticket_type = TicketType(ticket_type)

        if ticket_type == TicketType.AUTO:
            # Show feedback modal for AUTO tickets
            await self.app.push_screen(
                RejectionInputModal(ticket.title),
                callback=lambda feedback: self._apply_rejection_feedback(ticket, feedback),
            )
        else:
            # PAIR: just move back (user handles via tmux)
            await self.kagan_app.state_manager.move_ticket(ticket.id, TicketStatus.IN_PROGRESS)
            await self._refresh_board()
            self.notify(f"Moved back to IN_PROGRESS: {ticket.title}")

    async def _apply_rejection_feedback(self, ticket: Ticket, feedback: str | None) -> None:
        """Append feedback to description and move to IN_PROGRESS."""
        if feedback:
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

            # Append feedback to description with timestamp
            new_description = ticket.description or ""
            new_description += f"\n\n---\n**Review Feedback ({timestamp}):**\n{feedback}"

            await self.kagan_app.state_manager.update_ticket(
                ticket.id,
                TicketUpdate(description=new_description, status=TicketStatus.IN_PROGRESS),
            )
        else:
            # No feedback, just move back
            await self.kagan_app.state_manager.move_ticket(ticket.id, TicketStatus.IN_PROGRESS)

        await self._refresh_board()
        self.notify(f"Rejected: {ticket.title}")

    async def action_rerun_checks(self) -> None:
        """Re-run acceptance checks for a review ticket."""
        ticket = self._get_review_ticket()
        if not ticket:
            return

        worktree = self.kagan_app.worktree_manager
        wt_path = await worktree.get_path(ticket.id)
        if wt_path is None:
            self.notify("Worktree not found for ticket", severity="error")
            return

        command = ticket.check_command or "pytest && ruff check ."
        process = await asyncio.create_subprocess_shell(command, cwd=wt_path)
        return_code = await process.wait()
        checks_passed = return_code == 0
        await self.kagan_app.state_manager.update_ticket(
            ticket.id, TicketUpdate(checks_passed=checks_passed)
        )
        await self._refresh_board()
        status = "passed" if checks_passed else "failed"
        self.notify(f"Checks {status} for {ticket.short_id}")

    # Message handlers

    def on_ticket_card_selected(self, message: TicketCard.Selected) -> None:
        self.action_view_details()

    async def on_ticket_card_move_requested(self, message: TicketCard.MoveRequested) -> None:
        """Handle ticket move request from card."""
        if message.forward:
            await self.action_move_forward()
        else:
            await self.action_move_backward()

    def on_ticket_card_edit_requested(self, message: TicketCard.EditRequested) -> None:
        """Handle ticket edit request from card."""
        self.action_edit_ticket()

    def on_ticket_card_delete_requested(self, message: TicketCard.DeleteRequested) -> None:
        """Handle ticket delete request from card."""
        self.action_delete_ticket()

    async def on_ticket_card_drag_move(self, message: TicketCard.DragMove) -> None:
        if message.target_status and message.target_status != message.ticket.status:
            await self.kagan_app.state_manager.move_ticket(message.ticket.id, message.target_status)
            await self._refresh_board()
            self.notify(f"Moved #{message.ticket.id} to {message.target_status.value}")
            self._focus_column(message.target_status)

    async def on_ticket_changed(self, message: TicketChanged) -> None:
        """Handle ticket status change from background updates - refresh the board."""
        await self._refresh_board()
