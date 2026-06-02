# Branching Strategy

Follow GitFlow: `feature/*` → `develop` → `release/*` → `main`. Use `hotfix/*` for urgent production fixes.

Deployment flow

- `feature/*` pushes trigger `dev` deployments
- Merges to `develop` trigger `qa` deployments
- `release/*` branches trigger `uat` deployments and require manual approval for promotion
- Merges to `main` trigger `prod` deployments (protected environments and approval gates recommended)

Workflows call `scripts/deploy.py` which applies migrations from `migrations/ddl` then `migrations/dml`. Create matching rollback scripts in `migrations/rollback/` for safe revert.

Logging & CI
- Workflow linting uses `actionlint` for semantic checks; a YAML parse fallback exists.
- Deploys and rollbacks upload structured logs to `artifacts/` for debugging.
