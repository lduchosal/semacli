---
wiki:
  sections:
    - id: cli
      title: CLI layer
      description: Click entrypoint, shared decorators, error handlers, output formatting.
    - id: cli/commands
      title: CLI commands
      description: Individual click subcommands (ping, projects, templates, tasks, inventories).
    - id: core
      title: Core
      description: Configuration loading, Semaphore HTTP client, authentication, exceptions, and shared utilities.
    - id: core/models
      title: Core / models
      description: Data models shared across the codebase — Project, Template, Task, Inventory, Environment.
    - id: core/client
      title: Core / client
      description: HTTP client for the Semaphore REST API (/api/...).
    - id: services
      title: Services
      description: Business services that compose the core client into higher-level operations.
    - id: tests
      title: Tests
      description: Unit tests, integration tests, fixtures, and mock client.
    - id: packaging
      title: Packaging & tooling
      description: pyproject.toml, pdm, publish script, CI, linters, type checking.
    - id: docs
      title: Documentation
      description: README, ARCHITECTURE.md, and other user/developer-facing docs.
    - id: quality
      title: Code quality & CI
      description: Cross-cutting quality concerns — coverage, Sonarcloud, linters, CI workflows.
    - id: quality/test
      title: Quality / Tests
      description: Stratégie de tests, conventions pytest, fixtures partagées, coverage, regression cases.
    - id: quality/doc
      title: Quality / Documentation qualité
      description: Guides contributeur, conventions de tests, badges (coverage/interrogate), checklists de review.
---

# semacli architecture

This document is the source of truth for how kenboard's `ken wiki sync`
maps tasks to a structured wiki tree. The YAML frontmatter above declares
the section paths; the prose below describes what lives in each section
so an LLM agent (or human) can classify a task with `ken wiki groom <id> <section>`.

The section paths mirror the real package layout under `semacli/`:

```
semacli/
├── cli/                    # section: cli
│   ├── commands/           # section: cli/commands
│   ├── decorators.py
│   └── handlers.py
├── core/                   # section: core
│   ├── client.py           # section: core/client
│   ├── models.py           # section: core/models
│   ├── config.py
│   └── exceptions.py
└── services/               # section: services
```

Cross-cutting concerns map to:

- `tests` — anything under `tests/` (unit, integration, fixtures, mocks).
- `packaging` — `pyproject.toml`, `pdm.lock`, `publish.sh`, CI workflows.
- `docs` — `README.md`, this file.

When a task spans several files, classify it by the file where the
**root cause** lives, not the largest diff. For example, an enum value
bug fixed across `core/models.py`, `cli/handlers.py`, tests, and fixtures
belongs in `core/models` because that is where the canonical definition
lives — everything else is downstream of it.
