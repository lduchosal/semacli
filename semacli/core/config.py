"""Configuration management for semacli."""

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

from .exceptions import ConfigurationError


@dataclass
class SemaphoreConfig:
    """Semaphore connection configuration."""

    url: str
    bearer_token: str | None = None
    project: int | None = None
    timeout: int = 30
    verify_ssl: bool = True
    allow_http: bool = False


def load_config(config_path: str = "semacli.ini") -> SemaphoreConfig:
    """Load configuration from file.

    Raises:
        ConfigurationError: If configuration is invalid
    """
    config = configparser.ConfigParser(interpolation=None)

    config_file = _find_config_file(config_path)

    if not config_file or not os.path.exists(config_file):
        raise ConfigurationError(f"Configuration file not found: {config_path}")

    config.read(config_file)

    return _parse_config(config)


def _find_config_file(config_path: str) -> str | None:
    """Find configuration file in standard locations.

    Search order:
    1. Absolute path (if provided)
    2. Current directory
    3. User home directory (~/.semacli.ini)
    4. /usr/local/etc/semacli.ini
    """
    if os.path.isabs(config_path):
        return config_path

    current_dir = Path.cwd() / config_path
    if current_dir.exists():
        return str(current_dir)

    home_dir = Path.home() / f".{config_path}"
    if home_dir.exists():
        return str(home_dir)

    system_config = Path("/usr/local/etc") / config_path
    if system_config.exists():
        return str(system_config)

    return config_path


def _parse_config(config: configparser.ConfigParser) -> SemaphoreConfig:
    """Parse configuration into SemaphoreConfig object."""
    if "semaphore" not in config:
        raise ConfigurationError("Missing [semaphore] section in configuration")

    sema_section = config["semaphore"]

    url = sema_section.get("url")
    if not url:
        raise ConfigurationError("Missing 'url' in [semaphore] section")

    project_raw = sema_section.get("project")
    project = int(project_raw) if project_raw else None

    bearer_token: str | None = None

    if "auth" in config:
        auth_section = config["auth"]
        method = auth_section.get("method", "bearer_token")

        if method == "bearer_token":
            bearer_token = auth_section.get("bearer_token")
        elif method == "env_var":
            env_var = auth_section.get("env_var", "SEMAPHORE_TOKEN")
            bearer_token = os.environ.get(env_var)
        else:
            raise ConfigurationError(f"Unknown auth method: {method}")
    else:
        bearer_token = sema_section.get("bearer_token")

    timeout = 30
    verify_ssl = True
    allow_http = False

    if "settings" in config:
        settings_section = config["settings"]
        timeout = settings_section.getint("timeout", 30)
        verify_ssl = settings_section.getboolean("verify_ssl", True)
        allow_http = settings_section.getboolean("allow_http", False)

    clean_url = url.rstrip("/")
    if clean_url.startswith("http://") and not allow_http:
        raise ConfigurationError(
            "Plain HTTP url is refused by default. Set 'allow_http = true' "
            "in the [settings] section to enable it (not recommended)."
        )

    return SemaphoreConfig(
        url=clean_url,
        bearer_token=bearer_token,
        project=project,
        timeout=timeout,
        verify_ssl=verify_ssl,
        allow_http=allow_http,
    )
