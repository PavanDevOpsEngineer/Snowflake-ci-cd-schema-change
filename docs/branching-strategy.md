# Branching Strategy

Follow GitFlow: `feature/*` → `develop` → `release/*` → `main`. Use `hotfix/*` for urgent production fixes.

Deployment flow

- `feature/*` pushes trigger `dev` deployments. Example local flow:

```bash
git clone git@github.com:your-org/Snowflake-ci-cd-schema-change.git
cd Snowflake-ci-cd-schema-change
git checkout -b feature/your-change
# edit migrations or code
git push -u origin feature/your-change
```

- Open a Pull Request from `feature/*` into `develop` to trigger the QA deployment. CI runs preflight and tests on the PR before merging.

- Open a Pull Request from `develop` into `main` to trigger the PROD deployment. Enforce required status checks and approval gates on this PR.

Merge / Push behavior

- When a PR is merged, the resulting push to the target branch (for example `develop` or `main`) will trigger the deploy workflow for that branch only if files under `migrations/ddl/**` or `migrations/dml/**` changed in the commit. This prevents unrelated changes from causing deployments.

Concurrency and queuing

- Deploys are queued per environment using `concurrency` groups in the workflows. Use these groups to reason about parallel runs:
	- `deploy-dev` — DEV feature branch deploys
	- `deploy-qa` — QA (develop) deploys
	- `deploy-prod` — PROD (main) and hotfix deploys

- The workflows are configured to queue new runs and not cancel in-progress runs, ensuring sequential application of migrations to each environment.

Workflows call `scripts/deploy.py` which applies migrations from `migrations/ddl` then `migrations/dml`.

Logging & CI
- Workflow linting uses `actionlint` for semantic checks; a YAML parse fallback exists.
- Deploys and rollbacks upload structured logs to `artifacts/` for debugging.
