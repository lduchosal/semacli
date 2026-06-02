"""Tests for semacli.core.models."""

from semacli.core.models import Environment, Inventory, Project, Task, Template


class TestProject:
    def test_minimal(self) -> None:
        p = Project(id=1, name="foo")
        assert p.id == 1
        assert p.name == "foo"
        assert p.created == ""
        assert p.alert is False
        assert p.alert_chat == ""
        assert p.max_parallel_tasks == 0

    def test_full(self) -> None:
        p = Project(
            id=7,
            name="prod",
            created="2026-01-01",
            alert=True,
            alert_chat="slack",
            max_parallel_tasks=5,
        )
        assert p.alert is True
        assert p.max_parallel_tasks == 5


class TestTemplate:
    def test_minimal(self) -> None:
        t = Template(id=1, project_id=2, name="deploy")
        assert t.id == 1
        assert t.project_id == 2
        assert t.name == "deploy"
        assert t.playbook == ""
        assert t.inventory_id == 0

    def test_full(self) -> None:
        t = Template(
            id=10,
            project_id=2,
            name="deploy",
            playbook="site.yml",
            inventory_id=3,
            repository_id=4,
            environment_id=5,
            description="prod deploy",
        )
        assert t.playbook == "site.yml"
        assert t.description == "prod deploy"


class TestTask:
    def test_minimal(self) -> None:
        t = Task(id=1, template_id=2)
        assert t.id == 1
        assert t.template_id == 2
        assert t.status == ""
        assert t.debug is False
        assert t.dry_run is False

    def test_full(self) -> None:
        t = Task(
            id=99,
            template_id=10,
            status="success",
            debug=True,
            dry_run=True,
            playbook="site.yml",
            environment="prod",
            created="c",
            start="s",
            end="e",
        )
        assert t.status == "success"
        assert t.debug is True


class TestInventory:
    def test_minimal(self) -> None:
        i = Inventory(id=1, project_id=2, name="hosts")
        assert i.id == 1
        assert i.type == ""

    def test_full(self) -> None:
        i = Inventory(
            id=1,
            project_id=2,
            name="hosts",
            type="static",
            content="[all]\nhost1\n",
            ssh_key_id=3,
            become_key_id=4,
        )
        assert i.type == "static"
        assert i.ssh_key_id == 3
        assert i.content.startswith("[all]")


class TestEnvironment:
    def test_minimal(self) -> None:
        e = Environment(id=1, project_id=2, name="prod")
        assert e.password == ""
        assert e.vars_json == ""

    def test_full(self) -> None:
        e = Environment(
            id=1,
            project_id=2,
            name="prod",
            password="secret",
            vars_json='{"k": "v"}',
        )
        assert e.password == "secret"
        assert e.vars_json == '{"k": "v"}'

    def test_accepts_api_alias(self) -> None:
        # API returns the JSON content under the "json" key.
        e = Environment.model_validate({"id": 1, "name": "x", "json": '{"k":"v"}'})
        assert e.vars_json == '{"k":"v"}'
