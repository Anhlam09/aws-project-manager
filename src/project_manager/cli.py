"""
Command-line interface for the Project Manager.

Examples:
    pm project create "Website Redesign"
    pm project list
    pm task add <project_id> "Write homepage copy"
    pm task list <project_id>
    pm task done <project_id> <task_id>
    pm task delete <project_id> <task_id>
    pm project delete <project_id>
"""

from __future__ import annotations

import argparse
import sys

from .storage import get_storage, StorageError


def _print_project(p) -> None:
    print(f"[{p.project_id}] {p.name}  (created {p.created_at})")


def _print_task(t) -> None:
    marker = {"todo": " ", "in_progress": "~", "done": "x"}.get(t.status, "?")
    print(f"  ({marker}) [{t.task_id}] {t.title}  [{t.status}]")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pm", description="A tiny AWS-backed project/task manager.")
    sub = parser.add_subparsers(dest="entity", required=True)

    project = sub.add_parser("project", help="Manage projects")
    project_sub = project.add_subparsers(dest="action", required=True)

    p_create = project_sub.add_parser("create", help="Create a new project")
    p_create.add_argument("name")

    project_sub.add_parser("list", help="List all projects")

    p_delete = project_sub.add_parser("delete", help="Delete a project")
    p_delete.add_argument("project_id")

    task = sub.add_parser("task", help="Manage tasks")
    task_sub = task.add_subparsers(dest="action", required=True)

    t_add = task_sub.add_parser("add", help="Add a task to a project")
    t_add.add_argument("project_id")
    t_add.add_argument("title")

    t_list = task_sub.add_parser("list", help="List tasks in a project")
    t_list.add_argument("project_id")

    t_status = task_sub.add_parser("status", help="Update a task's status")
    t_status.add_argument("project_id")
    t_status.add_argument("task_id")
    t_status.add_argument("status", choices=["todo", "in_progress", "done"])

    t_done = task_sub.add_parser("done", help="Mark a task as done")
    t_done.add_argument("project_id")
    t_done.add_argument("task_id")

    t_delete = task_sub.add_parser("delete", help="Delete a task")
    t_delete.add_argument("project_id")
    t_delete.add_argument("task_id")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    storage = get_storage()

    try:
        if args.entity == "project":
            if args.action == "create":
                _print_project(storage.create_project(args.name))
            elif args.action == "list":
                projects = storage.list_projects()
                if not projects:
                    print("No projects yet. Create one with: pm project create <name>")
                for p in projects:
                    _print_project(p)
            elif args.action == "delete":
                storage.delete_project(args.project_id)
                print(f"Deleted project {args.project_id}")

        elif args.entity == "task":
            if args.action == "add":
                _print_task(storage.add_task(args.project_id, args.title))
            elif args.action == "list":
                tasks = storage.list_tasks(args.project_id)
                if not tasks:
                    print("No tasks yet.")
                for t in tasks:
                    _print_task(t)
            elif args.action == "status":
                _print_task(storage.update_task_status(args.project_id, args.task_id, args.status))
            elif args.action == "done":
                _print_task(storage.update_task_status(args.project_id, args.task_id, "done"))
            elif args.action == "delete":
                storage.delete_task(args.project_id, args.task_id)
                print(f"Deleted task {args.task_id}")

    except StorageError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
