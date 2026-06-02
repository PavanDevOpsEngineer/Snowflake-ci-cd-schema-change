# Rollback Procedures

Use the `rollback` workflow or `scripts/deploy.py rollback` to revert migrations. Always validate on a non-prod copy first.

Examples:

Dry-run rollback:
```bash
python3 scripts/deploy.py rollback dev v1.0.0 --dry-run
```

Trigger via GitHub Actions (manual dispatch): open the `rollback` workflow and provide `environment` and `target_version` inputs.

Observability
- Rollback runs write structured logs to `artifacts/` that are uploaded by the workflow; download them from the Actions run to inspect what was executed.
