"""Modal components for Kagan TUI."""

from kagan.ui.modals.actions import ModalAction
from kagan.ui.modals.agent_output import AgentOutputModal
from kagan.ui.modals.base import BaseActionModal
from kagan.ui.modals.confirm import ConfirmModal
from kagan.ui.modals.debug_log import DebugLogModal
from kagan.ui.modals.description_editor import DescriptionEditorModal
from kagan.ui.modals.diff import DiffModal
from kagan.ui.modals.duplicate_task import DuplicateTaskModal
from kagan.ui.modals.folder_picker import FolderPickerModal
from kagan.ui.modals.help import HelpModal
from kagan.ui.modals.merge_dialog import MergeDialog
from kagan.ui.modals.new_project import NewProjectModal
from kagan.ui.modals.rejection_input import RejectionInputModal
from kagan.ui.modals.review import ReviewModal
from kagan.ui.modals.settings import SettingsModal
from kagan.ui.modals.start_workspace import StartWorkspaceModal
from kagan.ui.modals.task_details_modal import TaskDetailsModal
from kagan.ui.modals.tmux_gateway import TmuxGatewayModal

__all__ = [
    "AgentOutputModal",
    "BaseActionModal",
    "ConfirmModal",
    "DebugLogModal",
    "DescriptionEditorModal",
    "DiffModal",
    "DuplicateTaskModal",
    "FolderPickerModal",
    "HelpModal",
    "MergeDialog",
    "ModalAction",
    "NewProjectModal",
    "RejectionInputModal",
    "ReviewModal",
    "SettingsModal",
    "StartWorkspaceModal",
    "TaskDetailsModal",
    "TmuxGatewayModal",
]
