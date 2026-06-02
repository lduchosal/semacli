"""Commands package for CLI."""

from typing import Any

from .ping import register_ping_commands
from .projects import register_projects_commands


def register_all_commands(main_group: Any) -> None:
    """Register all commands with the main CLI group."""
    register_ping_commands(main_group)
    register_projects_commands(main_group)
