"""CLI entry point for Kagan."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from kagan import __version__
from kagan.constants import DEFAULT_CONFIG_PATH, DEFAULT_DB_PATH, DEFAULT_LOCK_PATH


@click.group(invoke_without_command=True)
@click.option("--version", is_flag=True, help="Show version and exit")
@click.pass_context
def cli(ctx: click.Context, version: bool) -> None:
    """AI-powered Kanban TUI for autonomous development workflows."""
    if version:
        click.echo(f"kagan {__version__}")
        ctx.exit(0)

    # Run TUI by default if no subcommand
    if ctx.invoked_subcommand is None:
        ctx.invoke(tui)


@cli.command()
@click.option("--db", default=DEFAULT_DB_PATH, help="Path to SQLite database")
@click.option("--config", default=DEFAULT_CONFIG_PATH, help="Path to config file")
def tui(db: str, config: str) -> None:
    """Run the Kanban TUI (default command)."""
    config_path = Path(config)
    db_path = db

    # Derive db path from config path if only config is specified
    if db == DEFAULT_DB_PATH and config != DEFAULT_CONFIG_PATH:
        db_path = str(config_path.parent / "state.db")

    # Import here to avoid slow startup for --help/--version
    from kagan.lock import InstanceLock, InstanceLockError

    lock = InstanceLock(DEFAULT_LOCK_PATH)
    try:
        lock.acquire()
    except InstanceLockError:
        from kagan.ui.screens.locked import InstanceLockedApp

        app = InstanceLockedApp()
        app.run()
        sys.exit(1)

    try:
        from kagan.app import KaganApp

        app = KaganApp(db_path=db_path, config_path=config)
        app._instance_lock = lock
        app.run()
    finally:
        lock.release()


@cli.command()
def mcp() -> None:
    """Run the MCP server (STDIO transport).

    This command is typically invoked by AI agents (Claude Code, OpenCode, etc.)
    to communicate with Kagan via the Model Context Protocol.

    The MCP server finds the nearest .kagan/ directory by traversing up
    from the current working directory.
    """
    from kagan.mcp.server import main as mcp_main

    mcp_main()


if __name__ == "__main__":
    cli()
