import os
import tempfile

import pytest

from project_manager.storage import LocalStorage, StorageError


@pytest.fixture
def local_storage():
    with tempfile.TemporaryDirectory() as tmp:
        yield LocalStorage(path=os.path.join(tmp, "data.json"))


def test_create_and_list_project(local_storage):
    p = local_storage.create_project("Website Redesign")
    assert p.name == "Website Redesign"
    projects = local_storage.list_projects()
    assert len(projects) == 1
    assert projects[0].project_id == p.project_id


def test_add_and_list_tasks(local_storage):
    p = local_storage.create_project("Website Redesign")
    t1 = local_storage.add_task(p.project_id, "Write homepage copy")
    t2 = local_storage.add_task(p.project_id, "Design logo")

    tasks = local_storage.list_tasks(p.project_id)
    assert {t.task_id for t in tasks} == {t1.task_id, t2.task_id}
    assert all(t.status == "todo" for t in tasks)


def test_add_task_to_missing_project_raises(local_storage):
    with pytest.raises(StorageError):
        local_storage.add_task("nonexistent", "Some task")


def test_update_task_status(local_storage):
    p = local_storage.create_project("Website Redesign")
    t = local_storage.add_task(p.project_id, "Write homepage copy")
    updated = local_storage.update_task_status(p.project_id, t.task_id, "done")
    assert updated.status == "done"

    tasks = local_storage.list_tasks(p.project_id)
    assert tasks[0].status == "done"


def test_delete_task(local_storage):
    p = local_storage.create_project("Website Redesign")
    t = local_storage.add_task(p.project_id, "Write homepage copy")
    local_storage.delete_task(p.project_id, t.task_id)
    assert local_storage.list_tasks(p.project_id) == []


def test_delete_project_cascades_tasks(local_storage):
    p = local_storage.create_project("Website Redesign")
    local_storage.add_task(p.project_id, "Write homepage copy")
    local_storage.delete_project(p.project_id)

    assert local_storage.get_project(p.project_id) is None
    assert local_storage.list_tasks(p.project_id) == []


@pytest.mark.dynamo
class TestDynamoDBStorage:
    """
    These tests use moto to mock AWS, so no real AWS account or
    credentials are needed to run them.
    """

    def test_full_lifecycle(self):
        moto = pytest.importorskip("moto")
        with moto.mock_aws():
            from project_manager.storage import DynamoDBStorage

            storage = DynamoDBStorage(table_name="TestProjectManager", region_name="us-east-1")
            storage.ensure_table()

            p = storage.create_project("Mobile App Launch")
            assert p.name == "Mobile App Launch"

            t = storage.add_task(p.project_id, "Submit to App Store")
            assert t.status == "todo"

            updated = storage.update_task_status(p.project_id, t.task_id, "in_progress")
            assert updated.status == "in_progress"

            tasks = storage.list_tasks(p.project_id)
            assert len(tasks) == 1

            storage.delete_task(p.project_id, t.task_id)
            assert storage.list_tasks(p.project_id) == []

            storage.delete_project(p.project_id)
            assert storage.get_project(p.project_id) is None
