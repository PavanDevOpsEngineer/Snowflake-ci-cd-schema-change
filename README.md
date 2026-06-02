
# Snowflake CI/CD Schema Change

This repository implements a Snowflake migration CI/CD pipeline using GitHub Actions and a Python-driven deploy tool. It applies DDL and DML migrations, tracks migration history, and protects deployments with environment-specific workflows.

Key features
- GitHub Actions workflows for each environment:
  - `feature-deploy.yml`: DEV deploys on `feature/**` pushes when `migrations/ddl/**` or `migrations/dml/**` change.
  - `develop-deploy.yml`: QA deploys on PRs targeting `develop`, with migration path filters.
  - `main-deploy.yml`: PROD deploys on PRs targeting `main`, with migration path filters.
  - `hotfix-deploy.yml`: hotfix deployments on PRs targeting `hotfix/**`.
- `scripts/deploy.py` is the canonical CLI for applying migrations and includes:
  - `deploy` to apply migrations
  - `rollback` to apply rollback SQL
  - `validate` to verify schema connectivity
  - `generate` to scaffold migration files
  - `preflight` to parse SQL and catch syntax issues early
- Migration tracking and locking inside Snowflake via `schema_migrations` and a lock table.
- `<env>` placeholder replacement in SQL migration files for environment-specific object names.
- Environment config files in `config/<env>.yml` for Snowflake connection settings.
- Built with `snowflake-connector-python` and `PyYAML`.

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
4. Apply migrations to `dev`:
```bash
SNOWFLAKE_ACCOUNT=your-account SNOWFLAKE_USER=ci_user SNOWFLAKE_PASSWORD=secret SNOWFLAKE_WAREHOUSE=DEV_WH SNOWFLAKE_ROLE=CI_ROLE python3 scripts/deploy.py deploy dev
```

Core commands
- Deploy: `python3 scripts/deploy.py deploy <env>`
- Rollback: `python3 scripts/deploy.py rollback <env> [target]`
- Validate: `python3 scripts/deploy.py validate <env> [--tables ...]`
- Generate migration: `python3 scripts/deploy.py generate v1.2.0 "add_table" --type ddl`
- Preflight: `python3 scripts/deploy.py preflight`
- Workflow validation: `python3 scripts/validate_workflows.py`
- Secret verification: `python3 scripts/test_secrets.py`

How the CI flow works

- `feature/**` pushes trigger the DEV workflow and deploy only when migration files change.
- PRs targeting `develop` run the QA preflight checks and the actual deployment executes only after the PR is merged into `develop`.
- PRs targeting `main` run the PROD preflight checks and the actual deployment executes only after the PR is merged into `main`.
- Hotfix PRs target `hotfix/**` and deploy only after merge.

Merge policy

- Use **Merge Commit** as the merge strategy for `develop`, `main`, and `hotfix` PRs.
- This preserves the merge history and enables the workflow logic to detect merged PRs cleanly.
- Avoid squash or rebase merges for release-related branches, because this flow depends on merge commits and branch-level path filters.

Workflow implementation details

- Each workflow checks out code, installs Python 3.11, caches pip dependencies, validates Python scripts, verifies Snowflake secrets, replaces `<env>` placeholders in SQL files, then runs `scripts/deploy.py deploy <env>`.
- Workflows upload JSON-lines logs from `artifacts/*.log` so run details are available for inspection.
- `scripts/test_secrets.py` ensures Snowflake credentials are present before deployment.

Migration structure

- `migrations/ddl/`: schema changes and SQL objects
- `migrations/dml/`: reference data and seed data
- `migrations/rollback/`: rollback scripts for revert operations

Project structure

- `scripts/`: deployment tools and helpers. Contains the central deploy CLI (`deploy.py`), migration scaffolding (`generate_migration.py`), workflow validation (`validate_workflows.py`), secret checking (`test_secrets.py`), and backward-compatible wrappers like `rollback.py`.
- `migrations/ddl/`: DDL migration files for schema changes, stored procedures, functions, and object creation. Files in this directory use `<env>` placeholders that are replaced at deploy time.
- `migrations/dml/`: DML migration files for reference data, seed records, and environment-specific inserts or updates.
- `migrations/rollback/`: rollback scripts that reverse applied migrations; used by `scripts/deploy.py rollback`.
- `config/`: environment-specific Snowflake configuration files (`dev.yml`, `qa.yml`, `prod.yml`) that define connection settings, database, and schema defaults.
- `.github/workflows/`: GitHub Actions workflows that run environment deploys, apply path filters, and serialize runs by environment using concurrency groups.
- `artifacts/`: structured JSON log output from deployment runs. These logs are uploaded as workflow artifacts for auditing and debugging.
- `docs/`: operational documentation, branching strategy, and deployment guidance.
- `requirements.txt`: Python dependency manifest used by CI and local execution.

How deployments are protected

- The deploy tool records applied migration checksums in Snowflake and skips already-applied files.
- A Snowflake lock table prevents concurrent deploy runs from colliding.
- Workflows are scoped to migration path changes so unrelated PRs do not trigger deployments.

Additional notes

- `scripts/deploy.py` uses a robust SQL splitter that correctly handles single quotes, double quotes, dollar-quoted blocks, and comments.
- `scripts/generate_migration.py` creates skeletal migration files in the appropriate directory.
- `scripts/rollback.py` is a thin wrapper that delegates rollback work to `scripts/deploy.py`.

See `docs/` for more details on branching strategy, deployment guidance, and rollback procedures.
