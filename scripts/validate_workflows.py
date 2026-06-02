#!/usr/bin/env python3
import sys
import glob
import subprocess
import yaml

def main():
    files = glob.glob('.github/workflows/*.yml') + glob.glob('.github/workflows/*.yaml')
    if not files:
        print('No workflow files found')
        return 0

    failed = 0
    for f in files:
        print('Checking:', f)
        try:
            # prefer actionlint if installed
            p = subprocess.run(['actionlint', f], check=False)
            if p.returncode == 0:
                continue
        except FileNotFoundError:
            pass

        # fallback to YAML load
        try:
            with open(f) as fh:
                yaml.safe_load(fh)
        except Exception as e:
            print('YAML parse error in', f, e, file=sys.stderr)
            failed = 1

    if failed:
        return 1
    print('All workflow files are syntactically valid')
    return 0

if __name__ == '__main__':
    sys.exit(main())
