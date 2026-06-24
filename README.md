# semacli

[![PyPI version](https://img.shields.io/pypi/v/semacli.svg)](https://pypi.org/project/semacli/)
[![Python versions](https://img.shields.io/pypi/pyversions/semacli.svg)](https://pypi.org/project/semacli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Build](https://github.com/lduchosal/semacli/actions/workflows/python-package.yml/badge.svg)](https://github.com/lduchosal/semacli/actions/workflows/python-package.yml)
[![Publish](https://github.com/lduchosal/semacli/actions/workflows/python-publish.yml/badge.svg)](https://github.com/lduchosal/semacli/actions/workflows/python-publish.yml)
[![codecov](https://codecov.io/gh/lduchosal/semacli/branch/main/graph/badge.svg)](https://codecov.io/gh/lduchosal/semacli)
[![Docstring coverage](./interrogate_badge.svg)](./interrogate_badge.svg)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=lduchosal_semacli&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=lduchosal_semacli)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=lduchosal_semacli&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=lduchosal_semacli)
[![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=lduchosal_semacli&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=lduchosal_semacli)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=lduchosal_semacli&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=lduchosal_semacli)
[![Bugs](https://sonarcloud.io/api/project_badges/measure?project=lduchosal_semacli&metric=bugs)](https://sonarcloud.io/summary/new_code?id=lduchosal_semacli)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=lduchosal_semacli&metric=vulnerabilities)](https://sonarcloud.io/summary/new_code?id=lduchosal_semacli)
[![Code Smells](https://sonarcloud.io/api/project_badges/measure?project=lduchosal_semacli&metric=code_smells)](https://sonarcloud.io/summary/new_code?id=lduchosal_semacli)
[![Technical Debt](https://sonarcloud.io/api/project_badges/measure?project=lduchosal_semacli&metric=sqale_index)](https://sonarcloud.io/summary/new_code?id=lduchosal_semacli)

A CLI tool to manage [Semaphore UI](https://semaphoreui.com) (ansible-semaphore) via its HTTP REST API.

Designed for LLM/agent and automation use — deterministic commands, JSON output, exit codes.

## Features

- List projects, templates, inventories, environments
- Launch and monitor tasks
- Read task output
- Schedules: cron or one-shot `--run-at` triggers, carrying the same
  ansible overrides as a run (`--limit` / `--tags` / `--skip-tags` /
  `--inventory` / `--cli-args`) so a planned run can target a subset of
  hosts without a dedicated template — see `sem sched create --help`
- JSON output support
- Bearer-token authentication (User Settings → API Tokens)

## Installation

```bash
# From PyPI
pip install semacli

# From source
pip install git+https://github.com/lduchosal/semacli.git

# Development
git clone https://github.com/lduchosal/semacli.git
cd semacli
pdm install
```

## Quick Start

### Configuration

Create `semacli.ini` in the current directory or `~/.semacli.ini`:

```ini
[semaphore]
url = https://monitor.example.com/semaphore
project = 1

[auth]
method = bearer_token
bearer_token = your-api-token-here

[settings]
timeout = 30
verify_ssl = true
```

Get a bearer token from the Semaphore UI: **User Settings → API Tokens → Create**.

### Basic Usage

```bash
# Ping the API
sem ping

# List projects
sem projects

# (more commands wired in as the CLI grows)
```

## Output Options

```bash
# JSON output
sem projects --json

# Verbose debugging
sem projects -v
sem projects -vv
sem projects -vvv
```

## Configuration Options

### Authentication Methods

#### Bearer token (recommended)

```ini
[semaphore]
url = https://monitor.example.com/semaphore

[auth]
method = bearer_token
bearer_token = your-api-token
```

#### Bearer token from environment variable

```ini
[semaphore]
url = https://monitor.example.com/semaphore

[auth]
method = env_var
env_var = SEMAPHORE_TOKEN
```

#### TLS / system certificate store

`requests` ships with the [certifi](https://pypi.org/project/certifi/) CA
bundle and ignores the OS trust store by default. On corporate Windows
machines, root CAs installed via Group Policy are therefore **not
trusted** and you'll see `SSLError: unable to get local issuer
certificate` against an internal Semaphore. Same trap on macOS if your
corp CA only lives in Keychain.

semacli defaults to `use_system_ca = auto` — on (Windows) / off (macOS,
Linux). Force it either way if needed:

```ini
[settings]
# use_system_ca = auto   # default: true on Windows, false elsewhere
# use_system_ca = true   # force-use OS trust store (e.g. macOS Keychain)
# use_system_ca = false  # force-use certifi bundle (e.g. cross-platform CI)
```

Implementation: when on, semacli calls `truststore.inject_into_ssl()`
(via the [`truststore`](https://pypi.org/project/truststore/) library,
maintained by the urllib3 author). TLS verification stays on — only the
source of trust anchors changes.

#### Auto-load `.env` (opt-in)

When `method = env_var`, the token must be in your shell before you run
`sem`. Two ways to make that happen:

1. **`direnv`** (recommended for active dev) — `brew install direnv` +
   `eval "$(direnv hook zsh)"`, then drop a `.envrc` (or `.env` with
   `dotenv` directive) in the project. Auto-loads on `cd`.
2. **`[settings] load_dotenv = true`** (no extra tool) — semacli reads
   `.env` next to your `semacli.ini` at startup. Existing shell vars
   always win, so the file only fills gaps.

```ini
[settings]
load_dotenv = true
# load_dotenv_file = .env   # optional; relative paths resolve against
                            # the semacli.ini directory.
```

```sh
# .env (gitignored, chmod 600)
SEMAPHORE_TOKEN=ninjwlgclse7_...
```

The file is parsed by [`python-dotenv`](https://pypi.org/project/python-dotenv/),
so quoting, comments, and `${VAR}` interpolation all work as expected.
A warning is printed if `.env` is group/world-readable — `chmod 600 .env`
to silence it.

#### Shell hooks around `sem run`

Declare `[hook]` keys in `semacli.ini` to fire shell commands before/after
a template run. Useful for syncing a remote repo, sending notifications,
or paging on failure. Relative paths resolve against the `.ini` directory.

```ini
[hook]
# Aborts the run with exit 6 on non-zero. Receives env vars:
#   SEMACLI_TEMPLATE, SEMACLI_LIMIT, SEMACLI_TAGS, SEMACLI_PROJECT,
#   SEMACLI_TEMPLATE_ID, SEMACLI_CONFIG, SEMACLI_EVENT
task_run_prehook = scripts/sync-svn.sh

# Fires after watch completes (any status). Failures = warnings only.
# Also receives SEMACLI_TASK_ID and SEMACLI_STATUS.
task_run_posthook = scripts/notify.sh

# Same envelope as posthook, fires only when status != success.
task_run_failhook = scripts/page-oncall.sh

# Default 60s, applies per-hook.
timeout = 30
```

Pass `--no-hooks` on `sem run` to bypass them (debug / replay).

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Configuration error |
| 3 | Authentication error |
| 4 | API error |
| 5 | Not found |
| 6 | Hook aborted the command (pre-hook returned non-zero or timed out) |

## Development

```bash
# Clone and setup
git clone https://github.com/lduchosal/semacli.git
cd semacli
pdm install -G dev

# Run tests
pdm test

# Lint and format
pdm lint
pdm format

# Type check
pdm typecheck

# Build
pdm build
```

## Architecture

```
semacli/
├── cli/                    # Click CLI interface
│   ├── commands/           # Individual commands
│   ├── decorators.py       # Common CLI options
│   └── handlers.py         # Error handlers
├── core/                   # Core business logic
│   ├── client.py           # Semaphore HTTP client
│   ├── config.py           # Configuration
│   ├── exceptions.py       # Custom exceptions
│   └── models.py           # Data models
└── services/               # Business services
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the wiki classification map used by `ken wiki groom`.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Related Projects

- [nagioscli](https://github.com/lduchosal/nagioscli) - sibling CLI for Nagios Core (model project)
