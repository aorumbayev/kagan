"""Unified ticket modal for viewing, editing, and creating tickets."""

from typing import cast

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Rule, Select, Static, TextArea

from kagan.constants import PRIORITY_LABELS
from kagan.database.models import (
    Ticket,
    TicketCreate,
    TicketPriority,
    TicketStatus,
    TicketUpdate,
)
from kagan.ui.modals.actions import ModalAction
from kagan.ui.modals.description_editor import DescriptionEditorModal


class TicketDetailsModal(ModalScreen[ModalAction | TicketCreate | TicketUpdate | None]):
    """Unified modal for viewing, editing, and creating tickets."""

    editing = reactive(False)

    BINDINGS = [
        Binding("escape", "close_or_cancel", "Close/Cancel"),
        Binding("e", "toggle_edit", "Edit", show=True),
        Binding("d", "delete", "Delete", show=True),
        Binding("f", "expand_description", "Expand", show=True),
        Binding("ctrl+s", "save", "Save", show=False),
    ]

    def __init__(
        self, ticket: Ticket | None = None, *, start_editing: bool = False, **kwargs
    ) -> None:
        """Initialize the modal.

        Args:
            ticket: The ticket to view/edit, or None to create a new ticket.
            start_editing: If True, start in edit mode (for existing tickets).
        """
        super().__init__(**kwargs)
        self.ticket = ticket
        self.is_create = ticket is None
        # Start in edit mode for new tickets or if explicitly requested
        self._initial_editing = self.is_create or start_editing

    def on_mount(self) -> None:
        """Set initial editing state after mount."""
        self.editing = self._initial_editing
        if self.editing:
            # Focus the title input in edit mode
            try:
                title_input = self.query_one("#title-input", Input)
                title_input.focus()
            except Exception:
                pass

    def _build_agent_options(self) -> list[tuple[str, str]]:
        """Build agent backend options from config."""
        options = [("Default", "")]
        kagan_app = getattr(self.app, "kagan_app", None) or self.app
        if hasattr(kagan_app, "config"):
            for name, agent in kagan_app.config.agents.items():
                if agent.active:
                    options.append((agent.name, name))
        return options

    def compose(self) -> ComposeResult:
        """Compose the modal layout."""
        with Vertical(id="ticket-details-container"):
            # Title changes based on mode
            yield Label(
                self._get_modal_title(),
                classes="modal-title",
                id="modal-title-label",
            )

            yield Rule(line_style="heavy")

            # Badge row / form fields row (conditional on editing)
            with Horizontal(classes="badge-row", id="badge-row"):
                yield Label(
                    self._get_priority_label(),
                    classes=f"badge {self._get_priority_class()}",
                    id="priority-badge",
                )
                yield Label(
                    self._format_status(
                        self.ticket.status if self.ticket else TicketStatus.BACKLOG
                    ),
                    classes="badge badge-status",
                    id="status-badge",
                )
                if self.ticket and self.ticket.agent_backend:
                    yield Label(
                        self.ticket.agent_backend,
                        classes="badge badge-agent",
                        id="agent-badge",
                    )

            # Edit mode fields (hidden initially for view mode)
            with Horizontal(classes="field-row edit-fields", id="edit-fields-row"):
                with Vertical(classes="form-field field-half"):
                    yield Label("Priority:", classes="form-label")
                    current_priority = (
                        self.ticket.priority if self.ticket else TicketPriority.MEDIUM
                    )
                    if isinstance(current_priority, int):
                        current_priority = TicketPriority(current_priority)
                    yield Select(
                        options=[
                            (label, p.value) for p, label in PRIORITY_LABELS.items()
                        ],
                        value=current_priority.value,
                        id="priority-select",
                    )

                with Vertical(classes="form-field field-half"):
                    yield Label("Agent:", classes="form-label")
                    agent_options = self._build_agent_options()
                    current_backend = self.ticket.agent_backend if self.ticket else ""
                    yield Select(
                        options=agent_options,
                        value=current_backend or "",
                        id="agent-backend-select",
                        allow_blank=True,
                    )

            # Status field for create mode only
            with Vertical(classes="form-field edit-fields", id="status-field"):
                yield Label("Status:", classes="form-label")
                yield Select(
                    options=[
                        ("Backlog", TicketStatus.BACKLOG.value),
                        ("In Progress", TicketStatus.IN_PROGRESS.value),
                        ("Review", TicketStatus.REVIEW.value),
                        ("Done", TicketStatus.DONE.value),
                    ],
                    value=TicketStatus.BACKLOG.value,
                    id="status-select",
                )

            yield Rule()

            # Title section - view mode shows static, edit mode shows input
            yield Label("Title", classes="section-title", id="title-section-label")
            yield Static(
                self.ticket.title if self.ticket else "",
                classes="ticket-title",
                id="title-display",
            )
            with Vertical(classes="form-field edit-fields", id="title-field"):
                yield Input(
                    value=self.ticket.title if self.ticket else "",
                    placeholder="Enter ticket title...",
                    id="title-input",
                )

            yield Rule()

            # Description section
            with Horizontal(classes="description-header"):
                yield Label("Description", classes="section-title")
                yield Static("", classes="header-spacer")
                yield Static(
                    "[f] Expand" if not self.editing else "[F5] Full Editor",
                    classes="expand-hint",
                    id="expand-btn",
                )

            # View mode: static description
            description = (
                self.ticket.description if self.ticket else ""
            ) or "(No description)"
            yield Static(
                description, classes="ticket-description", id="description-content"
            )

            # Edit mode: textarea
            with Vertical(classes="form-field edit-fields", id="description-field"):
                yield TextArea(
                    self.ticket.description if self.ticket else "",
                    id="description-input",
                    show_line_numbers=True,
                )

            yield Rule()

            # Metadata row (only in view mode for existing tickets)
            with Horizontal(classes="meta-row", id="meta-row"):
                if self.ticket:
                    yield Label(
                        f"Created: {self.ticket.created_at:%Y-%m-%d %H:%M}",
                        classes="ticket-meta",
                    )
                    yield Static("  |  ", classes="meta-separator")
                    yield Label(
                        f"Updated: {self.ticket.updated_at:%Y-%m-%d %H:%M}",
                        classes="ticket-meta",
                    )

            yield Rule()

            # Button row - changes based on mode
            with Horizontal(classes="button-row", id="view-buttons"):
                yield Button("[Esc] Close", id="close-btn")
                yield Button("[e] Edit", id="edit-btn")
                yield Button("[d] Delete", variant="error", id="delete-btn")

            with Horizontal(classes="button-row edit-fields", id="edit-buttons"):
                yield Button("[Ctrl+S] Save", variant="primary", id="save-btn")
                yield Button("[Esc] Cancel", id="cancel-btn")

    def _get_modal_title(self) -> str:
        """Get the modal title based on mode."""
        if self.is_create:
            return "New Ticket"
        elif self.editing:
            return "Edit Ticket"
        else:
            return "Ticket Details"

    def _get_priority_label(self) -> str:
        """Get priority label text."""
        if not self.ticket:
            return "MED"
        priority = self.ticket.priority
        if isinstance(priority, int):
            priority = TicketPriority(priority)
        return {
            TicketPriority.LOW: "LOW",
            TicketPriority.MEDIUM: "MED",
            TicketPriority.HIGH: "HIGH",
        }.get(priority, "MED")

    def _get_priority_class(self) -> str:
        """Get CSS class for priority badge."""
        if not self.ticket:
            return "badge-priority-medium"
        priority = self.ticket.priority
        if isinstance(priority, int):
            priority = TicketPriority(priority)
        return {
            TicketPriority.LOW: "badge-priority-low",
            TicketPriority.MEDIUM: "badge-priority-medium",
            TicketPriority.HIGH: "badge-priority-high",
        }.get(priority, "badge-priority-medium")

    def _format_status(self, status: TicketStatus | str) -> str:
        if isinstance(status, str):
            status = TicketStatus(status)
        return status.value.replace("_", " ")

    def watch_editing(self, editing: bool) -> None:
        """React to editing mode changes."""
        # Update modal title
        try:
            title_label = self.query_one("#modal-title-label", Label)
            title_label.update(self._get_modal_title())
        except Exception:
            pass

        # Update expand hint text
        try:
            expand_btn = self.query_one("#expand-btn", Static)
            expand_btn.update("[F5] Full Editor" if editing else "[f] Expand")
        except Exception:
            pass

        # Toggle visibility of view vs edit elements
        self._update_visibility()

        # Focus title input when entering edit mode
        if editing:
            try:
                title_input = self.query_one("#title-input", Input)
                title_input.focus()
            except Exception:
                pass

    def _update_visibility(self) -> None:
        """Update visibility of elements based on editing mode."""
        editing = self.editing

        # Show/hide badge row (view mode only)
        try:
            badge_row = self.query_one("#badge-row")
            badge_row.display = not editing
        except Exception:
            pass

        # Show/hide edit fields row
        try:
            edit_fields = self.query_one("#edit-fields-row")
            edit_fields.display = editing
        except Exception:
            pass

        # Show/hide status field (create mode only in edit)
        try:
            status_field = self.query_one("#status-field")
            status_field.display = editing and self.is_create
        except Exception:
            pass

        # Show/hide title display vs input
        try:
            title_display = self.query_one("#title-display")
            title_display.display = not editing
        except Exception:
            pass
        try:
            title_field = self.query_one("#title-field")
            title_field.display = editing
        except Exception:
            pass

        # Hide title section label in edit mode (input has no separate label)
        try:
            title_section = self.query_one("#title-section-label")
            title_section.display = not editing
        except Exception:
            pass

        # Show/hide description display vs textarea
        try:
            desc_content = self.query_one("#description-content")
            desc_content.display = not editing
        except Exception:
            pass
        try:
            desc_field = self.query_one("#description-field")
            desc_field.display = editing
        except Exception:
            pass

        # Show/hide metadata row (only for view mode of existing tickets)
        try:
            meta_row = self.query_one("#meta-row")
            meta_row.display = not editing and self.ticket is not None
        except Exception:
            pass

        # Show/hide button rows
        try:
            view_buttons = self.query_one("#view-buttons")
            view_buttons.display = not editing
        except Exception:
            pass
        try:
            edit_buttons = self.query_one("#edit-buttons")
            edit_buttons.display = editing
        except Exception:
            pass

    # Button handlers
    @on(Button.Pressed, "#edit-btn")
    def on_edit_btn(self) -> None:
        self.action_toggle_edit()

    @on(Button.Pressed, "#delete-btn")
    def on_delete_btn(self) -> None:
        self.action_delete()

    @on(Button.Pressed, "#close-btn")
    def on_close_btn(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#save-btn")
    def on_save_btn(self) -> None:
        self.action_save()

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel_btn(self) -> None:
        self.action_close_or_cancel()

    # Actions
    def action_toggle_edit(self) -> None:
        """Toggle between view and edit mode."""
        if not self.editing and not self.is_create:
            self.editing = True

    def action_delete(self) -> None:
        """Delete the ticket."""
        if not self.editing and self.ticket:
            self.dismiss(ModalAction.DELETE)

    def action_close_or_cancel(self) -> None:
        """Close modal or cancel editing."""
        if self.editing:
            if self.is_create:
                # For new tickets, cancel means close
                self.dismiss(None)
            else:
                # For existing tickets, cancel returns to view mode
                self.editing = False
                # Reset form fields to original values
                self._reset_form_fields()
        else:
            self.dismiss(None)

    def _reset_form_fields(self) -> None:
        """Reset form fields to original ticket values."""
        if not self.ticket:
            return
        try:
            self.query_one("#title-input", Input).value = self.ticket.title
            self.query_one("#description-input", TextArea).text = (
                self.ticket.description or ""
            )
            priority = self.ticket.priority
            if isinstance(priority, int):
                priority = TicketPriority(priority)
            self.query_one("#priority-select", Select).value = priority.value
            self.query_one("#agent-backend-select", Select).value = (
                self.ticket.agent_backend or ""
            )
        except Exception:
            pass

    def action_save(self) -> None:
        """Save the ticket (submit form)."""
        if not self.editing:
            return

        title_input = self.query_one("#title-input", Input)
        description_input = self.query_one("#description-input", TextArea)
        priority_select: Select[int] = self.query_one("#priority-select", Select)

        title = title_input.value.strip()
        if not title:
            self.notify("Title is required", severity="error")
            title_input.focus()
            return

        description = description_input.text

        # Validate priority selection
        priority_value = priority_select.value
        if priority_value is Select.BLANK:
            self.notify("Priority is required", severity="error")
            priority_select.focus()
            return
        priority = TicketPriority(cast("int", priority_value))

        # Get agent backend selection
        agent_backend_select: Select[str] = self.query_one(
            "#agent-backend-select", Select
        )
        agent_backend_value = agent_backend_select.value
        agent_backend = (
            str(agent_backend_value) if agent_backend_value is not Select.BLANK else ""
        )

        if self.is_create:
            status_select: Select[str] = self.query_one("#status-select", Select)
            status_value = status_select.value
            if status_value is Select.BLANK:
                self.notify("Status is required", severity="error")
                status_select.focus()
                return
            status = TicketStatus(cast("str", status_value))
            result = TicketCreate(
                title=title,
                description=description,
                priority=priority,
                status=status,
                agent_backend=agent_backend or None,
            )
        else:
            result = TicketUpdate(
                title=title,
                description=description,
                priority=priority,
                agent_backend=agent_backend or None,
            )

        self.dismiss(result)

    def action_expand_description(self) -> None:
        """Open the description in a full-screen editor."""
        if self.editing:
            # Edit mode: open editable full editor
            description_input = self.query_one("#description-input", TextArea)
            current_text = description_input.text

            def handle_result(result: str | None) -> None:
                if result is not None:
                    description_input.text = result

            self.app.push_screen(
                DescriptionEditorModal(
                    description=current_text,
                    readonly=False,
                    title="Edit Description",
                ),
                handle_result,
            )
        else:
            # View mode: open read-only viewer
            description = self.ticket.description if self.ticket else ""
            self.app.push_screen(
                DescriptionEditorModal(
                    description=description,
                    readonly=True,
                    title="View Description",
                )
            )
