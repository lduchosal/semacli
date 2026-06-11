"""Pre-flight guards executed before launching a task."""

from .exceptions import OverrideNotAllowedError
from .models import Template


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
