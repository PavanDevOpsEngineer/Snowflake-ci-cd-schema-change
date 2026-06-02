#!/usr/bin/env python3
import os
import argparse
from datetime import datetime

def main():
    p = argparse.ArgumentParser()
    p.add_argument('version', nargs='?', default='v1.0.0')
    p.add_argument('description', nargs='?', default='description')
    p.add_argument('type', nargs='?', choices=['ddl','dml','rollback'], default='ddl')
    args = p.parse_args()

    name = f"{args.version}__{args.description.replace(' ','_')}.sql"
    dirpath = os.path.join('migrations', args.type)
    os.makedirs(dirpath, exist_ok=True)
    path = os.path.join(dirpath, name)
    with open(path, 'w') as f:
        f.write(f'-- {path}\n-- created: {datetime.utcnow().isoformat()}Z\n\n')
    print('Created', path)

if __name__ == '__main__':
    main()
