"""Custom click Group classes used across the CLI.

See UX.md for the rules these classes implement: hidden plural aliases,
sectioned listing on the root, 80-column help, no colors.
"""

from typing import Any, ClassVar

import click


class RawEpilogCommand(click.Command):
    """``click.Command`` that preserves line breaks in ``epilog``.

    Click's default ``format_epilog`` reflows the epilog to fit the
    formatter width, which destroys hand-formatted examples and
    hierarchy diagrams.
    """

    def format_epilog(self, _ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """Write the epilog verbatim instead of reflowing it."""
        _write_raw_epilog(self.epilog, formatter)


class AliasedGroup(click.Group):
    """Click Group that resolves hidden aliases via ``get_command``.

    Aliases are not listed by ``list_commands`` so they stay invisible in
    ``--help`` while remaining fully functional. Used to keep the old
    plural names (``environments``, ``inventories``, …) working after the
    rename to singular forms.

    Also preserves ``epilog`` formatting like ``RawEpilogCommand``.
    """

    command_class = RawEpilogCommand
    # group_class is set after the class body below so it can reference itself.

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401 — click passthrough
        self._aliases: dict[str, str] = {}
        super().__init__(*args, **kwargs)

    def add_alias(self, alias: str, canonical: str) -> None:
        """Register a hidden alias pointing at a canonical command name."""
        self._aliases[alias] = canonical

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        """Resolve hidden aliases before the normal lookup."""
        canonical = self._aliases.get(cmd_name, cmd_name)
        return super().get_command(ctx, canonical)

    def list_commands(self, ctx: click.Context) -> list[str]:
        """List commands with the hidden aliases filtered out."""
        return [name for name in super().list_commands(ctx) if name not in self._aliases]

    def format_epilog(self, _ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """Write the epilog verbatim instead of reflowing it."""
        _write_raw_epilog(self.epilog, formatter)


AliasedGroup.group_class = AliasedGroup


def _write_raw_epilog(epilog: str | None, formatter: click.HelpFormatter) -> None:
    """Write an epilog while preserving its line breaks (click's default
    implementation reflows everything to the formatter width).
    """
    if not epilog:
        return
    formatter.write_paragraph()
    for line in epilog.splitlines():
        formatter.write(line)
        formatter.write("\n")


class SectionedRootGroup(AliasedGroup):
    """Root group that lists subcommands grouped by category.

    Commands declare their section via the ``category`` attribute
    (``connection`` / ``read`` / ``execution``). Commands without one are
    listed under ``Other``.
    """

    SECTIONS: ClassVar[list[tuple[str, str]]] = [
        ("connection", "Connection"),
        ("read", "Read / write"),
        ("execution", "Execution"),
    ]

    def set_category(self, name: str, category: str) -> None:
        """Tag a registered command for the sectioned root help listing.

        The tag is a dynamic attribute read back by ``format_commands``
        via ``getattr`` — ``click.Command`` does not declare it.
        """
        self.commands[name].category = category  # type: ignore[attr-defined]

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """Render the command list bucketed by ``category``, with an ``Other`` catch-all."""
        buckets: dict[str, list[tuple[str, str]]] = {key: [] for key, _ in self.SECTIONS}
        other: list[tuple[str, str]] = []

        for name in self.list_commands(ctx):
            cmd = self.get_command(ctx, name)
            if cmd is None or cmd.hidden:
                continue
            short = cmd.get_short_help_str(limit=60)
            category = getattr(cmd, "category", None)
            if category in buckets:
                buckets[category].append((name, short))
            else:
                other.append((name, short))

        for key, title in self.SECTIONS:
            rows = buckets[key]
            if rows:
                with formatter.section(title):
                    formatter.write_dl(rows)
        if other:
            with formatter.section("Other"):
                formatter.write_dl(other)


class ResourceGroup(AliasedGroup):
    """Resource group (env / inv / repo / key / sched / template / task).

    Behavior:
    - ``invoke_without_command=True`` is forced — bare invocation lists.
    - ``get_command`` returns ``None`` for arguments that look like a
      filter query (any token that isn't a registered subcommand). The
      root callback then dispatches to the default list handler with the
      query, implementing the positional-filter rule from UX.md § 3.1 B.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401 — click passthrough
        kwargs.setdefault("invoke_without_command", True)
        super().__init__(*args, **kwargs)
