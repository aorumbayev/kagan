"""Base screen class for Kagan screens."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.screen import Screen

if TYPE_CHECKING:
    from kagan.app import KaganApp
    from kagan.bootstrap import AppContext


class KaganScreen(Screen):
    """Base screen with typed app access."""

    @property
    def kagan_app(self) -> KaganApp:
        """Get the typed KaganApp instance."""
        return cast("KaganApp", self.app)

    @property
    def ctx(self) -> AppContext:
        """Get the application context for service access.

        Raises:
            RuntimeError: If AppContext is not initialized on the app.
        """
        app = self.kagan_app
        if not hasattr(app, "_ctx") or app._ctx is None:
            msg = "AppContext not initialized. Ensure bootstrap has completed."
            raise RuntimeError(msg)
        return app._ctx
