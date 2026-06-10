"""Semaphore HTTP API client.

The client is split per resource: ``_base`` owns the transport
(session, request building, error mapping) and each ``*Mixin`` module
covers one API resource. ``SemaphoreClient`` composes them back into
the single public class — import it from here, never from the
submodules.
"""

from ._base import BaseClient
from ._environments import EnvironmentsMixin
from ._integrations import IntegrationsMixin
from ._inventories import InventoriesMixin
from ._keys import KeysMixin
from ._projects import ProjectsMixin
from ._repositories import RepositoriesMixin
from ._schedules import SchedulesMixin
from ._tasks import TasksMixin
from ._templates import TemplatesMixin
from ._users import UsersMixin
from ._views import ViewsMixin

__all__ = ["SemaphoreClient"]


class SemaphoreClient(
    ProjectsMixin,
    TemplatesMixin,
    TasksMixin,
    InventoriesMixin,
    EnvironmentsMixin,
    RepositoriesMixin,
    KeysMixin,
    SchedulesMixin,
    UsersMixin,
    ViewsMixin,
    IntegrationsMixin,
    BaseClient,
):
    """HTTP client for Semaphore UI REST API.

    See ``BaseClient`` for the transport/SSL behaviour; resource
    methods live in the per-resource mixins.
    """
