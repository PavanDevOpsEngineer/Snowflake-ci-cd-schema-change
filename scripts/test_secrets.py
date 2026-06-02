#!/usr/bin/env python3
"""Check presence of Snowflake-related environment variables.

Exits with code 0 if required vars are present, 2 otherwise.
This script is safe to print in CI logs (it only prints whether variables are set).
"""
import os
import sys

required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER"]
optional_keys = ["SNOWFLAKE_PASSWORD", "SNOWFLAKE_PRIVATE_KEY"]

def status(name):
    return "set" if os.environ.get(name) else "unset"

for k in required:
    print(f"{k}: {status(k)}")

pw_or_key = any(os.environ.get(k) for k in optional_keys)
print(f"SNOWFLAKE_AUTH_METHOD: {'password' if os.environ.get('SNOWFLAKE_PASSWORD') else ('private_key' if os.environ.get('SNOWFLAKE_PRIVATE_KEY') else 'none')}")

missing = [k for k in required if not os.environ.get(k)]
if missing or not pw_or_key:
    if missing:
        print("Missing required variables:", ", ".join(missing))
    if not pw_or_key:
        print("Missing authentication: set SNOWFLAKE_PASSWORD or SNOWFLAKE_PRIVATE_KEY")
    sys.exit(2)

print("All required Snowflake secrets appear available.")
sys.exit(0)
