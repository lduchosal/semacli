"""Data models for semacli."""

from dataclasses import dataclass


@dataclass
class Project:
    """A Semaphore project."""

    id: int
    name: str
    created: str = ""
    alert: bool = False
    alert_chat: str = ""
    max_parallel_tasks: int = 0


@dataclass
class Template:
    """A Semaphore task template."""

    id: int
    project_id: int
    name: str
    playbook: str = ""
    inventory_id: int = 0
    repository_id: int = 0
    environment_id: int = 0
    description: str = ""


@dataclass
class Task:
    """A Semaphore task (a run of a template)."""

    id: int
    template_id: int
    status: str = ""
    debug: bool = False
    dry_run: bool = False
    playbook: str = ""
    environment: str = ""
    created: str = ""
    start: str = ""
    end: str = ""


@dataclass
class Inventory:
    """A Semaphore inventory."""

    id: int
    project_id: int
    name: str
    type: str = ""
    content: str = ""
    ssh_key_id: int = 0
    become_key_id: int = 0


@dataclass
class Environment:
    """A Semaphore environment (extra vars + secrets)."""

    id: int
    project_id: int
    name: str
    password: str = ""
    json: str = ""
