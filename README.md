# AWS Project Manager

A small command-line tool for tracking projects and tasks, backed by
**AWS DynamoDB** — with a **local JSON fallback** so you can try it
out immediately with no AWS account required.

## Features

- Create/list/delete projects
- Add/list/update/delete tasks within a project
- Pluggable storage: DynamoDB in production, local JSON for dev/demo
- Unit tests using [moto](https://github.com/getmoto/moto) to mock AWS (no real AWS calls or costs in CI)
- GitHub Actions CI workflow included

## Project structure

```
aws-project-manager/
├── src/project_manager/
│   ├── __init__.py
│   ├── cli.py          # command-line interface
│   └── storage.py       # LocalStorage + DynamoDBStorage backends
├── tests/
│   └── test_storage.py
├── .github/workflows/ci.yml
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Quickstart (no AWS needed)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Force the local JSON backend
export PM_BACKEND=local          # Windows: set PM_BACKEND=local

pm project create "Website Redesign"
pm project list
pm task add <project_id> "Write homepage copy"
pm task list <project_id>
pm task done <project_id> <task_id>
```

Data is stored in `project_manager_data.json` in your working directory.

## Using it with real AWS

1. Configure AWS credentials (any of the usual ways work):
   ```bash
   aws configure
   # or set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_REGION env vars
   ```

2. Create the DynamoDB table (one-time), either via the AWS Console or
   by letting the app do it for you:
   ```bash
   export PM_BACKEND=dynamo
   python -c "from project_manager.storage import DynamoDBStorage; DynamoDBStorage().ensure_table()"
   ```
   This creates a single on-demand (pay-per-request) table named
   `ProjectManager` with a `PK`/`SK` key schema. Override the name with
   `PM_TABLE_NAME`.

3. Use the CLI exactly as before — it now reads/writes DynamoDB:
   ```bash
   pm project create "Mobile App Launch"
   pm task add <project_id> "Submit to App Store"
   ```

By default (`PM_BACKEND` unset), the app tries DynamoDB first and
falls back to local JSON if AWS isn't reachable/configured — handy
while you're still setting things up.

## Running tests

```bash
pytest -v
```

The DynamoDB tests use `moto` to simulate AWS in-memory, so they run
fully offline and never touch a real AWS account.

## Ideas for extending this

- Add a `pm project rename` command
- Add due dates / priorities to tasks
- Swap the CLI for a small Flask/FastAPI API and deploy it on AWS Lambda
- Add an S3-backed export/import (`pm export s3://bucket/key.json`)

## License

MIT — do whatever you'd like with it.
