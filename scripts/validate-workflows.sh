#!/usr/bin/env bash
set -euo pipefail

echo "Validating GitHub workflow YAML files..."

FAILED=0

shopt -s nullglob
files=(.github/workflows/*.yml .github/workflows/*.yaml)
if [ ${#files[@]} -eq 0 ]; then
  echo "No workflow files found in .github/workflows"
  exit 0
fi

for f in "${files[@]}"; do
  echo "Checking: $f"
  if command -v actionlint >/dev/null 2>&1; then
    actionlint "$f" || FAILED=1
  elif command -v ruby >/dev/null 2>&1; then
    ruby -ryaml -e "YAML.load_file(ARGV[0])" "$f" || FAILED=1
  elif command -v python3 >/dev/null 2>&1; then
    python3 - <<PY
import sys
try:
    import yaml
except Exception as e:
    print('PyYAML not available; please install pyyaml or use actionlint', file=sys.stderr)
    sys.exit(2)
try:
    yaml.safe_load(open(sys.argv[1]))
except Exception as e:
    print(e, file=sys.stderr)
    sys.exit(1)
print('OK')
PY
    if [ $? -ne 0 ]; then FAILED=1; fi
  else
    echo "No YAML validator found (actionlint / ruby / python3+PyYAML). Install one to enable full validation." >&2
    exit 2
  fi
done

if [ $FAILED -ne 0 ]; then
  echo "One or more workflow files failed validation" >&2
  exit 1
fi

echo "All workflow files are syntactically valid"
