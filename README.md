
# Snowflake CI/CD Schema Change

This repository implements a GitFlow-style CI/CD pipeline for Snowflake schema changes (DDL + DML) across DEV → QA → UAT → PROD.

Key points
- Workflows: `.github/workflows/*` (feature/develop/release/main/hotfix/rollback)
- All deploy/rollback/validate/generate functionality is provided by `scripts/deploy.py` (Python + Snowflake connector)
- Additional convenience scripts: `scripts/generate_migration.py`, `scripts/validate_workflows.py`.

Quick start

1. Install dependencies locally:
```bash
python3 -m pip install -r requirements.txt
```
2. Create required GitHub secrets (minimum):
```text
SNOWFLAKE_ACCOUNT
SNOWFLAKE_USER
SNOWFLAKE_PASSWORD (or private key)
SNOWFLAKE_WAREHOUSE
SNOWFLAKE_ROLE
```
3. Dry-run migrations against `dev`:
```bash
SNOWFLAKE_ACCOUNT=your-account SNOWFLAKE_USER=ci_user SNOWFLAKE_PASSWORD=secret python3 scripts/deploy.py deploy dev --dry-run
```
4. Apply migrations:
```bash
SNOWFLAKE_ACCOUNT=your-account SNOWFLAKE_USER=ci_user SNOWFLAKE_PASSWORD=secret SNOWFLAKE_WAREHOUSE=DEV_WH SNOWFLAKE_ROLE=CI_ROLE python3 scripts/deploy.py deploy dev
```

Other commands
- Rollback: `python3 scripts/deploy.py rollback <env> [target]`
- Validate connectivity/tables: `python3 scripts/deploy.py validate <env>`
- Generate migration: `python3 scripts/deploy.py generate v1.2.0 "add_table" --type ddl`

CI notes
- Workflows install Python 3.11, cache pip, and install `requirements.txt` before running scripts.
CI details
- Workflows are pinned to **Python 3.11** and cache pip based on `requirements.txt` to speed installs.
- Linting for GitHub workflows uses `rhysd/actionlint@v1` (semantic checks for Actions) with a Python YAML fallback.
- After each deploy/rollback run the workflows upload structured JSON logs from `artifacts/*.log` so you can download and inspect run details.

Notes on scripts
- `scripts/deploy.py` is the canonical tool (subcommands: `deploy`, `rollback`, `validate`, `generate`).
- `scripts/rollback.py` and `scripts/validate_schema.py` are thin wrappers that delegate to `deploy.py` for backward compatibility.

Logging & observability
- Deploy and rollback commands emit JSON-lines structured logs into `artifacts/` (uploaded as workflow artifacts). Fields include timestamps, event types, file names, and query results for validation steps.

Security & secrets
- Store credentials as GitHub secrets (`SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD` or key material, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_ROLE`).

Recommended next steps
- Implement a `schema_migrations` history table and a deploy lock to avoid concurrent runs and to make migrations idempotent.
- Add key-pair auth support for `deploy.py` if you prefer private-key over passwords.
- Linting for GitHub workflows runs via `scripts/validate_workflows.py`.

See `docs/` for more details.
