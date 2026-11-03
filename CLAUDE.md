# semacli — agent guide

CLI tool to drive [Semaphore UI](https://semaphoreui.com) via its HTTP REST
API. Python 3.10+, PDM-managed, click-based. See `README.md` / `ARCHITECTURE.md`
for the user-facing docs.

Parent project conventions (SVN externals, ken CLI install, monitor stack,
FreeBSD infra) live in the parent meta-repo's `CLAUDE.md` — read that
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
   pdm run lint              # ruff check semacli/ tests/
   pdm run lint-fix          # ruff check --fix
   pdm run format            # ruff format
   pdm run format-check      # black --check (CI-equivalent)
   pdm run typecheck         # mypy semacli/
   pdm run test              # pytest + coverage (unit + integration replay)
   pdm run test-quick        # pytest --tb=no -q (everything)
   pdm run test-unit         # unit only, with coverage
   pdm run test-integration  # cassette replay strict (--vcr-record=none)
   pdm run vulture           # dead code (whitelist: vulture_whitelist.py)
   pdm run refurb            # modernisation refurb
   pdm run metrics           # snapshot des critères qualité
   pdm run metrics-gate      # gate qualité bloquant (paliers + ratchet)
   pdm run vscode-install    # npm ci de l'extension VS Code (vscode/)
   pdm run vscode-check      # biome + tsc --noEmit + node --test (coverage gate)
   ```

   L'extension VS Code (`vscode/`, ken #1131) relit `semacli.ini` via sa
   propre implémentation (`vscode/src/config.js`) : tout changement du
   format de config (`semacli/core/config.py`) doit être reporté là, tests
   compris. `publish.sh` package le `.vsix` et l'attache à la release
   GitHub `semacli-<version>`.

   Le gate qualité (ken #828, porté de kenboard) : plafonds absolus par
   palier + ratchet best-ever contre `doc/quality-history.csv` — voir
   [`doc/code-quality.md`](doc/code-quality.md). Règle d'or : on ne détend
   jamais un seuil sans décision humaine tracée. Quand une famille ruff de
   `DEBT_SELECT` tombe à zéro, elle passe dans `[tool.ruff.lint] select`.

   If a failure shows up in an area you didn't touch, confirm it's
   pre-existing before continuing.

### Integration tests (VCR cassettes)

`tests/integration/` exercises the real HTTP contract against a recorded
Semaphore. Replay is strict, runs offline, and gates `publish.sh` before
`python -m build` — a stale cassette fails the release.

To **add** a new cassette:

```sh
# 1. Write the test under tests/integration/, decorate with @pytest.mark.vcr.
# 2. Record against the real server (uses semacli.ini for URL + token):
SEMACLI_RECORD=1 pdm run test-integration-record \
    tests/integration/test_my_new_thing.py
# 3. Verify replay strict still passes (no network):
pdm run test-integration
# 4. Confirm no token leaked into the YAML:
grep -i 'bearer' tests/integration/cassettes/test_my_new_thing.yaml
# Must print only `Bearer REDACTED`.
```

Resource-creating cassettes (`create_xxx` calls) must wrap their assertions
in `try: ... finally: client.delete_xxx(...)` so the cassette captures the
DELETE and the server is left clean.

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

Never call `ken done` on your own. The user finalises after review — or
asks you to, through the closing ceremony below.

## Closing ceremony

Copied from the angel `README.md` (§ Closing ceremony), adapted to this git
repo. When a task is finished, the user asks for it in these words — *« ken
done, ken tldr, commit, groom, wiki, publish »* (or just *« cloture »*). The
steps, in order:

| Step | What it means |
|---|---|
| **ken done** | `ken done <id>`. This is the one moment the rule *« never move to done yourself »* is lifted: the user is asking for it. If real leftovers remain, open a **follow-up task** for them rather than leaving the finished one open. |
| **ken tldr** | Rewrite the task description with a **TL;DR** on top, then the detail below: what was done, which commits / versions, what was found, what is explicitly *not* done. The board is the audit trail — commit messages alone are not enough. Use `--desc-file`, never `--desc "…\n…"` (the `\n` stays literal and wrecks the markdown). |
| **commit** | Everything still pending in this repo — `git status`, then `git commit` following the commit style below (`closes ken #<id>`). Often a no-op because the work was committed as it went; say so rather than staying silent. |
| **groom** | `ken wiki groom <id> <section>` (most semacli work: `cli/<sub>`). `ken wiki groom` with no arguments lists what is still unclassified — the pre-flight. Only classified tasks reach the wiki. |
| **wiki** | `ken wiki sync` → `ken wiki build`: exports the classified tasks to `wiki/` and renders `wiki-html/` locally. |
| **publish** | `svn ci wiki wiki-html` → `semacli run wiki --limit monitor1`: pushes the rendered wiki and deploys it to <https://www.monitor.2113.ch/wiki/>. |

**wiki** + **publish** are chained by a single command, run from the angel
root: `.venv/bin/angel publish`.

```sh
ken done <id>
ken update <id> --desc-file <scratch>/ken-<id>.md   # TL;DR + detail
git status && git commit ...                         # nothing left behind?
ken wiki groom <id> cli/<sub>
(cd .. && .venv/bin/angel publish)                   # wiki + publish
```

Run `angel publish` from the angel root — other venvs may hold a stale `ken`
that shadows the good one. If it fails at `svn ci` or at `semacli run wiki`,
it is almost always the laptop VPN: reconnect and replay the two steps by
hand, the sync and build are already done.

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
- Don't move tasks to `done` — except when the user asks for the closing ceremony.
- Don't skip `ken wiki groom` after `--to review`.
- Don't use `// NOSONAR` or blanket suppressions — refactor or use
  scoped, documented config-level suppressions (see user memory
  `feedback-no-nosonar`).
