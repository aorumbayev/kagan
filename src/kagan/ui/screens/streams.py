"""Agent streams screen for viewing agent output in tabbed interface."""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from textual import getters, on
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.css.query import NoMatches
from textual.timer import Timer
from textual.widgets import Footer, Static, TabbedContent, TabPane

from kagan.acp import messages
from kagan.agents.roles import AgentRole
from kagan.ui.screens.base import KaganScreen
from kagan.ui.widgets import StreamingOutput
from kagan.ui.widgets.header import KaganHeader

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from kagan.acp.agent import Agent

# Tab IDs
REVIEWER_TAB_ID = "reviewer"


class BaseStreamPane(TabPane):
    """Base class for stream panes with shared message handlers."""

    def get_output(self) -> StreamingOutput | None:
        """Get the StreamingOutput widget. Override in subclasses."""
        return None

    async def _write_stream(self, text: str) -> None:
        """Write to the streaming output (smooth rendering)."""
        output = self.get_output()
        if output:
            await output.write(text)

    def _write_status(self, text: str, style: str = "") -> None:
        """Write to the status log (discrete entries)."""
        output = self.get_output()
        if output:
            output.write_status(text, style)

    @on(messages.AgentUpdate)
    async def on_agent_update(self, message: messages.AgentUpdate) -> None:
        if message.type == "terminal":
            self._write_status(message.text, style="bold yellow")
        elif message.type == "terminal_output":
            self._write_status(message.text, style="dim")
        elif message.type == "terminal_exit":
            self._write_status(message.text)
        else:
            # Main AI output - use smooth streaming
            await self._write_stream(message.text)

    @on(messages.Thinking)
    async def on_agent_thinking(self, message: messages.Thinking) -> None:
        # Thinking can be chunked, so use main stream with italic formatting
        await self._write_stream(f"*{message.text}*")

    @on(messages.ToolCall)
    def on_tool_call(self, message: messages.ToolCall) -> None:
        title = message.tool_call.get("title", "Tool call")
        kind = message.tool_call.get("kind", "")
        self._write_status(f"\n[bold cyan]> {title}[/bold cyan]")
        if kind:
            self._write_status(f"  [dim]({kind})[/dim]")

    @on(messages.ToolCallUpdate)
    def on_tool_call_update(self, message: messages.ToolCallUpdate) -> None:
        status = message.update.get("status")
        if status:
            style = "green" if status == "completed" else "yellow"
            self._write_status(f"  [{style}]{status}[/{style}]")

    @on(messages.AgentReady)
    def on_agent_ready(self, message: messages.AgentReady) -> None:
        self._write_status("[green]Agent ready[/green]\n")

    @on(messages.AgentFail)
    def on_agent_fail(self, message: messages.AgentFail) -> None:
        self._write_status(f"[red bold]Error: {message.message}[/red bold]")
        if message.details:
            self._write_status(f"[red]{message.details}[/red]")


class AgentStreamPane(BaseStreamPane):
    """Individual agent tab with status display and streaming output."""

    def __init__(
        self,
        agent_id: str,
        title: str | None = None,
        **kwargs,
    ) -> None:
        display_title = title or agent_id
        super().__init__(display_title, id=f"agent-{agent_id}", **kwargs)
        self.agent_id = agent_id
        # Note: Don't hold agent reference - use agent_id to look up via manager
        # This prevents memory leaks when agents terminate
        self._is_running = True

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold green]RUNNING[/bold green]",
            id=f"status-{self.agent_id}",
            classes="stream-status",
        )
        yield StreamingOutput(
            show_status_log=True,
            id=f"output-{self.agent_id}",
            classes="stream-output",
        )

    @property
    def is_running(self) -> bool:
        return self._is_running

    def set_running(self, running: bool) -> None:
        self._is_running = running
        with suppress(NoMatches):
            status = self.query_one(f"#status-{self.agent_id}", Static)
            if running:
                status.update("[bold green]RUNNING[/bold green]")
            else:
                status.update("[bold blue]STOPPED[/bold blue]")

    def get_output(self) -> StreamingOutput | None:
        try:
            return self.query_one(f"#output-{self.agent_id}", StreamingOutput)
        except NoMatches:
            return None


class ReviewerPane(BaseStreamPane):
    """Fixed reviewer tab showing review agent activity."""

    def __init__(self, **kwargs) -> None:
        super().__init__("Reviewer", id=REVIEWER_TAB_ID, **kwargs)

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold cyan]REVIEW AGENT[/bold cyan]",
            id="reviewer-status",
            classes="stream-status",
        )
        yield StreamingOutput(
            show_status_log=True,
            id="reviewer-output",
            classes="stream-output",
        )

    def get_output(self) -> StreamingOutput | None:
        try:
            return self.query_one("#reviewer-output", StreamingOutput)
        except NoMatches:
            return None

    def log_review_start(self, ticket_id: str) -> None:
        self._write_status(f"\n[bold cyan]--- Review started for {ticket_id} ---[/bold cyan]\n")

    def log_decision(self, approved: bool, ticket_id: str) -> None:
        if approved:
            self._write_status(
                f"[bold green]APPROVED[/bold green] - Ticket {ticket_id} passed review\n"
            )
        else:
            self._write_status(
                f"[bold red]REJECTED[/bold red] - Ticket {ticket_id} needs changes\n"
            )

    def log_summary(self, summary: str) -> None:
        self._write_status(f"[dim]{summary}[/dim]\n")


class AgentStreamsScreen(KaganScreen):
    """Full-screen tabbed view of agent output streams."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("h", "prev_tab", "Prev Tab", show=False),
        Binding("l", "next_tab", "Next Tab", show=False),
        Binding("j", "scroll_down", "Scroll Down", show=False),
        Binding("k", "scroll_up", "Scroll Up", show=False),
    ]

    header = getters.query_one(KaganHeader)

    def __init__(self, **kwargs) -> None:
        """Initialize agent streams screen."""
        super().__init__(**kwargs)
        self._agent_panes: dict[str, AgentStreamPane] = {}
        self._reviewer_pane: ReviewerPane | None = None
        self._subscribed_agents: set[str] = set()
        self._tab_refresh_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        """Compose the streams screen layout."""
        yield KaganHeader(ticket_count=0)
        with Vertical(id="streams-container"):
            with TabbedContent(id="streams-tabs"):
                # Fixed reviewer tab
                yield ReviewerPane()
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize screen on mount."""
        # Store reference to reviewer pane
        self._reviewer_pane = self.query_one(f"#{REVIEWER_TAB_ID}", ReviewerPane)

        # Initial tab refresh
        self._refresh_agent_tabs()

        # Set up periodic refresh
        self._tab_refresh_timer = self.set_interval(2.0, self._refresh_agent_tabs)

        # Update header
        self.header.update_count(len(self._agent_panes))

    def on_unmount(self) -> None:
        """Unsubscribe from agent streams and clean up resources."""
        # Stop the refresh timer
        if self._tab_refresh_timer:
            self._tab_refresh_timer.stop()
            self._tab_refresh_timer = None

        # Unsubscribe from agent streams
        manager = self.kagan_app.agent_manager
        for agent_id in list(self._subscribed_agents):
            role = manager.get_role(agent_id)
            if role == AgentRole.REVIEWER:
                if self._reviewer_pane:
                    manager.unsubscribe(agent_id, self._reviewer_pane)
            else:
                if pane := self._agent_panes.get(agent_id):
                    manager.unsubscribe(agent_id, pane)
        self._subscribed_agents.clear()

        # Clear pane references to allow garbage collection
        self._agent_panes.clear()
        self._reviewer_pane = None

    def _refresh_agent_tabs(self) -> None:
        """Refresh tabs based on active agents.

        - Add new tabs for newly spawned agents
        - Mark stopped tabs (update status)
        """
        try:
            manager = self.kagan_app.agent_manager
            active_ids = set(manager.list_active())
            known_ids = manager.list_known()

            tabbed = self.query_one("#streams-tabs", TabbedContent)

            # Add new tabs for known agents (including inactive ones with logs)
            for agent_id in known_ids:
                role = manager.get_role(agent_id)
                if role == AgentRole.REVIEWER:
                    if agent_id not in self._subscribed_agents and self._reviewer_pane:
                        manager.subscribe(agent_id, self._reviewer_pane)
                        self._subscribed_agents.add(agent_id)
                    continue
                if agent_id in self._agent_panes:
                    continue
                short_title = agent_id[:8] if len(agent_id) > 8 else agent_id
                pane = AgentStreamPane(
                    agent_id=agent_id,
                    title=short_title,
                )
                self._agent_panes[agent_id] = pane
                tabbed.add_pane(pane)
                manager.subscribe(agent_id, pane)
                self._subscribed_agents.add(agent_id)

            # Update status for existing panes
            for agent_id, pane in self._agent_panes.items():
                is_active = agent_id in active_ids
                if pane.is_running != is_active:
                    pane.set_running(is_active)

            # Update header with agent count
            self.header.update_agents(
                manager.count_active(AgentRole.WORKER),
                self.kagan_app.config.general.max_concurrent_agents,
            )

        except NoMatches:
            # Silently handle errors during refresh
            pass

    def get_agent_pane(self, agent_id: str) -> AgentStreamPane | None:
        """Get agent pane by ID.

        Args:
            agent_id: The agent/ticket ID.

        Returns:
            The AgentStreamPane or None if not found.
        """
        return self._agent_panes.get(agent_id)

    def get_reviewer_pane(self) -> ReviewerPane | None:
        """Get the reviewer pane.

        Returns:
            The ReviewerPane instance.
        """
        return self._reviewer_pane

    def _get_current_output(self) -> StreamingOutput | None:
        """Get the StreamingOutput of the currently active tab."""
        try:
            tabbed = self.query_one("#streams-tabs", TabbedContent)
            active_tab_id = tabbed.active
            if active_tab_id == REVIEWER_TAB_ID:
                if self._reviewer_pane:
                    return self._reviewer_pane.get_output()
            else:
                # Extract agent_id from tab id (format: "agent-{agent_id}")
                if active_tab_id and active_tab_id.startswith("agent-"):
                    agent_id = active_tab_id[6:]  # Remove "agent-" prefix
                    pane = self._agent_panes.get(agent_id)
                    if pane:
                        return pane.get_output()
        except NoMatches:
            pass
        return None

    def _get_current_scroll_container(self) -> ScrollableContainer | None:
        """Get the scrollable container of the currently active tab."""
        output = self._get_current_output()
        if output:
            try:
                return output.query_one("#streaming-container", ScrollableContainer)
            except NoMatches:
                pass
        return None

    # Actions

    def action_back(self) -> None:
        """Return to Kanban screen."""
        self.app.pop_screen()

    def _navigate_tab(self, direction: int) -> None:
        """Navigate tabs by direction (-1 for prev, +1 for next)."""
        try:
            tabbed = self.query_one("#streams-tabs", TabbedContent)
            tabs = list(tabbed.query("TabPane"))
            if not tabs:
                return
            current_idx = next((i for i, t in enumerate(tabs) if t.id == tabbed.active), 0)
            new_idx = (current_idx + direction) % len(tabs)
            if new_tab_id := tabs[new_idx].id:
                tabbed.active = new_tab_id
        except NoMatches:
            pass

    def action_prev_tab(self) -> None:
        """Switch to previous agent tab."""
        self._navigate_tab(-1)

    def action_next_tab(self) -> None:
        """Switch to next agent tab."""
        self._navigate_tab(+1)

    def action_scroll_down(self) -> None:
        """Scroll down in current output."""
        container = self._get_current_scroll_container()
        if container:
            container.scroll_down()

    def action_scroll_up(self) -> None:
        """Scroll up in current output."""
        container = self._get_current_scroll_container()
        if container:
            container.scroll_up()
