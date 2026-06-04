"""CLI module for semacli."""

import click

from semacli import __version__

from ._groups import SectionedRootGroup
from .commands import register_all_commands

ROOT_EPILOG = """\
SEMAPHORE HIERARCHY
  project
    +-- inv        ansible hosts (inventories)
    +-- repo       git sources of playbooks
    +-- env        variables and secrets passed at runtime
    +-- key        SSH / vault / login credentials
    +-- template   recipe = repo + inv + env + playbook
    |     +-- task   executions of a template
    +-- sched      cron triggers -> template

FIRST TIME?
  sem init           Interactive assistant (URL, token, project).
  sem ping           Check that the server responds.

EXAMPLES
  sem init
  sem project
  sem run mtree --limit ans2.0.2113.ch
  sem env create --name prod --vars @vars.json
  sem sched create --template mtree --cron '0 3 * * *'

Config: ./semacli.ini, ~/.semacli.ini, /usr/local/etc/semacli.ini
"""


@click.group(cls=SectionedRootGroup, invoke_without_command=True, epilog=ROOT_EPILOG)
@click.version_option(version=__version__, prog_name="sem")
@click.pass_context
def main(ctx: click.Context) -> None:
    """Manage your ansible codebase through Semaphore UI."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


register_all_commands(main)
