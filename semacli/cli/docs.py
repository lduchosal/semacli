"""``semacli docs`` — self-introspected CLI reference for LLM agents.

Methodology (cf ken #701):

* **Single source of truth = Click decorators.** Names, options, types,
  and required flags are read from the live Click tree, not maintained
  separately. Renaming a flag updates the doc automatically.
* **Examples live in ``_doc_examples.py``** — what introspection cannot
  capture (realistic calls, expected output, REST endpoint, response
  schema). One curated dict, one entry per documented command.
* **Pydantic models supply the return schema.** ``model: "Template"`` in
  the fixture resolves via ``semacli.core.models``; field names + types
  are dumped from ``model_fields``.
* **Sync-check test** verifies every fixture key matches a real Click
  command (see ``tests/unit/test_docs.py``).

The output is designed for an LLM agent: structured, predictable,
parsable with ``--json``, with concrete example invocations and
realistic response bodies.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import click

from semacli.core import models

from ._doc_examples import EXAMPLES


def _type_label(param: click.Parameter) -> str:
    """Human-readable type label for a Click parameter."""
    if getattr(param, "is_flag", False):
        return "flag"
    if getattr(param, "count", False):
        return "count"
    ptype = param.type
    if isinstance(ptype, click.Choice):
        return f"choice[{('|').join(ptype.choices)}]"
    name = getattr(ptype, "name", None) or type(ptype).__name__
    return {
        "integer": "int",
        "text": "str",
        "float": "float",
        "boolean": "bool",
    }.get(name, name)


def _param_decl(param: click.Parameter) -> str:
    """Human-readable invocation form (``--name`` / ``TEMPLATE_ID``)."""
    if isinstance(param, click.Argument):
        return param.name.upper() if param.name else "?"
    opts = getattr(param, "opts", None) or [param.name or "?"]
    return ", ".join(opts)


def _walk_commands(
    group: click.Group, path: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], click.Command]]:
    """Depth-first walk of the Click tree, yielding (path, command)."""
    for name, sub in sorted(group.commands.items()):
        sub_path = (*path, name)
        yield sub_path, sub
        if isinstance(sub, click.Group):
            yield from _walk_commands(sub, sub_path)


def _short_help(cmd: click.Command) -> str:
    return cmd.get_short_help_str(limit=80) or ""


def _root_group(ctx: click.Context) -> click.Group:
    """Climb the context chain to the root ``semacli`` group."""
    root = ctx
    while root.parent is not None:
        root = root.parent
    assert isinstance(root.command, click.Group)
    return root.command


def _command_at_path(root: click.Group, path: list[str]) -> click.Command | None:
    cmd: click.Command = root
    for segment in path:
        if not isinstance(cmd, click.Group):
            return None
        nxt = cmd.commands.get(segment)
        if nxt is None:
            return None
        cmd = nxt
    return cmd


def _safe_default(value: Any) -> Any:
    """Coerce a Click default into something json-serializable."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return repr(value)


def _describe_params(cmd: click.Command) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in cmd.params:
        if isinstance(p, click.Argument):
            kind = "argument"
        else:
            kind = "option"
        out.append(
            {
                "kind": kind,
                "decl": _param_decl(p),
                "type": _type_label(p),
                "required": bool(getattr(p, "required", False)),
                "default": _safe_default(getattr(p, "default", None)),
                "help": getattr(p, "help", None) or "",
            }
        )
    return out


def _resolve_schema(model_name: str | None) -> list[dict[str, str]] | None:
    """Return the field/type pairs of a pydantic model declared in the fixture."""
    if not model_name:
        return None
    model = getattr(models, model_name, None)
    if model is None:
        return None
    fields = getattr(model, "model_fields", None)
    if not fields:
        return None
    out = []
    for fname, finfo in fields.items():
        anno = finfo.annotation
        type_str = getattr(anno, "__name__", str(anno))
        out.append({"name": fname, "type": type_str})
    return out


def _describe_command(path: tuple[str, ...], cmd: click.Command) -> dict[str, Any]:
    path_str = " ".join(("semacli", *path))
    fixture_key = " ".join(path)
    example = EXAMPLES.get(fixture_key)
    doc: dict[str, Any] = {
        "path": path_str,
        "name": " ".join(path),
        "is_group": isinstance(cmd, click.Group),
        "short_help": _short_help(cmd),
        "help": (cmd.help or "").strip(),
        "params": _describe_params(cmd),
    }
    if example:
        doc["endpoint"] = example.get("endpoint")
        doc["returns"] = example.get("returns")
        doc["schema"] = _resolve_schema(example.get("model"))
        doc["example_call"] = example.get("example_call")
        doc["example_output_text"] = example.get("example_output_text")
        doc["example_output_json"] = example.get("example_output_json")
    return doc


def _render_text(doc: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"path:        {doc['path']}")
    if doc.get("short_help"):
        lines.append(f"description: {doc['short_help']}")
    if doc.get("endpoint"):
        lines.append(f"endpoint:    {doc['endpoint']}")
    if doc.get("returns"):
        lines.append(f"returns:     {doc['returns']}")

    args = [p for p in doc["params"] if p["kind"] == "argument"]
    opts = [p for p in doc["params"] if p["kind"] == "option"]
    if args:
        lines.append("")
        lines.append("Arguments:")
        for p in args:
            req = "required" if p["required"] else "optional"
            lines.append(f"  {p['decl']:<20} {p['type']:<14} {req:<8} {p['help']}")
    if opts:
        lines.append("")
        lines.append("Options:")
        for p in opts:
            req = "required" if p["required"] else "optional"
            default = "" if p["default"] in (None, False) else f"(default: {p['default']})"
            lines.append(
                f"  {p['decl']:<20} {p['type']:<14} {req:<8} {p['help']} {default}".rstrip()
            )

    if doc.get("schema"):
        lines.append("")
        lines.append("Response schema:")
        for f in doc["schema"]:
            lines.append(f"  {f['name']:<18} {f['type']}")

    if doc.get("example_call"):
        lines.append("")
        lines.append("Example:")
        lines.append(f"  $ {doc['example_call']}")
        if doc.get("example_output_text"):
            for raw_line in doc["example_output_text"].splitlines():
                lines.append(f"  {raw_line}")
        if doc.get("example_output_json"):
            lines.append("")
            lines.append(f"  $ {doc['example_call']} --json")
            for raw_line in doc["example_output_json"].splitlines():
                lines.append(f"  {raw_line}")
    return "\n".join(lines)


def register_docs_commands(main_group: click.Group) -> None:
    """Register the ``docs`` command group."""

    @main_group.group("docs", invoke_without_command=True)
    @click.pass_context
    def docs_group(ctx: click.Context) -> None:
        """Self-introspected CLI reference (designed for LLM agents).

        Run without arguments to list every command. Use ``docs show
        <path>`` for full details (params, types, endpoint, schema,
        example call, example output).
        """
        if ctx.invoked_subcommand is not None:
            return
        root = _root_group(ctx)
        items = []
        for path, cmd in _walk_commands(root):
            if path[0] == "docs":
                continue
            items.append(
                {
                    "path": " ".join(("semacli", *path)),
                    "is_group": isinstance(cmd, click.Group),
                    "short_help": _short_help(cmd),
                    "has_example": " ".join(path) in EXAMPLES,
                }
            )
        click.echo(json.dumps(items, indent=2)) if ctx.obj and ctx.obj.get(
            "output_json"
        ) else _emit_index_text(items)

    @docs_group.command("show")
    @click.argument("command_path", nargs=-1, required=True)
    @click.option("--json", "output_json", is_flag=True, help="Output as JSON")
    @click.pass_context
    def show_cmd(
        ctx: click.Context, command_path: tuple[str, ...], output_json: bool
    ) -> None:
        """Show full doc for a command path (e.g. ``docs show tasks raw-output``)."""
        root = _root_group(ctx)
        cmd = _command_at_path(root, list(command_path))
        if cmd is None:
            click.echo(f"Unknown command path: {' '.join(command_path)}", err=True)
            ctx.exit(5)
        assert cmd is not None
        doc = _describe_command(command_path, cmd)
        if output_json:
            click.echo(json.dumps(doc, indent=2))
        else:
            click.echo(_render_text(doc))

    @docs_group.command("list")
    @click.option("--json", "output_json", is_flag=True, help="Output as JSON")
    @click.pass_context
    def list_cmd(ctx: click.Context, output_json: bool) -> None:
        """List every command in the CLI tree."""
        root = _root_group(ctx)
        items = []
        for path, cmd in _walk_commands(root):
            if path[0] == "docs":
                continue
            items.append(
                {
                    "path": " ".join(("semacli", *path)),
                    "is_group": isinstance(cmd, click.Group),
                    "short_help": _short_help(cmd),
                    "has_example": " ".join(path) in EXAMPLES,
                }
            )
        if output_json:
            click.echo(json.dumps(items, indent=2))
        else:
            _emit_index_text(items)


def _emit_index_text(items: list[dict[str, Any]]) -> None:
    if not items:
        click.echo("No commands registered")
        return
    width = max(len(i["path"]) for i in items)
    for it in items:
        mark = "*" if it["has_example"] else " "
        kind = "[group]" if it["is_group"] else "       "
        click.echo(f"{mark} {it['path']:<{width}}  {kind}  {it['short_help']}")
    click.echo("\n* = curated example available (semacli docs show <path>)")
