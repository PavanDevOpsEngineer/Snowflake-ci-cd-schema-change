#!/usr/bin/env python3
"""Deploy tool using Snowflake Python connector.

Subcommands: deploy, rollback, validate, generate

Features:
- Applies migrations from migrations/ddl then migrations/dml
- Records applied migrations in a `schema_migrations` table
- Attempts a simple lock via `schema_migration_lock` table to prevent concurrent runs
- Emits JSON-lines logs to `artifacts/` and prints them to stdout
"""
import os
import sys
import argparse
import glob
import yaml
import snowflake.connector
from datetime import datetime
import json
import hashlib


def init_logger(env):
    os.makedirs('artifacts', exist_ok=True)
    ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    fname = f'artifacts/deploy-{env}-{ts}.log'
    return fname


def log_event(logfile, level, message, **fields):
    entry = {
        'ts': datetime.utcnow().isoformat() + 'Z',
        'level': level,
        'message': message,
    }
    entry.update(fields)
    line = json.dumps(entry, default=str)
    print(line)
    try:
        with open(logfile, 'a') as fh:
            fh.write(line + '\n')
    except Exception:
        pass


def load_config(env):
    path = os.path.join('config', f'{env}.yml')
    if not os.path.exists(path):
        raise FileNotFoundError(f'Config file not found: {path}')
    with open(path) as f:
        return yaml.safe_load(f)


def compute_checksum(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def gather_migrations(kind):
    pattern = os.path.join('migrations', kind, '*.sql')
    files = sorted(glob.glob(pattern))
    return files


def apply_file(cursor, path, dry_run=False):
    print(f'-- Applying: {path}')
    with open(path, 'r') as f:
        sql = f.read()
    if dry_run:
        print(sql)
        return
    # Execute the file content; Snowflake will execute statements.
    try:
        cursor.execute(sql)
    except Exception:
        print(f'Error applying {path}', file=sys.stderr)
        raise


def ensure_migration_tables(cur, db, schema, logfile):
    migrations_table = f"{db}.{schema}.schema_migrations"
    lock_table = f"{db}.{schema}.schema_migration_lock"
    # Create tables if they don't exist
    cur.execute(f"CREATE TABLE IF NOT EXISTS {migrations_table} (filename VARCHAR, checksum VARCHAR, applied_at TIMESTAMP_LTZ, status VARCHAR, note VARCHAR)")
    cur.execute(f"CREATE TABLE IF NOT EXISTS {lock_table} (lock_name VARCHAR, owner VARCHAR, acquired_at TIMESTAMP_LTZ)")
    log_event(logfile, 'info', 'ensure_migration_tables', migrations_table=migrations_table, lock_table=lock_table)
    return migrations_table, lock_table


def acquire_lock(cur, lock_table, owner, logfile):
    # Check existing lock
    cur.execute(f"SELECT owner, acquired_at FROM {lock_table} WHERE lock_name='deploy_lock'")
    rows = cur.fetchall()
    if rows:
        existing_owner = rows[0][0]
        log_event(logfile, 'error', 'lock_exists', owner=existing_owner)
        raise RuntimeError(f"Deploy lock already held by {existing_owner}")
    # Acquire lock by inserting row
    cur.execute(f"INSERT INTO {lock_table} (lock_name, owner, acquired_at) VALUES ('deploy_lock', %s, current_timestamp())", (owner,))
    log_event(logfile, 'info', 'lock_acquired', owner=owner)


def release_lock(cur, lock_table, owner, logfile):
    cur.execute(f"DELETE FROM {lock_table} WHERE lock_name='deploy_lock' AND owner=%s", (owner,))
    log_event(logfile, 'info', 'lock_released', owner=owner)


def get_applied_checksums(cur, migrations_table):
    cur.execute(f"SELECT checksum FROM {migrations_table} WHERE status='success'")
    rows = cur.fetchall()
    return set(r[0] for r in rows if r and r[0])


def subcommand_deploy(args):
    cfg = load_config(args.env)
    logfile = init_logger(args.env)

    account = os.environ.get('SNOWFLAKE_ACCOUNT') or cfg.get('account')
    user = os.environ.get('SNOWFLAKE_USER')
    password = os.environ.get('SNOWFLAKE_PASSWORD')
    warehouse = os.environ.get('SNOWFLAKE_WAREHOUSE') or cfg.get('warehouse')
    role = os.environ.get('SNOWFLAKE_ROLE') or cfg.get('role')

    # Allow dry-run to operate without credentials
    if not args.dry_run:
        if not account or not user or (not password and 'SNOWFLAKE_PRIVATE_KEY' not in os.environ):
            print('Missing Snowflake credentials. Set SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER and SNOWFLAKE_PASSWORD or private key.', file=sys.stderr)
            sys.exit(2)

    if args.dry_run:
        print('Running in dry-run mode; SQL will be printed but not executed.')
        log_event(logfile, 'info', 'dry_run', env=args.env)

    conn_kwargs = dict(account=account, user=user, warehouse=warehouse, role=role)
    if password:
        conn_kwargs['password'] = password

    # Note: key-pair auth not implemented in this script; can be added if needed.

    if not args.dry_run:
        conn = snowflake.connector.connect(**conn_kwargs)
        cur = conn.cursor()
    else:
        conn = None
        cur = None

    owner = f"{os.environ.get('GITHUB_RUN_ID','local')}-{os.getpid()}-{datetime.utcnow().isoformat()}"
    migrations_table = None
    lock_table = None
    try:
        log_event(logfile, 'info', 'start_deploy', env=args.env, owner=owner)
        # Ensure migration tables exist and acquire lock
        if not args.dry_run:
            db = cfg.get('database')
            schema = cfg.get('schema', 'PUBLIC')
            migrations_table, lock_table = ensure_migration_tables(cur, db, schema, logfile)
            acquire_lock(cur, lock_table, owner, logfile)

            applied = get_applied_checksums(cur, migrations_table)
        else:
            applied = set()

        # Apply DDL then DML only if checksum not applied
        for f in gather_migrations('ddl'):
            checksum = compute_checksum(f)
            if checksum in applied:
                log_event(logfile, 'info', 'skip_applied', file=f, checksum=checksum)
                continue
            log_event(logfile, 'info', 'apply_ddl_start', file=f)
            try:
                apply_file(cur, f, dry_run=args.dry_run)
                if not args.dry_run:
                    cur.execute(f"INSERT INTO {migrations_table} (filename, checksum, applied_at, status) VALUES (%s, %s, current_timestamp(), 'success')", (os.path.basename(f), checksum))
                log_event(logfile, 'info', 'apply_ddl_end', file=f, checksum=checksum)
            except Exception as e:
                if not args.dry_run:
                    cur.execute(f"INSERT INTO {migrations_table} (filename, checksum, applied_at, status, note) VALUES (%s, %s, current_timestamp(), 'failed', %s)", (os.path.basename(f), checksum, str(e)))
                log_event(logfile, 'error', 'apply_ddl_failed', file=f, error=str(e))
                raise

        for f in gather_migrations('dml'):
            checksum = compute_checksum(f)
            if checksum in applied:
                log_event(logfile, 'info', 'skip_applied', file=f, checksum=checksum)
                continue
            log_event(logfile, 'info', 'apply_dml_start', file=f)
            try:
                apply_file(cur, f, dry_run=args.dry_run)
                if not args.dry_run:
                    cur.execute(f"INSERT INTO {migrations_table} (filename, checksum, applied_at, status) VALUES (%s, %s, current_timestamp(), 'success')", (os.path.basename(f), checksum))
                log_event(logfile, 'info', 'apply_dml_end', file=f, checksum=checksum)
            except Exception as e:
                if not args.dry_run:
                    cur.execute(f"INSERT INTO {migrations_table} (filename, checksum, applied_at, status, note) VALUES (%s, %s, current_timestamp(), 'failed', %s)", (os.path.basename(f), checksum, str(e)))
                log_event(logfile, 'error', 'apply_dml_failed', file=f, error=str(e))
                raise

        log_event(logfile, 'info', 'migrations_processed', env=args.env)
        print('Migrations processed.')
    finally:
        # release lock if held
        if cur and lock_table and owner:
            try:
                release_lock(cur, lock_table, owner, logfile)
            except Exception as e:
                log_event(logfile, 'warn', 'release_lock_failed', error=str(e))
        if cur:
            cur.close()
        if conn:
            conn.close()
        log_event(logfile, 'info', 'connection_closed', env=args.env)


def subcommand_rollback(args):
    cfg = load_config(args.env)
    logfile = init_logger(args.env)
    account = os.environ.get('SNOWFLAKE_ACCOUNT') or cfg.get('account')
    user = os.environ.get('SNOWFLAKE_USER')
    password = os.environ.get('SNOWFLAKE_PASSWORD')
    warehouse = os.environ.get('SNOWFLAKE_WAREHOUSE') or cfg.get('warehouse')
    role = os.environ.get('SNOWFLAKE_ROLE') or cfg.get('role')

    if not account or not user or (not password and 'SNOWFLAKE_PRIVATE_KEY' not in os.environ):
        print('Missing Snowflake credentials. Set SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER and SNOWFLAKE_PASSWORD or private key.', file=sys.stderr)
        sys.exit(2)

    conn_kwargs = dict(account=account, user=user, warehouse=warehouse, role=role)
    if password:
        conn_kwargs['password'] = password

    if not args.dry_run:
        conn = snowflake.connector.connect(**conn_kwargs)
        cur = conn.cursor()
    else:
        conn = None
        cur = None

    try:
        files = sorted(glob.glob(os.path.join('migrations', 'rollback', '*.sql')), reverse=True)
        if args.target:
            # filter files that include the target version string
            files = [f for f in files if args.target in os.path.basename(f)]

        if not files:
            print('No rollback files found for given criteria.')
            return

        for f in files:
            log_event(logfile, 'info', 'apply_rollback_start', file=f)
            apply_file(cur, f, dry_run=args.dry_run)
            log_event(logfile, 'info', 'apply_rollback_end', file=f)

        log_event(logfile, 'info', 'rollback_complete', env=args.env)
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def subcommand_validate(args):
    cfg = load_config(args.env)
    logfile = init_logger(args.env)
    account = os.environ.get('SNOWFLAKE_ACCOUNT') or cfg.get('account')
    user = os.environ.get('SNOWFLAKE_USER')
    password = os.environ.get('SNOWFLAKE_PASSWORD')
    warehouse = os.environ.get('SNOWFLAKE_WAREHOUSE') or cfg.get('warehouse')
    role = os.environ.get('SNOWFLAKE_ROLE') or cfg.get('role')

    if not account or not user or (not password and 'SNOWFLAKE_PRIVATE_KEY' not in os.environ):
        print('Missing Snowflake credentials. Set SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER and SNOWFLAKE_PASSWORD or private key.', file=sys.stderr)
        sys.exit(2)

    conn_kwargs = dict(account=account, user=user, warehouse=warehouse, role=role)
    if password:
        conn_kwargs['password'] = password

    if not args.dry_run:
        conn = snowflake.connector.connect(**conn_kwargs)
        cur = conn.cursor()
    else:
        conn = None
        cur = None

    try:
        # basic validation: check tables listed
        for t in args.tables:
            q = f"DESC TABLE IF EXISTS {t};"
            print(q)
            log_event(logfile, 'info', 'validate_query', query=q)
            if not args.dry_run:
                cur.execute(q)
                for r in cur:
                    print(r)
                    log_event(logfile, 'info', 'validate_result', table=t, row=str(r))
        print('Validation complete.')
        log_event(logfile, 'info', 'validation_complete', env=args.env)
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def subcommand_generate(args):
    ver = args.version
    desc = args.description.replace(' ', '_')
    kind = args.type
    name = f"{ver}__{desc}.sql"
    dirpath = os.path.join('migrations', kind)
    os.makedirs(dirpath, exist_ok=True)
    path = os.path.join(dirpath, name)
    with open(path, 'w') as f:
        f.write(f'-- {path}\n-- created: {datetime.utcnow().isoformat()}Z\n\n')
    print(f'Created {path}')


def main():
    p = argparse.ArgumentParser(description='Manage migrations using Snowflake Python connector')
    sub = p.add_subparsers(dest='cmd')

    d = sub.add_parser('deploy', help='Apply migrations')
    d.add_argument('env', nargs='?', default='dev')
    d.add_argument('--dry-run', action='store_true')
    d.set_defaults(func=subcommand_deploy)

    r = sub.add_parser('rollback', help='Run rollback scripts')
    r.add_argument('env')
    r.add_argument('target', nargs='?', help='target version substring to match', default=None)
    r.add_argument('--dry-run', action='store_true')
    r.set_defaults(func=subcommand_rollback)

    v = sub.add_parser('validate', help='Validate schema connectivity')
    v.add_argument('env')
    v.add_argument('--tables', nargs='*', default=['users'])
    v.add_argument('--dry-run', action='store_true')
    v.set_defaults(func=subcommand_validate)

    g = sub.add_parser('generate', help='Generate a migration SQL file')
    g.add_argument('version', nargs='?', default='v1.0.0')
    g.add_argument('description', nargs='?', default='description')
    g.add_argument('--type', choices=['ddl', 'dml', 'rollback'], default='ddl')
    g.set_defaults(func=subcommand_generate)

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == '__main__':
    main()
