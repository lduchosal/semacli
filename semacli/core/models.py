"""Data models for semacli (pydantic v2 BaseModel)."""

from pydantic import BaseModel, ConfigDict, Field


class _ApiModel(BaseModel):
    """Base class: allow field name OR API alias on input; ignore extras."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class Project(_ApiModel):
    """A Semaphore project."""

    id: int = 0
    name: str = ""
    created: str = ""
    alert: bool = False
    alert_chat: str = ""
    max_parallel_tasks: int = 0


class Template(_ApiModel):
    """A Semaphore task template."""

    id: int = 0
    project_id: int = 0
    name: str = ""
    playbook: str = ""
    inventory_id: int = 0
    repository_id: int = 0
    environment_id: int = 0
    description: str = ""


class Task(_ApiModel):
    """A Semaphore task (a run of a template)."""

    id: int = 0
    template_id: int = 0
    status: str = ""
    debug: bool = False
    dry_run: bool = False
    playbook: str = ""
    environment: str = ""
    created: str = ""
    start: str = ""
    end: str = ""


class Inventory(_ApiModel):
    """A Semaphore inventory.

    The API field is named ``inventory`` (the textual content); we expose
    it as ``content`` to avoid the field-matches-class-name confusion
    (SonarCloud S1700, ken #639). ``populate_by_name=True`` lets callers
    use either name; ``model_dump(by_alias=True)`` emits the API form.
    """

    id: int = 0
    project_id: int = 0
    name: str = ""
    type: str = ""
    content: str = Field("", alias="inventory")
    ssh_key_id: int = 0
    become_key_id: int = 0


class Environment(_ApiModel):
    """A Semaphore environment (extra vars + secrets).

    The API field ``json`` (a JSON-encoded string of env vars) is exposed
    as ``vars_json`` here to avoid shadowing BaseModel.json (deprecated
    method) and to be less ambiguous. populate_by_name=True keeps both
    forms accepted on input; model_dump(by_alias=True) emits ``json``.
    """

    id: int = 0
    project_id: int = 0
    name: str = ""
    password: str = ""
    vars_json: str = Field("", alias="json")


class Repository(_ApiModel):
    """A Semaphore repository (git source for playbooks)."""

    id: int = 0
    project_id: int = 0
    name: str = ""
    git_url: str = ""
    git_branch: str = ""
    ssh_key_id: int = 0


class Key(_ApiModel):
    """A Semaphore access key (SSH, login_password, none)."""

    id: int = 0
    project_id: int = 0
    name: str = ""
    type: str = ""


class Schedule(_ApiModel):
    """A Semaphore cron schedule."""

    id: int = 0
    project_id: int = 0
    template_id: int = 0
    cron_format: str = ""
    name: str = ""
    active: bool = True


class User(_ApiModel):
    """A Semaphore user."""

    id: int = 0
    name: str = ""
    username: str = ""
    email: str = ""
    admin: bool = False
    created: str = ""


class UserToken(_ApiModel):
    """A Semaphore user API token (created by `user tokens create`)."""

    id: str = ""
    created: str = ""
    expired: bool = False
    user_id: int = 0


class ProjectMember(_ApiModel):
    """A user attached to a project with a role (owner / manager / task_runner / guest)."""

    user_id: int = 0
    project_id: int = 0
    role: str = ""
    name: str = ""
    username: str = ""


class ApiInfo(_ApiModel):
    """Semaphore server metadata returned by GET /api/info."""

    version: str = ""


class View(_ApiModel):
    """A saved-filter / dashboard scoped to a project."""

    id: int = 0
    project_id: int = 0
    title: str = ""
    position: int = 0


class Integration(_ApiModel):
    """An inbound webhook attached to a template inside a project."""

    id: int = 0
    project_id: int = 0
    name: str = ""
    template_id: int = 0
    auth_method: str = ""
    auth_header: str = ""
    auth_secret_id: int = 0


class IntegrationMatcher(_ApiModel):
    """A pattern matcher gating an integration's incoming requests."""

    id: int = 0
    integration_id: int = 0
    name: str = ""
    match_type: str = ""
    method: str = ""
    key: str = ""
    value: str = ""


class ProjectEvent(_ApiModel):
    """An audit-log entry inside a project."""

    user_id: int = 0
    project_id: int = 0
    object_id: int = 0
    object_type: str = ""
    description: str = ""
    created: str = ""
