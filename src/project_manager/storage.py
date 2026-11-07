"""
Storage backends for the Project Manager.

Two backends are provided:

- DynamoDBStorage: stores projects/tasks in an AWS DynamoDB table.
- LocalStorage: stores everything in a local JSON file. Useful for
  trying the tool out without any AWS account, and used automatically
  as a fallback if AWS credentials / table access aren't available.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class Task:
    task_id: str
    project_id: str
    title: str
    status: str = "todo"  # todo | in_progress | done
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Project:
    project_id: str
    name: str
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)


class StorageError(Exception):
    pass


class BaseStorage:
    """Interface every storage backend implements."""

    def create_project(self, name: str) -> Project:
        raise NotImplementedError

    def list_projects(self) -> list[Project]:
        raise NotImplementedError

    def get_project(self, project_id: str) -> Optional[Project]:
        raise NotImplementedError

    def delete_project(self, project_id: str) -> None:
        raise NotImplementedError

    def add_task(self, project_id: str, title: str) -> Task:
        raise NotImplementedError

    def list_tasks(self, project_id: str) -> list[Task]:
        raise NotImplementedError

    def update_task_status(self, project_id: str, task_id: str, status: str) -> Task:
        raise NotImplementedError

    def delete_task(self, project_id: str, task_id: str) -> None:
        raise NotImplementedError


class LocalStorage(BaseStorage):
    """
    JSON-file-backed storage. Good for local dev / demos with no AWS
    dependency at all.
    """

    def __init__(self, path: str | Path = "project_manager_data.json"):
        self.path = Path(path)
        if not self.path.exists():
            self._write({"projects": {}, "tasks": {}})

    def _read(self) -> dict:
        with open(self.path, "r") as f:
            return json.load(f)

    def _write(self, data: dict) -> None:
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def create_project(self, name: str) -> Project:
        data = self._read()
        project = Project(project_id=_new_id(), name=name)
        data["projects"][project.project_id] = project.to_dict()
        self._write(data)
        return project

    def list_projects(self) -> list[Project]:
        data = self._read()
        return [Project(**p) for p in data["projects"].values()]

    def get_project(self, project_id: str) -> Optional[Project]:
        data = self._read()
        p = data["projects"].get(project_id)
        return Project(**p) if p else None

    def delete_project(self, project_id: str) -> None:
        data = self._read()
        data["projects"].pop(project_id, None)
        data["tasks"] = {
            tid: t for tid, t in data["tasks"].items()
            if t["project_id"] != project_id
        }
        self._write(data)

    def add_task(self, project_id: str, title: str) -> Task:
        if not self.get_project(project_id):
            raise StorageError(f"Project {project_id} not found")
        data = self._read()
        task = Task(task_id=_new_id(), project_id=project_id, title=title)
        data["tasks"][task.task_id] = task.to_dict()
        self._write(data)
        return task

    def list_tasks(self, project_id: str) -> list[Task]:
        data = self._read()
        return [
            Task(**t) for t in data["tasks"].values()
            if t["project_id"] == project_id
        ]

    def update_task_status(self, project_id: str, task_id: str, status: str) -> Task:
        data = self._read()
        t = data["tasks"].get(task_id)
        if not t or t["project_id"] != project_id:
            raise StorageError(f"Task {task_id} not found in project {project_id}")
        t["status"] = status
        t["updated_at"] = _now_iso()
        data["tasks"][task_id] = t
        self._write(data)
        return Task(**t)

    def delete_task(self, project_id: str, task_id: str) -> None:
        data = self._read()
        t = data["tasks"].get(task_id)
        if t and t["project_id"] == project_id:
            data["tasks"].pop(task_id)
            self._write(data)


class DynamoDBStorage(BaseStorage):
    """
    DynamoDB-backed storage.

    Expects a single table (default name: "ProjectManager") using a
    single-table design:
      PK = "PROJECT#<project_id>"      SK = "META"
      PK = "PROJECT#<project_id>"      SK = "TASK#<task_id>"

    Create the table (see README) before using this backend, or call
    `ensure_table()` to create it on the fly.
    """

    def __init__(self, table_name: Optional[str] = None, region_name: Optional[str] = None):
        import boto3  # imported lazily so LocalStorage-only use doesn't need boto3 installed

        self.table_name = table_name or os.environ.get("PM_TABLE_NAME", "ProjectManager")
        self.region_name = region_name or os.environ.get("AWS_REGION", "us-east-1")
        self._dynamodb = boto3.resource("dynamodb", region_name=self.region_name)
        self._table = self._dynamodb.Table(self.table_name)

    def ensure_table(self) -> None:
        """Create the DynamoDB table if it doesn't already exist."""
        import boto3
        from botocore.exceptions import ClientError

        client = boto3.client("dynamodb", region_name=self.region_name)
        try:
            client.describe_table(TableName=self.table_name)
            return  # already exists
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceNotFoundException":
                raise

        client.create_table(
            TableName=self.table_name,
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        client.get_waiter("table_exists").wait(TableName=self.table_name)

    def create_project(self, name: str) -> Project:
        project = Project(project_id=_new_id(), name=name)
        item = {"PK": f"PROJECT#{project.project_id}", "SK": "META", **project.to_dict()}
        self._table.put_item(Item=item)
        return project

    def list_projects(self) -> list[Project]:
        resp = self._table.scan(
            FilterExpression="SK = :sk",
            ExpressionAttributeValues={":sk": "META"},
        )
        return [Project(**{k: v for k, v in item.items() if k in Project.__dataclass_fields__})
                for item in resp.get("Items", [])]

    def get_project(self, project_id: str) -> Optional[Project]:
        resp = self._table.get_item(Key={"PK": f"PROJECT#{project_id}", "SK": "META"})
        item = resp.get("Item")
        if not item:
            return None
        return Project(**{k: v for k, v in item.items() if k in Project.__dataclass_fields__})

    def delete_project(self, project_id: str) -> None:
        for task in self.list_tasks(project_id):
            self.delete_task(project_id, task.task_id)
        self._table.delete_item(Key={"PK": f"PROJECT#{project_id}", "SK": "META"})

    def add_task(self, project_id: str, title: str) -> Task:
        if not self.get_project(project_id):
            raise StorageError(f"Project {project_id} not found")
        task = Task(task_id=_new_id(), project_id=project_id, title=title)
        item = {"PK": f"PROJECT#{project_id}", "SK": f"TASK#{task.task_id}", **task.to_dict()}
        self._table.put_item(Item=item)
        return task

    def list_tasks(self, project_id: str) -> list[Task]:
        resp = self._table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :prefix)",
            ExpressionAttributeValues={":pk": f"PROJECT#{project_id}", ":prefix": "TASK#"},
        )
        return [Task(**{k: v for k, v in item.items() if k in Task.__dataclass_fields__})
                for item in resp.get("Items", [])]

    def update_task_status(self, project_id: str, task_id: str, status: str) -> Task:
        resp = self._table.update_item(
            Key={"PK": f"PROJECT#{project_id}", "SK": f"TASK#{task_id}"},
            UpdateExpression="SET #s = :status, updated_at = :ts",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":status": status, ":ts": _now_iso()},
            ReturnValues="ALL_NEW",
        )
        attrs = resp["Attributes"]
        return Task(**{k: v for k, v in attrs.items() if k in Task.__dataclass_fields__})

    def delete_task(self, project_id: str, task_id: str) -> None:
        self._table.delete_item(Key={"PK": f"PROJECT#{project_id}", "SK": f"TASK#{task_id}"})


def get_storage() -> BaseStorage:
    """
    Pick a backend automatically:
    - PM_BACKEND=local  -> always LocalStorage
    - PM_BACKEND=dynamo -> always DynamoDBStorage (raises if unavailable)
    - unset             -> try DynamoDB, fall back to LocalStorage
    """
    backend = os.environ.get("PM_BACKEND", "auto").lower()

    if backend == "local":
        return LocalStorage()

    if backend == "dynamo":
        return DynamoDBStorage()

    # auto: try DynamoDB, fall back quietly
    try:
        storage = DynamoDBStorage()
        storage._table.load()  # forces a real call to check credentials/table
        return storage
    except Exception:
        return LocalStorage()
