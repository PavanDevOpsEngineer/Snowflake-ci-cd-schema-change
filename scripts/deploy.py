#!/usr/bin/env python3
"""Deploy tool for Snowflake migrations.

Usage: scripts/deploy.py deploy|rollback|validate|generate <env>

This script reads config/<env>.yml for connection defaults and applies SQL
files from migrations/ddl and migrations/dml. It records applied migrations in
<database>.<schema>.schema_migrations and uses a simple lock table to prevent
concurrent runs.
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
        return yaml.safe_load(f) or {}


def compute_checksum(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def gather_migrations(kind):
    pattern = os.path.join('migrations', kind, '*.sql')
    files = sorted(glob.glob(pattern))
    return files


def apply_file(cursor, path, dry_run=False, atomic_override=False):
    print(f'-- Applying: {path}')
    with open(path, 'r') as f:
        sql = f.read()
    # split into statements and execute each separately to handle multi-statement files
    stmts = split_sql_statements(sql)
    if dry_run:
        for s in stmts:
            print(s)
        return
    # If file contains only DML statements, attempt to run atomically
    # If atomic_override is True, attempt to run the whole file atomically regardless
    if stmts and (atomic_override or is_dml_only(stmts)):
        try:
            cursor.execute('BEGIN')
            for s in stmts:
                if not s.strip():
                    continue
                cursor.execute(s)
            cursor.execute('COMMIT')
        except Exception:
            try:
                cursor.execute('ROLLBACK')
            except Exception:
                pass
            raise
    else:
        for s in stmts:
            if not s.strip():
                continue
            cursor.execute(s)


def split_sql_statements(sql_text):
    """Split SQL text into statements by semicolon, ignoring semicolons inside
    single/double quotes or dollar-quoted blocks (e.g. $$...$$ or $tag$...$tag$).
    Returns a list of statement strings without trailing semicolons.
    """
    statements = []
    cur = []
    in_squote = False
    in_dquote = False
    in_dollar = False
    dollar_tag = None
    in_line_comment = False
    in_block_comment = False
    i = 0
    L = len(sql_text)
    while i < L:
        ch = sql_text[i]

        # handle end of line comment
        if in_line_comment:
            if ch == '\n':
                in_line_comment = False
                cur.append(ch)
            i += 1
            continue

        # handle end of block comment
        if in_block_comment:
            if ch == '*' and i + 1 < L and sql_text[i+1] == '/':
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        # handle entering comments when not inside quotes/dollar
        if not in_squote and not in_dquote and not in_dollar:
            if ch == '-' and i + 1 < L and sql_text[i+1] == '-':
                in_line_comment = True
                i += 2
                continue
            if ch == '/' and i + 1 < L and sql_text[i+1] == '*':
                in_block_comment = True
                i += 2
                continue

        # handle dollar-quoted blocks
        if in_dollar:
            if sql_text.startswith(dollar_tag, i):
                cur.append(dollar_tag)
                i += len(dollar_tag)
                in_dollar = False
                dollar_tag = None
                continue
            else:
                cur.append(ch)
                i += 1
                continue

        if ch == '$' and not in_squote and not in_dquote:
            # try to read a dollar tag
            j = i + 1
            while j < L and (sql_text[j].isalnum() or sql_text[j] == '_'):
                j += 1
            if j < L and sql_text[j] == '$':
                dollar_tag = sql_text[i:j+1]
                cur.append(dollar_tag)
                i = j + 1
                in_dollar = True
                continue

        if ch == "'" and not in_dquote:
            in_squote = not in_squote
            cur.append(ch)
            i += 1
            continue

        if ch == '"' and not in_squote:
            in_dquote = not in_dquote
            cur.append(ch)
            i += 1
            continue

        if ch == ';' and not in_squote and not in_dquote and not in_dollar and not in_line_comment and not in_block_comment:
            stmt = ''.join(cur).strip()
            if stmt:
                statements.append(stmt)
            cur = []
            i += 1
            continue

        cur.append(ch)
        i += 1

    last = ''.join(cur).strip()
    if last:
        statements.append(last)

    # if any context is left open, raise a parse error
    if in_squote or in_dquote or in_dollar or in_block_comment:
        raise ValueError('Unterminated quote/dollar-quote or block comment detected')
    return statements


def preflight_validate_paths(paths):
    results = []
    for p in paths:
        try:
            with open(p, 'r') as f:
                txt = f.read()
            stmts = split_sql_statements(txt)
            results.append((p, 'ok', len(stmts)))
        except Exception as e:
            results.append((p, 'error', str(e)))
    return results


def is_dml_only(statements):
    dml_prefixes = ('INSERT', 'UPDATE', 'DELETE', 'MERGE')
    for s in statements:
        ss = s.lstrip().upper()
        if not ss:
            continue
        # if it starts with a DML verb, continue; otherwise it's not DML-only
        if not ss.startswith(dml_prefixes):
            return False
    return True


def ensure_migration_tables(cursor, database, schema, logfile):
    migrations_table = f"{database}.{schema}.schema_migrations"
    lock_table = f"{database}.{schema}.schema_migration_lock"
    cursor.execute(f"CREATE TABLE IF NOT EXISTS {migrations_table} (filename VARCHAR, checksum VARCHAR, applied_at TIMESTAMP_LTZ, status VARCHAR, note VARCHAR)")
    cursor.execute(f"CREATE TABLE IF NOT EXISTS {lock_table} (lock_name VARCHAR, owner VARCHAR, acquired_at TIMESTAMP_LTZ)")
    log_event(logfile, 'info', 'ensure_migration_tables', migrations_table=migrations_table, lock_table=lock_table)
    return migrations_table, lock_table


def acquire_lock(cursor, lock_table, owner, logfile):
    cursor.execute(f"SELECT owner FROM {lock_table} WHERE lock_name='deploy_lock'")
    rows = cursor.fetchall()
    if rows:
        existing = rows[0][0]
        log_event(logfile, 'error', 'lock_exists', owner=existing)
        raise RuntimeError(f"Deploy lock already held by {existing}")
    cursor.execute(f"INSERT INTO {lock_table} (lock_name, owner, acquired_at) VALUES ('deploy_lock', %s, current_timestamp())", (owner,))
    log_event(logfile, 'info', 'lock_acquired', owner=owner)


def release_lock(cursor, lock_table, owner, logfile):
    cursor.execute(f"DELETE FROM {lock_table} WHERE lock_name='deploy_lock' AND owner=%s", (owner,))
    log_event(logfile, 'info', 'lock_released', owner=owner)


def get_applied_checksums(cursor, migrations_table):
    cursor.execute(f"SELECT checksum FROM {migrations_table} WHERE status='success'")
    rows = cursor.fetchall()
    return set(r[0] for r in rows if r and r[0])


def connect(cfg, logfile, require_auth=True):
    account = os.environ.get('SNOWFLAKE_ACCOUNT') or cfg.get('account')
    user = os.environ.get('SNOWFLAKE_USER') or cfg.get('user')
    password = os.environ.get('SNOWFLAKE_PASSWORD') or cfg.get('password')
    warehouse = os.environ.get('SNOWFLAKE_WAREHOUSE') or cfg.get('warehouse')
    role = os.environ.get('SNOWFLAKE_ROLE') or cfg.get('role')

    if require_auth and (not account or not user or (not password and 'SNOWFLAKE_PRIVATE_KEY' not in os.environ)):
        raise RuntimeError('Missing Snowflake credentials. Set SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER and SNOWFLAKE_PASSWORD or private key.')

    conn_kwargs = dict(account=account, user=user)
    if password:
        conn_kwargs['password'] = password
    if warehouse:
        conn_kwargs['warehouse'] = warehouse
    if role:
        conn_kwargs['role'] = role
    if cfg.get('database'):
        conn_kwargs['database'] = cfg.get('database')
    if cfg.get('schema'):
        conn_kwargs['schema'] = cfg.get('schema')

    # allow callers to skip auth (dry-run) by setting require_auth=False
    if not require_auth:
        return None, None

    conn = snowflake.connector.connect(**conn_kwargs)
    cur = conn.cursor()
    # set session context explicitly to avoid unqualified object errors
    try:
        if cfg.get('database'):
            cur.execute(f"USE DATABASE {cfg.get('database')}")
        if cfg.get('schema'):
            cur.execute(f"USE SCHEMA {cfg.get('schema')}")
    except Exception:
        pass
    log_event(logfile, 'info', 'connected', account=account, user=user)
    return conn, cur


def subcommand_deploy(args):
    cfg = load_config(args.env)
    logfile = init_logger(args.env)
    log_event(logfile, 'info', 'start_deploy', env=args.env)

    # allow dry-run without credentials
    require_auth = not args.dry_run
    conn, cur = (None, None)
    if require_auth:
        conn, cur = connect(cfg, logfile, require_auth=True)

    owner = f"{os.environ.get('GITHUB_RUN_ID','local')}-{os.getpid()}-{datetime.utcnow().isoformat()}"
    try:
        if cur:
            migrations_table, lock_table = ensure_migration_tables(cur, cfg.get('database'), cfg.get('schema', 'PUBLIC'), logfile)
            acquire_lock(cur, lock_table, owner, logfile)
            applied = get_applied_checksums(cur, migrations_table)
        else:
            applied = set()

        for f in gather_migrations('ddl'):
            checksum = compute_checksum(f)
            if checksum in applied:
                log_event(logfile, 'info', 'skip_applied', file=f, checksum=checksum)
                continue
            log_event(logfile, 'info', 'apply_ddl_start', file=f)
            try:
                apply_file(cur, f, dry_run=args.dry_run, atomic_override=getattr(args, 'atomic_files', False))
                if cur:
                    cur.execute(f"INSERT INTO {migrations_table} (filename, checksum, applied_at, status) VALUES (%s, %s, current_timestamp(), 'success')", (os.path.basename(f), checksum))
                log_event(logfile, 'info', 'apply_ddl_end', file=f, checksum=checksum)
            except Exception as e:
                if cur:
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
                apply_file(cur, f, dry_run=args.dry_run, atomic_override=getattr(args, 'atomic_files', False))
                if cur:
                    cur.execute(f"INSERT INTO {migrations_table} (filename, checksum, applied_at, status) VALUES (%s, %s, current_timestamp(), 'success')", (os.path.basename(f), checksum))
                log_event(logfile, 'info', 'apply_dml_end', file=f, checksum=checksum)
            except Exception as e:
                if cur:
                    cur.execute(f"INSERT INTO {migrations_table} (filename, checksum, applied_at, status, note) VALUES (%s, %s, current_timestamp(), 'failed', %s)", (os.path.basename(f), checksum, str(e)))
                log_event(logfile, 'error', 'apply_dml_failed', file=f, error=str(e))
                raise

        log_event(logfile, 'info', 'migrations_processed', env=args.env)
        print('Migrations processed.')
    finally:
        if cur and lock_table and owner:
            try:
                release_lock(cur, lock_table, owner, logfile)
            except Exception:
                pass
        if cur:
            cur.close()
        if conn:
            conn.close()
        log_event(logfile, 'info', 'connection_closed', env=args.env)


def subcommand_rollback(args):
    cfg = load_config(args.env)
    logfile = init_logger(args.env)
    require_auth = not args.dry_run
    conn, cur = (None, None)
    if require_auth:
        conn, cur = connect(cfg, logfile, require_auth=True)

    try:
        files = sorted(glob.glob(os.path.join('migrations', 'rollback', '*.sql')), reverse=True)
        if args.target:
            files = [f for f in files if args.target in os.path.basename(f)]
        if not files:
            print('No rollback files found for given criteria.')
            return
        for f in files:
            log_event(logfile, 'info', 'apply_rollback_start', file=f)
            apply_file(cur, f, dry_run=args.dry_run, atomic_override=getattr(args, 'atomic_files', False))
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
    require_auth = not args.dry_run
    conn, cur = (None, None)
    if require_auth:
        conn, cur = connect(cfg, logfile, require_auth=True)
    try:
        # basic validation: if tables provided, try desc
        for t in args.tables:
            q = f"DESC TABLE IF EXISTS {t};"
            print(q)
            log_event(logfile, 'info', 'validate_query', query=q)
            if cur and not args.dry_run:
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
    d.add_argument('--atomic-files', action='store_true', help='Run each migration file atomically (wrap in transaction)')
    d.set_defaults(func=subcommand_deploy)

    r = sub.add_parser('rollback', help='Run rollback scripts')
    r.add_argument('env')
    r.add_argument('target', nargs='?', help='target version substring to match', default=None)
    r.add_argument('--dry-run', action='store_true')
    r.add_argument('--atomic-files', action='store_true', help='Run each rollback file atomically (wrap in transaction)')
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

    pflight = sub.add_parser('preflight', help='Parse all migrations and report parsing errors')
    pflight.add_argument('--dirs', nargs='*', default=['migrations/ddl', 'migrations/dml', 'migrations/rollback'], help='Directories to scan')
    pflight.set_defaults(func=lambda args: subcommand_preflight(args))

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        sys.exit(1)
    args.func(args)


def subcommand_preflight(args):
    dirs = args.dirs
    files = []
    for d in dirs:
        if os.path.isdir(d):
            for root, _dirs, fnames in os.walk(d):
                for fn in fnames:
                    if fn.lower().endswith('.sql'):
                        files.append(os.path.join(root, fn))
    results = preflight_validate_paths(files)
    has_error = False
    for p, status, info in results:
        if status == 'ok':
            print(f'OK: {p} -> {info} statements')
        else:
            print(f'ERROR: {p} -> {info}')
            has_error = True
    if has_error:
        print('Preflight found errors')
        sys.exit(2)
    print('Preflight passed')


if __name__ == '__main__':
    main()
