"""Pre-flight guards: refuse unsafe runs and unsafe template payloads.

Both guards exist because Semaphore fails *open*: a forbidden per-run
override is dropped without an error (ken #827), and ``arguments`` are
handed to ansible-playbook verbatim, with no templating pass (ken #636).
semacli refuses up front instead.
"""

import json
import re

from .exceptions import InvalidArgumentsError, OverrideNotAllowedError
from .models import Template

# `{{ limit }}` / `{% if %}` — Semaphore never expands these.
_JINJA = re.compile(r"{{.*?}}|{%.*?%}")


def ensure_overrides_allowed(
    template: Template,
    limit: str | None = None,
    tags: str | None = None,
    skip_tags: str | None = None,
    debug: int = 0,
) -> None:
    """Fail closed when a requested per-run override is forbidden.

    Semaphore does not error on a forbidden override — it silently
    drops the param, so a refused ``--limit`` runs the playbook on the
    full inventory (ken #827). Callers must check BEFORE posting the
    task; raises :class:`OverrideNotAllowedError` on the first
    forbidden flag.
    """
    p = template.task_params
    checks = [
        (
            "--limit",
            bool(limit),
            p.allow_override_limit,
            "allow_override_limit",
            "run on the FULL inventory",
        ),
        (
            "--tags",
            bool(tags),
            p.allow_override_tags,
            "allow_override_tags",
            "run ALL tasks of the playbook",
        ),
        (
            "--skip-tags",
            bool(skip_tags),
            p.allow_override_skip_tags,
            "allow_override_skip_tags",
            "run ALL tasks of the playbook",
        ),
        ("--debug", debug > 0, p.allow_debug, "allow_debug", "run without the requested verbosity"),
    ]
    name = template.name or f"id={template.id}"
    for flag, requested, allowed, toggle, consequence in checks:
        if requested and not allowed:
            raise OverrideNotAllowedError(name, flag, toggle, consequence)


def validate_template_arguments(arguments: str | None) -> None:
    """Refuse ``--arguments`` that Semaphore cannot honour.

    Accepts only a JSON array of static flags (``'["--diff"]'``). A
    Jinja placeholder is rejected: Semaphore stores the string as-is and
    ansible-playbook then reads ``{{ limit }}`` as a literal host
    pattern (ken #636) — per-run targeting belongs in ``task_params``,
    not in ``arguments``.
    """
    if not arguments:
        return
    if _JINJA.search(arguments):
        jinja = (
            "Jinja placeholders are never expanded and reach ansible literally "
            "(use --limit/--tags at run time, gated by task_params)"
        )
        raise InvalidArgumentsError(jinja, arguments)
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError as err:
        bad_json = f"not valid JSON ({err.msg})"
        raise InvalidArgumentsError(bad_json, arguments) from err
    if not isinstance(parsed, list):
        not_array = f"not a JSON array (got {type(parsed).__name__})"
        raise InvalidArgumentsError(not_array, arguments)
    if any(not isinstance(item, str) for item in parsed):
        not_strings = "every element must be a string"
        raise InvalidArgumentsError(not_strings, arguments)
