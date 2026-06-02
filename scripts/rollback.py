#!/usr/bin/env python3
"""Thin wrapper to keep backward compatibility.
Delegates to `scripts/deploy.py rollback ...`.
"""
import sys
import subprocess

def main():
    args = ['python3', 'scripts/deploy.py', 'rollback'] + sys.argv[1:]
    rc = subprocess.call(args)
    sys.exit(rc)

if __name__ == '__main__':
    main()
