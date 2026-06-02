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
semacli ping

# List projects
semacli projects

# (more commands wired in as the CLI grows)
```

## Output Options

```bash
# JSON output
semacli projects --json

# Verbose debugging
semacli projects -v
semacli projects -vv
semacli projects -vvv
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

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Configuration error |
| 3 | Authentication error |
| 4 | API error |
| 5 | Not found |

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
