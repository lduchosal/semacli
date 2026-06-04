"""Commands package for CLI."""

from typing import Any

from .environments import register_environments_commands
from .info import register_info_commands
from .init import register_init_commands
from .inventories import register_inventories_commands
from .keys import register_keys_commands
from .ping import register_ping_commands
from .projects import register_projects_commands
from .repositories import register_repositories_commands
from .run import register_run_commands
from .schedules import register_schedules_commands
from .tasks import register_tasks_commands
from .templates import register_templates_commands
from .user import register_user_commands


def register_all_commands(main_group: Any) -> None:
    """Register all commands with the main CLI group."""
    register_ping_commands(main_group)
    register_info_commands(main_group)
    register_init_commands(main_group)
    register_user_commands(main_group)
    register_projects_commands(main_group)
    register_templates_commands(main_group)
    register_tasks_commands(main_group)
    register_inventories_commands(main_group)
    register_environments_commands(main_group)
    register_repositories_commands(main_group)
    register_keys_commands(main_group)
    register_schedules_commands(main_group)
    register_run_commands(main_group)
