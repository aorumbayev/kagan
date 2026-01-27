"""Chat screen for planner agent interaction."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual import on
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Input, Label, Static

from kagan.acp import messages
from kagan.agents.planner import build_planner_prompt, parse_ticket_from_response
from kagan.agents.roles import AgentRole
from kagan.config import get_fallback_agent_config
from kagan.ui.screens.base import KaganScreen
from kagan.ui.widgets import StreamingOutput
from kagan.ui.widgets.header import KAGAN_LOGO

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from kagan.acp.agent import Agent

PLANNER_SESSION_ID = "planner"


class ChatScreen(KaganScreen):
    """Chat screen for planner agent interaction."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("ctrl+c", "interrupt", "Interrupt", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._agent: Agent | None = None
        self._is_running = False
        self._accumulated_response: list[str] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="chat-header"):
            yield Label(KAGAN_LOGO, classes="header-logo")
            yield Label("KAGAN", classes="header-title")
            yield Label("Planner Chat", classes="header-subtitle")
        with Vertical(id="chat-container"):
            yield Static("Status: Not started", id="chat-status")
            yield StreamingOutput(show_status_log=True, id="chat-output")
            with Horizontal(id="chat-input-row"):
                yield Input(placeholder="Describe your goal...", id="chat-input")
        yield Footer()

    async def on_mount(self) -> None:
        await self._start_planner()
        self.query_one("#chat-input", Input).focus()

    async def _start_planner(self) -> None:
        """Start the planner agent."""
        manager = self.kagan_app.agent_manager

        # Check if already running
        existing = manager.get(PLANNER_SESSION_ID)
        if existing:
            self._agent = existing
            self._is_running = True
            # Subscribe for streaming updates
            manager.subscribe(PLANNER_SESSION_ID, self)
            self._update_status()
            return

        # Get agent config from config (uses user's selection from welcome screen)
        config = self.kagan_app.config
        agent_config = config.get_worker_agent()

        if agent_config is None:
            agent_config = get_fallback_agent_config()

        # Spawn in current directory (no worktree for planner)
        cwd = Path.cwd()

        try:
            # Pass self as message_target to receive streaming updates
            self._agent = await manager.spawn(
                PLANNER_SESSION_ID,
                agent_config,
                cwd,
                self,
                role=AgentRole.PLANNER,
            )
            self._is_running = True
            self._update_status()
        except ValueError:
            # Agent already running
            self._agent = manager.get(PLANNER_SESSION_ID)
            if self._agent:
                self._is_running = True
                manager.subscribe(PLANNER_SESSION_ID, self)
                self._update_status()

    def _update_status(self) -> None:
        """Update status display."""
        status = self.query_one("#chat-status", Static)
        if not self._agent:
            status.update("Status: Not started")
            return
        if self._is_running:
            status.update("Status: [bold green]RUNNING[/]")
        else:
            status.update("Status: [bold blue]STOPPED[/]")

    def _get_output(self) -> StreamingOutput:
        """Get the streaming output widget."""
        return self.query_one("#chat-output", StreamingOutput)

    # Message handlers for ACP agent events

    @on(messages.AgentUpdate)
    async def on_agent_update(self, message: messages.AgentUpdate) -> None:
        """Handle agent text output."""
        self._accumulated_response.append(message.text)
        await self._get_output().write(message.text)

    @on(messages.Thinking)
    async def on_agent_thinking(self, message: messages.Thinking) -> None:
        """Handle agent thinking/reasoning."""
        # Thinking can be chunked, so use main stream with italic formatting
        await self._get_output().write(f"*{message.text}*")

    @on(messages.ToolCall)
    def on_tool_call(self, message: messages.ToolCall) -> None:
        """Handle tool call start."""
        output = self._get_output()
        title = message.tool_call.get("title", "Tool call")
        kind = message.tool_call.get("kind", "")
        output.write_status(f"\n[bold cyan]> {title}[/bold cyan]")
        if kind:
            output.write_status(f"  [dim]({kind})[/dim]")

    @on(messages.ToolCallUpdate)
    def on_tool_call_update(self, message: messages.ToolCallUpdate) -> None:
        """Handle tool call update."""
        status = message.update.get("status")
        if status:
            style = "green" if status == "completed" else "yellow"
            self._get_output().write_status(f"  [{style}]{status}[/{style}]")

    @on(messages.AgentReady)
    def on_agent_ready(self, message: messages.AgentReady) -> None:
        """Handle agent ready."""
        self._get_output().write_status("[green]Agent ready[/green]\n")

    @on(messages.AgentFail)
    def on_agent_fail(self, message: messages.AgentFail) -> None:
        """Handle agent failure."""
        self._is_running = False
        self._update_status()
        output = self._get_output()
        output.write_status(f"[red bold]Error: {message.message}[/red bold]")
        if message.details:
            output.write_status(f"[red]{message.details}[/red]")

    async def _try_create_ticket_from_response(self) -> None:
        """Parse accumulated response and create ticket if found."""
        if not self._accumulated_response:
            return

        full_response = "".join(self._accumulated_response)
        parsed = parse_ticket_from_response(full_response)

        if parsed is None:
            return

        try:
            ticket = await self.kagan_app.state_manager.create_ticket(parsed.ticket)
            self.notify(
                f"Created ticket [{ticket.short_id}]: {ticket.title[:50]}",
                severity="information",
            )
            self._get_output().write_status(
                f"\n[bold green]✓ Created ticket {ticket.short_id}[/bold green]\n"
            )
        except Exception as e:
            self.notify(f"Failed to create ticket: {e}", severity="error")
            self._get_output().write_status(f"[red]Failed to create ticket: {e}[/red]")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user input submission."""
        text = event.value.strip()
        if not text:
            return

        event.input.value = ""

        # Write user input to streaming output
        await self._get_output().write(f"\n\n**You:** {text}\n\n")

        if self._agent and self._is_running:
            # Use send_prompt for ACP agents
            self.run_worker(self._send_prompt(text))
        else:
            self.notify("Planner not running", severity="warning")

    async def _send_prompt(self, text: str) -> None:
        """Send prompt to agent asynchronously."""
        if self._agent:
            # Clear accumulated response before sending new prompt
            self._accumulated_response.clear()

            # Build planner prompt with system instructions
            prompt = build_planner_prompt(text)

            try:
                await self._agent.send_prompt(prompt)
                # After prompt completes, try to create ticket from response
                await self._try_create_ticket_from_response()
            except Exception as e:
                self._get_output().write_status(f"[red]Error sending prompt: {e}[/red]")

    async def action_interrupt(self) -> None:
        """Send cancel signal to planner."""
        if self._agent and self._is_running:
            await self._agent.cancel()
            self.notify("Sent cancel request")

    def action_back(self) -> None:
        """Return to Kanban screen."""
        self.app.pop_screen()

    async def on_unmount(self) -> None:
        """Cleanup on screen exit - do not terminate the planner."""
        # Clear ourselves as subscriber but keep the agent running for reuse
        if self._agent:
            self.kagan_app.agent_manager.unsubscribe(PLANNER_SESSION_ID, self)
