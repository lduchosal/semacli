# semacli — agent guide

CLI tool to drive [Semaphore UI](https://semaphoreui.com) via its HTTP REST
API. Python 3.10+, PDM-managed, click-based. See `README.md` / `ARCHITECTURE.md`
for the user-facing docs.

Parent project conventions (SVN externals, ken CLI install, monitor stack,
FreeBSD infra) live in `/Users/q/Projects/2113.ch/CLAUDE.md` — read that
first for anything outside this directory.

## UX standard

**Any change to `--help` text, prompts, output, or command structure must
follow [`UX.md`](UX.md).** It is the canonical reference for: English-only
copy, ASCII formatting (no ANSI colors), short singular group names
(`env`/`inv`/`repo`/`sched`), concept-first help text, realistic examples,
name-first addressing (`sem run mtree`), bare-group-as-list, and exit
code conventions. When a rule is challenged or refined, update `UX.md` in
the same commit as the code change.

## Work is tracked on kenboard

All tasks for this repo are queued on the kenboard board and assigned to
`Claude`. `.ken` (chmod 600, API token, `svn:global-ignore`d) is already
in this directory, so the `ken` CLI works from here directly. The full
agent contract is in `ken help` — this file captures only what's specific
to semacli.

## The loop: pick → doing → implement → desc → review → groom

1. **Pick.** Read your queue and announce the chosen task + reason in chat
   *before* touching code.

   ```sh
   ken list --who Claude --status todo
   ken show <id>
   ```

   Default to the human-readable output (no `--json`). The aligned table
   from `ken list` and the key-value pairs from `ken show` are directly
   readable.

2. **Mark WIP.** Move it before doing anything else so the board reflects
   reality and nobody else grabs the same card.

   ```sh
   ken move <id> --to doing
   ```

3. **Implement.** Make the change, then run the project's quality gates.
   For semacli the canonical gate is:

   ```sh
   pdm run check        # lint + format-check + typecheck + test
   ```

   Individual gates (use during iteration):

   ```sh
   pdm run lint         # ruff check semacli/ tests/
   pdm run lint-fix     # ruff check --fix
   pdm run format       # ruff format
   pdm run format-check # black --check (CI-equivalent)
   pdm run typecheck    # mypy semacli/
   pdm run test         # pytest + coverage
   pdm run test-quick   # pytest --tb=no -q
   ```

   If a failure shows up in an area you didn't touch, confirm it's
   pre-existing before continuing.

4. **Update the task description BEFORE moving to review.** Append a
   `## Résolution` block — the board accumulates the audit trail; commit
   messages alone are not enough.

   Use `--desc-file` (the safe idiom). Do **not** use `--desc "line1\nline2"` —
   bash does not interpret `\n` in double quotes, the result is a single
   broken line that corrupts every markdown block.

   ```sh
   cat > /tmp/ken-<id>.md <<'EOF'
   <original description verbatim>

   ---

   ## Résolution

   ### Modifications
   - semacli/cli.py: short summary
   - tests/unit/test_xxx.py: cases added

   ### Comportements obtenus
   - what works now that did not before

   ### Garde-fous
   - pdm run check: passed
   EOF

   ken update <id> --desc-file /tmp/ken-<id>.md
   ```

   Preserve the original description verbatim above the `---`. Always
   include all three sub-sections (Modifications, Comportements obtenus,
   Garde-fous).

5. **Move to review.**

   ```sh
   ken move <id> --to review
   ```

   Never move to `done` yourself — the user owns the `review → done`
   transition.

6. **Classify for the wiki.** `ken move --to review` prints a reminder.
   Pick the deepest matching section from `kenboard/ARCHITECTURE.md`
   (most semacli work fits under `cli/*`).

   ```sh
   ken wiki groom                 # list unclassified + sections
   ken wiki groom <id> cli/<sub>  # assign
   ```

   Skipping this leaves the task invisible to `ken wiki sync`.

## Title convention

Every task title follows `MODULE / Titre` (uppercase MODULE). Common
modules seen on the semacli queue:

- `SEMACLI / <area> <verb>` — feature work (most cards), e.g.
  `SEMACLI / templates create (POST /project/{pid}/templates)`.
  Sub-modules with ` / ` (`SEMACLI / user tokens list`).
- `BUG / …`, `FIX / …` — defects.
- `SEC / …` — security work (XSS, auth, SSL defaults).
- `CLEAN / …`, `REFACTOR / …` — non-behavioural maintenance.
- `QUALITY / …` — SonarCloud / coverage / interrogate.
- `DOC / …` — README, examples, docstrings.

When adding a card yourself, match the convention and keep the title
short — details go in `--desc` / `--desc-file`.

## Ownership

```
todo → doing → review → done
└──── agent owns ────┘  └─ user ─┘
```

Never call `ken done`. The user finalises after review.

## Quick reference

```sh
ken list --who Claude --status todo
ken show <id>
ken move <id> --to doing
# ... implement + pdm run check ...
ken update <id> --desc-file /tmp/ken-<id>.md
ken move <id> --to review
ken wiki groom <id> cli/<sub>
```

## Commit style (this repo)

Commits follow `<type>: <subject> (closes ken #<id>)` based on
`git log`. Examples from `main`:

- `feat: implement P1 — inventories/environments/repositories/keys/schedules CRUD + tasks list/stop/raw-output`
- `sec: secure-by-default SSL + opt-in HTTP / insecure-SSL (closes ken #638)`
- `test: bring coverage to 95% (closes ken #637)`
- `refactor: fix 3 SonarCloud maintainability issues (closes ken #639)`

Types in use: `feat`, `fix`, `sec`, `refactor`, `test`, `doc`. Always
reference the ken id when the commit closes a task.

## Don't

- Don't pipe `ken list --json` through `jq`/`awk`/python — use the
  native filters (`--who`, `--status`).
- Don't use `--desc "…\n…"` — corrupts markdown. Use `--desc-file` (or
  `--desc -` from stdin, or `$(cat <<'EOF' … EOF)`).
- Don't move tasks to `done`.
- Don't skip `ken wiki groom` after `--to review`.
- Don't use `// NOSONAR` or blanket suppressions — refactor or use
  scoped, documented config-level suppressions (see user memory
  `feedback-no-nosonar`).
