# UX Standard — semacli

Canonical reference for semacli's user-facing surface (`--help` pages,
prompts, output). All implementation must follow these rules. When a
rule is challenged or refined, update this file in the same change
that updates the code.

Underlying discussions live on the kenboard board — see the **Index**
section at the bottom for the full list of UX tickets.

---

## 1. Foundational rules

### 1.1 Language
English only. All help text, prompts, error messages, output messages,
example values. The root command tagline is also English; the French
variant briefly used in early drafts was dropped (see #720).

### 1.2 Formatting
- No ANSI escape codes (no colors, no bold, no underline).
- No emoji.
- ASCII for prose. Unicode box-drawing characters (`├`, `└`, `─`) are
  acceptable in hierarchy diagrams since they degrade gracefully in
  modern terminals.
- Output must remain useful when piped or redirected (no terminal
  detection, no width-dependent layout beyond click's defaults).

### 1.3 Naming — short and singular
First-level group names use the **short, singular** form:

| Long form     | Standard short |
|---------------|----------------|
| environments  | `env`          |
| inventories   | `inv`          |
| repositories  | `repo`         |
| schedules     | `sched`        |
| keys          | `key`          |
| templates     | `template`     |
| tasks         | `task`         |
| projects      | `project`      |

Long forms (plural) remain as **hidden aliases** for back-compat: they
keep accepting all subcommands and flags but are not listed in `--help`.

### 1.4 `sem` ≡ `sem --help`
Invoking the binary with no argument prints the same help screen as
`--help`. Implementation: `invoke_without_command=True` on the root
group plus an explicit call to `ctx.get_help()` in the root callback
when no subcommand is selected.

---

## 2. Help page structure

Every command's help page follows the same sections, in order:

1. **Usage** — click default.
2. **Concept** — 2-4 lines answering *what is this thing?*, not *what
   verbs are available?*. Tie it to Semaphore UI vocabulary and to
   the ansible workflow.
3. **Options** — click default, with shared common options
   (`-c`, `-v`, `-q`, `--json`, `-p`) injected via decorators.
4. **Commands** (groups only) — short concept-oriented descriptions,
   never `List, show, create, update, delete X.`.
5. **Examples** — concrete invocations. Always present, never elided.

### 2.1 Concept one-liners (root page)

| Command     | Concept (≤ 60 chars)                              |
|-------------|---------------------------------------------------|
| `project`   | Projects visible to your token.                   |
| `inv`       | Inventories: ansible hosts.                       |
| `env`       | Environments: runtime vars + secrets.             |
| `repo`      | Repositories: git sources of playbooks.           |
| `key`       | Keys: SSH, vault password, login/password.        |
| `template`  | Templates: job recipes (what you run).            |
| `sched`     | Schedules: cron triggers.                         |
| `task`      | Tasks: executions of a template.                  |
| `ping`      | Server reachability test (no auth).               |
| `init`      | Create semacli.ini in guided mode.                |
| `run`       | Shortcut: run a template by name (§ 3).           |

### 2.2 Examples — realistic values

Always use realistic values rooted in the 2113.ch infrastructure:

- Hostnames: `web1.0.2113.ch`, `ans2.0.2113.ch`, `monitor1.0.2113.ch`
- Template names: `mtree`, `nightly-backup`, `deploy-prod`
- Environment names: `prod`, `staging`
- Inventory names: `prod-hosts`
- Repo names: `infra`
- Key names: `deploy-ssh`, `vault-pw`
- Cron: `0 3 * * *` (nightly 3 am), `*/15 * * * *` (every 15 min)
- File references: `@vars.json`, `@hosts.ini`, `@~/.ssh/id_ed25519`

Never use `<placeholder>`, `<value>`, `<name>`, `<id>`.

Every example block should include at least one of each:

- the simplest possible call,
- the most common real-world call (with project-specific values),
- a scripting form (`--json | jq`, or capture into a shell variable).

---

## 3. Name-first addressing

The CLI must accept **names everywhere it accepts IDs**.

### 3.1 Three forms

**A. Top-level `sem run <template-name>`** — runs a template by
name without going through `tasks run`:

```
sem run mtree --limit ans2.0.2113.ch
sem run mtree --dry-run --debug
sem run mtree --watch
```

**B. Positional filter on group commands.** Bare invocation with one
extra word filters the listing:

```
sem templates             # all templates of default project
sem templates mtree       # only those whose name contains 'mtree'
sem inv prod              # inventories containing 'prod'
```

**C. Name accepted wherever an ID is accepted.**

```
sem templates show mtree
sem env update prod --json @vars.json
sem inv delete prod-hosts
```

### 3.2 Resolution rules

1. **Pure integer** argument → treated as id, no lookup.
2. **String** argument → name lookup:
   - case-insensitive substring match,
   - scoped to the project from `-p` or `semacli.ini`.
3. Outcomes:
   - **0 matches** → `error: no <type> matching '<query>'`, exit 2.
   - **N matches with one exact hit** → use the exact match
     (`mtree` wins over `mtree-dev` when query is exactly `mtree`).
   - **N matches, none exact** → list candidates with their ids and
     exit 2 with a hint pointing at `--exact`.
   - **1 match** → use it.
4. `--exact NAME` bypasses the substring matcher and requires
   `name == NAME`.

### 3.3 Where this applies

| Object type   | Name-based addressing | Positional filter   |
|---------------|-----------------------|---------------------|
| `template`    | yes                   | yes                 |
| `inv`         | yes                   | yes                 |
| `env`         | yes                   | yes                 |
| `repo`        | yes                   | yes                 |
| `key`         | yes                   | yes                 |
| `sched`       | by template name      | yes                 |
| `project`     | by project name       | yes                 |
| `task`        | no (no human name)    | filter by status / template |

---

## 4. Group commands

### 4.1 Bare invocation = list
Invoking a group with no subcommand lists its items (filtered by the
positional query, if present). No explicit `list` subcommand is
exposed; if one exists, it is a hidden alias for the bare form.

### 4.2 Standard CRUD verbs
Resource groups expose the same vocabulary:

- `show <id-or-name>` — full details of one item.
- `create [...]` — required flags depend on the object type.
- `update <id-or-name> [...]` — patch mutable fields.
- `delete <id-or-name>` — fails if referenced elsewhere.

`task` keeps verb-noun ordering but uses task-specific verbs
(`run`, `watch`, `show`, `output`, `raw-output`, `stop`, `list`).

### 4.3 Shared options
Available on every group, via `@common_options` + `@output_options`:

- `-c, --config TEXT` — path to semacli.ini.
- `-v, --verbose` — increase verbosity, repeatable.
- `-q, --quiet` — minimal output.
- `--json` — output as JSON.
- `-p, --project INTEGER` — project id (or name, per § 3) override.
- `--help` — click default.

---

## 5. Errors and exit codes

| Code | Meaning                                                   |
|------|-----------------------------------------------------------|
| 0    | Success.                                                  |
| 1    | Command-level failure (HTTP 5xx, network, decoding).      |
| 2    | User error (missing config, unknown object, ambiguous name, bad flag combination). |
| 3    | Auth failure (401/403). Sentinel for scripts that want to trigger a re-init. |
| 130  | Interrupted by SIGINT.                                    |

Error messages are single-line, plain English, lowercase first letter:

```
error: no template matching 'mtre' (did you mean: mtree?)
error: ambiguous 'mtree' — 4 candidates; use --exact or a longer name
```

---

## 6. Root screen

Reference layout (frozen in #720). Implementations may polish wording
but must preserve sections, order, and concept-first descriptions.
Target width: **80 columns strict**.

```
sem 0.1.5 — Manage your ansible codebase through Semaphore UI.

USAGE
  sem <command> [subcommand] [options]

FIRST TIME?
  sem init           Interactive assistant (URL, token, project).
  sem ping           Check that the server responds.

SEMAPHORE HIERARCHY
  project
    ├── inv        ansible hosts (inventories)
    ├── repo       git sources of playbooks
    ├── env        variables and secrets passed at runtime
    ├── key        SSH / vault / login credentials
    ├── template   recipe = repo + inv + env + playbook
    │     └── task   executions of a template
    └── sched      cron triggers → template

COMMANDS
  Connection
    ping                 Server reachability test (no auth).
    init                 Create semacli.ini in guided mode.

  Read / write
    project              Projects visible to your token.
    inv                  Inventories: ansible hosts.
    env                  Environments: runtime vars + secrets.
    repo                 Repositories: git sources of playbooks.
    key                  Keys: SSH, vault password, login/password.
    template             Templates: job recipes (what you run).
    sched                Schedules: cron triggers.

  Execution
    run <name>           Shortcut: run a template by name.
    task                 Manage running and historical tasks.

EXAMPLES
  sem init
  sem project
  sem run mtree --limit ans2.0.2113.ch
  sem env create --name prod --vars @vars.json
  sem sched create --template mtree --cron '0 3 * * *'

HELP
  sem <cmd> --help   Per-command details + examples.

Config: ./semacli.ini, ~/.semacli.ini, /usr/local/etc/semacli.ini
```

---

## 7. Implementation handles

When wiring these rules into click:

- **Sectioned command listing** on the root (Connection / Read-write /
  Execution): override `Group.format_commands()` to consult a
  `category=` kwarg added on each `@command()` / `@group()`.
- **Hidden long aliases**: `Group.get_command()` maps
  `environments` → `env`, etc.; `list_commands()` returns only the
  short forms.
- **Bare-invocation list**: `invoke_without_command=True` + dispatch
  to an internal `_default_list` when no subcommand.
- **Name resolution**: per-resource helper in
  `semacli/core/client.py` — `client.resolve_<type>(query,
  exact=False)` returns an id or raises a structured exception.
- **Examples block**: `epilog=` on each command/group.
- **Exit codes**: a small helper in `semacli/cli/handlers.py` that
  maps exception classes to the codes in § 5.

---

## 8. Decision log

All UX questions have been arbitrated and folded into the rules above.
This log records the answers for traceability.

| Question                                                | Decision                                                       |
|---------------------------------------------------------|----------------------------------------------------------------|
| Extend singular to `key`/`template`/`task`/`project`?   | **Yes** — applied (§ 1.3).                                     |
| Terminal width target.                                  | **80 columns strict**.                                         |
| Version line duplicated in header?                      | **Yes** — kept (§ 6) for support traceability.                 |
| `--watch` default on `sem run`.                     | **On by default**; opt-out with `--no-watch`.                  |
| Extend top-level shortcut to `watch` / `stop`?          | **No** — only `run` (because templates have names, tasks have only ids). |
| Exact match wins over fuzzy on collision.               | **Yes** (§ 3.2 rule 3b).                                       |
| `env update --vars` patch vs replace.                   | **Replace wholesale** — same semantics as PUT on the REST API. |
| Rename `env --json` payload to `--vars`.                | **Yes** — `--json` only ever means "output as JSON".           |
| `--ssh-key` flag overloading.                           | `repo create --key NAME-OR-ID` (reference an existing key); `key create --type ssh --private-key @file` (the actual key body). |
| Keep `sem docs` command?                            | **No** — removed (commit `a02624b`).                           |
| `template` CRUD (create / update / delete)?             | **No** — `template` exposes only `list` (bare) and `show`.     |

---

## 9. Index — UX tickets

| Topic                                | Ticket |
|--------------------------------------|--------|
| Onboarding flow (`sem init`)     | #716   |
| Short singular command names         | #717   |
| Concept-oriented descriptions        | #718   |
| Concrete examples in help            | #719   |
| Root screen mockup                   | #720   |
| Page mockup: `ping`                  | #721   |
| Page mockup: `projects`              | #722   |
| Page mockup: `inv`                   | #723   |
| Page mockup: `env`                   | #724   |
| Page mockup: `repo`                  | #725   |
| Page mockup: `keys`                  | #726   |
| Page mockup: `templates`             | #727   |
| Page mockup: `sched`                 | #728   |
| Page mockup: `tasks`                 | #729   |
| Name-first addressing + `run`        | #730   |
