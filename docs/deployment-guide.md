# Deployment Guide

Use the GitHub Actions workflows under `.github/workflows/` to deploy to each environment. Ensure secrets are set.

Local usage (Python-driven)

1. Install dependencies:
```bash
python3 -m pip install -r requirements.txt
```
2. Dry-run deploy (prints SQL):
```bash
python3 scripts/deploy.py deploy dev --dry-run
```
3. Real deploy (requires GitHub secrets or env vars):
```bash
SNOWFLAKE_ACCOUNT=... SNOWFLAKE_USER=... SNOWFLAKE_PASSWORD=... SNOWFLAKE_WAREHOUSE=... SNOWFLAKE_ROLE=... python3 scripts/deploy.py deploy dev
```

Workflows automatically set up Python 3.11, cache pip, install `requirements.txt`, and run a sanity-check (`python -m py_compile scripts/*.py`) before executing the scripts.
Workflows automatically set up Python 3.11, cache pip, install `requirements.txt`, and run a sanity-check (`python -m py_compile scripts/*.py`) before executing the scripts.

CI notes
- Linting uses `rhysd/actionlint@v1` to validate GitHub Actions semantics. A Python YAML fallback runs after actionlint.
- Workflows upload structured JSON logs (`artifacts/*.log`) after runs for debugging and audit.

Authentication
If you rely on key-pair authentication, I can add support for `SNOWFLAKE_PRIVATE_KEY` handling in `deploy.py`.
