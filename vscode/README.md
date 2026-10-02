# semacli for VS Code

Semaphore UI tasks of your project in the VS Code sidebar, driven by the
same `semacli.ini` as the `sem` CLI (ken #1131).

- **Running**: waiting / starting / running / stopping tasks, oldest first,
  with live run time. A badge on the view shows how many are running.
- **Finished**: the most recent success / error / stopped tasks, with run
  time and age.
- **Task detail**: click a task to open a read-only log document: status,
  template, limit, commit, origin (schedule or user), timestamps, URL, then
  the raw ansible output (ANSI colours stripped). It refreshes on its own
  while the task runs.
- **Stop**: the stop button (or the context menu) on a running task, after a
  confirmation. A task already `stopping` is offered a force stop.
- **Open in Semaphore**: the project history, or one task, in the browser.

## Install

Each semacli release on GitHub attaches `semacli-vscode-<version>.vsix`:

```sh
gh release download semacli-<version> -R lduchosal/semacli -p '*.vsix'
code --install-extension semacli-vscode-<version>.vsix
```

## Configuration

Nothing to configure in VS Code: the extension reads `semacli.ini` like
`sem` does.

| Search order | |
|---|---|
| `semacli.ini` | in the workspace folder, then each parent folder |
| `~/.semacli.ini` | |
| `/usr/local/etc/semacli.ini` | |

- `[semaphore] url`, `project` (required: the project whose tasks are shown).
- `[auth] method = bearer_token | env_var` (`env_var`, default
  `SEMAPHORE_TOKEN`), or `[semaphore] bearer_token` without `[auth]`.
- `[settings] load_dotenv = true` loads the `.env` next to the ini (or
  `load_dotenv_file`). Variables already in the environment win. The
  extension never writes to the shared process environment.
- `[settings] timeout`, `verify_ssl`, `allow_http`: same secure defaults as
  the CLI (plain `http://` is refused unless `allow_http = true`). TLS uses
  the trust store VS Code provides to extensions (OS certificates, proxy
  settings), which covers `use_system_ca`.

The ini is re-read on every refresh, so edits apply without reloading.

| Setting | Default | |
|---|---|---|
| `semacli.autoRefreshSeconds` | `15` | refresh period, `0` disables it; skipped while VS Code is in the background |
| `semacli.finishedLimit` | `50` | finished tasks shown (Semaphore returns the last 200) |

## Development

```sh
npm ci
npm run check      # biome lint + format, tsc --noEmit (JSDoc types), node --test with coverage gate
npm run package    # semacli-vscode-<version>.vsix
```

Plain JavaScript with `// @ts-check` + JSDoc, no build step, no runtime
dependency. `src/config.js`, `src/api.js` and `src/tasks.js` do not import
`vscode`. `src/extension.js` is tested against `test/vscode-stub.js`.
