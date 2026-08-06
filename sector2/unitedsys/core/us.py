#!/usr/bin/env python3
import sys
import argparse
from core.detect      import sysinfo, get_backend, get_platform
from core.backends    import ALL
from core.transaction import Transaction, TransactionError
from core.resolver    import Resolver
from core.catalog     import init_db, list_packages, get_package, last_transaction
from core.manifest    import list_manifests, load as load_manifest, get_backend_name

def get_backend_instance(force=None):
    name = force or get_backend()
    if not name:
        print('ERROR: No supported package manager found on this system.')
        sys.exit(1)
    for cls in ALL:
        if cls.name == name:
            b = cls()
            if not b.available():
                print(f'ERROR: Backend {name} not available on this system.')
                sys.exit(1)
            return b
    print(f'ERROR: Unknown backend: {name}')
    sys.exit(1)

def cmd_install(args):
    backend  = get_backend_instance(args.via)
    resolver = Resolver()
    packages = []
    for pkg in args.packages:
        resolved = resolver.resolve(pkg, backend.name)
        for r in resolved:
            if r not in packages:
                packages.append(r)
    t = Transaction(backend)
    t.plan('install', packages)
    if args.dry_run:
        t.dry_run()
        return
    try:
        t.execute()
    except TransactionError as e:
        print(f'FAILED: {e}')
        sys.exit(1)

def cmd_remove(args):
    backend = get_backend_instance(args.via)
    t = Transaction(backend)
    t.plan('remove', args.packages)
    if args.dry_run:
        t.dry_run()
        return
    try:
        t.execute()
    except TransactionError as e:
        print(f'FAILED: {e}')
        sys.exit(1)

def cmd_upgrade(args):
    backend = get_backend_instance(args.via)
    t = Transaction(backend)
    pkgs = args.packages if args.packages else [None]
    t.plan('upgrade', pkgs)
    if args.dry_run:
        t.dry_run()
        return
    try:
        t.execute()
    except TransactionError as e:
        print(f'FAILED: {e}')
        sys.exit(1)

def cmd_search(args):
    backend = get_backend_instance(args.via)
    results = backend.search(args.query)
    if not results:
        print(f'No results for: {args.query}')
        return
    print(f'\nSearch results for "{args.query}" via {backend.name}:\n')
    for r in results:
        print(f'  {r["name"]:30} {r.get("description","")}')
    print()

def cmd_info(args):
    backend = get_backend_instance(args.via)
    info = backend.info(args.package)
    catalog = get_package(args.package)
    print(f'\n  Package : {args.package}')
    print(f'  Version : {info.get("version", "unknown")}')
    print(f'  Backend : {backend.name}')
    if info.get("description"):
        print(f'  Desc    : {info["description"]}')
    if catalog:
        print(f'  Installed : {catalog["installed_at"]}')
        if catalog.get("hash_sha3"):
            print(f'  SHA3-512  : {catalog["hash_sha3"][:32]}...')
    print()

def cmd_list(args):
    packages = list_packages()
    if not packages:
        print('No packages in catalog.')
        return
    print(f'\n{"Name":30} {"Version":15} {"Backend":10} {"Platform":10} Installed')
    print('-' * 80)
    for p in packages:
        print(f'  {p["name"]:28} {(p["version"] or ""):13} {(p["backend"] or ""):10} {(p["platform"] or ""):10} {p["installed_at"]}')
    print()

def cmd_doctor(args):
    info = sysinfo()
    print(f'\nUnitedSys Doctor\n{"="*40}')
    print(f'  Platform : {info["platform"]}')
    print(f'  Distro   : {info["distro"]}')
    print(f'  WSL      : {info["wsl"]}')
    print(f'  Python   : {info["python"]}')
    print(f'  Arch     : {info["arch"]}')
    print(f'  Primary  : {info["backend"]}')
    print(f'\n  Available backends:')
    for b in ALL:
        inst = b()
        status = 'OK' if inst.available() else '--'
        print(f'    [{status}] {b.name}')
    print()

def cmd_rollback(args):
    tx = last_transaction()
    if not tx:
        print('No transactions in catalog.')
        return
    print(f'\nLast transaction:')
    print(f'  Action  : {tx["action"]}')
    print(f'  Package : {tx["package"]}')
    print(f'  Status  : {tx["status"]}')
    print(f'  Backend : {tx["backend"]}')
    print(f'  Time    : {tx["timestamp"]}')
    if tx['status'] == 'rolled_back':
        print('Already rolled back.')
        return
    confirm = input(f'\nRollback {tx["action"]} of {tx["package"]}? [y/N] ')
    if confirm.lower() != 'y':
        print('Cancelled.')
        return
    backend = get_backend_instance(tx['backend'])
    t = Transaction(backend)
    reverse = 'remove' if tx['action'] == 'install' else 'install'
    t.plan(reverse, [tx['package']])
    try:
        t.execute()
        print('Rollback complete.')
    except TransactionError as e:
        print(f'Rollback failed: {e}')
        sys.exit(1)




def cmd_intake_dir(args):
    import subprocess
    from pathlib import Path
    from core.glossary import init_glossary, add_from_sidecar
    target = Path(args.directory).expanduser().resolve()
    if not target.exists():
        print(f'ERROR: directory not found: {target}')
        return
    excludes = {'.git', '__pycache__', 'site', '.db', 'rolodex'}
    files = [
        f for f in target.rglob('*')
        if f.is_file()
        and not any(ex in str(f) for ex in excludes)
        and not f.name.endswith('.pyc')
    ]
    print(f'Found {len(files)} files in {target}')
    print(f'Pool  : {args.pool}')
    print(f'State : {args.state}')
    print()
    ok = fail = 0
    for f in files:
        desc = args.desc or str(f.relative_to(target))
        result = subprocess.run(
            f'usys intake "{f}" "{args.pool}" "{args.state}" "{desc}"',
            shell=True, capture_output=True, text=True,
            executable='/usr/bin/zsh'
        )
        if 'Sidecar' in result.stdout or 'Registering' in result.stdout:
            ok += 1
            print(f'  [OK] {f.name}')
        else:
            fail += 1
            print(f'  [FAIL] {f.name}: {result.stderr.strip()[:60]}')
    print()
    print(f'Intake complete -- {ok} OK, {fail} failed')
    print('Syncing glossary...')
    init_glossary()
    imported = sum(1 for s in Path(args.pool).rglob('*.sidecar.json') if add_from_sidecar(str(s)))
    print(f'Glossary -- {imported} entries')

def cmd_gloss(args):
    from core.glossary import (init_glossary, list_entries, get_entry,
                                amend, check_evictions, list_categories)
    init_glossary()
    sub = args.gloss_cmd

    if sub == 'list':
        entries = list_entries(
            state    = getattr(args, 'state', None),
            category = getattr(args, 'category', None)
        )
        if not entries:
            print('No glossary entries.')
            return
        header = f"{'Name':25} {'Category':12} {'State':8} {'Amended':8} Grace Until"
        print('\n' + header)
        print('-' * 75)
        for e in entries:
            amended = 'YES' if e['amended'] else 'NO'
            print(f"  {e['name']:23} {(e['category'] or 'unknown'):12} {e['state']:8} {amended:8} {e['grace_until']}")
        print()

    elif sub == 'info':
        e = get_entry(args.identifier)
        if not e:
            print(f'Not found: {args.identifier}')
            return
        print()
        for k, v in e.items():
            if v is not None:
                print(f'  {k:15}: {v}')
        print()

    elif sub == 'amend':
        amend(args.identifier, args.description,
              category=getattr(args, 'category', None))
        print(f'  [OK] amended: {args.identifier}')

    elif sub == 'check':
        evicted = check_evictions()
        if not evicted:
            print('No entries to evict.')
            return
        for e in evicted:
            print(f'  [evicted] {e["name"]} ({e["hex"][:16]}...) grace expired: {e["grace_until"]}')

    elif sub == 'categories':
        cats = list_categories()
        header2 = f"{'Name':15} {'Hex':25} Description"
        print('\n' + header2)
        print('-' * 65)
        for c in cats:
            print(f"  {c['name']:13} {c['hex']:25} {c['description']}")
        print()
def cmd_seed(args):
    from core.backends.clonepool import ClonepoolBackend
    cp = ClonepoolBackend()
    if not cp.available():
        print('ERROR: Clonepool not available at /mnt/d/clonepool')
        return
    for package in args.packages:
        print(f'Seeding {package} into clonepool...')
        result = cp.seed(package)
        if result['success']:
            print(f'  [OK] {package} seeded')
        else:
            print(f'  [FAIL] {package}: {result["error"]}')
def cmd_manifests(args):
    manifests = list_manifests()
    if not manifests:
        print('No manifests found.')
        return
    print(f'\nAvailable manifests ({len(manifests)}):')
    for m in manifests:
        print(f'  {m}')
    print()

def main():
    init_db()

    parser = argparse.ArgumentParser(
        prog='us',
        description='UnitedSys — cross-platform package manager'
    )
    parser.add_argument('--version', action='version', version='UnitedSys 2.0.0')

    sub = parser.add_subparsers(dest='command', metavar='command')
    sub.required = True

    # install
    p_install = sub.add_parser('install', help='Install packages')
    p_install.add_argument('packages', nargs='+')
    p_install.add_argument('--via', help='Force specific backend')
    p_install.add_argument('--dry-run', action='store_true')
    p_install.set_defaults(func=cmd_install)

    # remove
    p_remove = sub.add_parser('remove', help='Remove packages')
    p_remove.add_argument('packages', nargs='+')
    p_remove.add_argument('--via', help='Force specific backend')
    p_remove.add_argument('--dry-run', action='store_true')
    p_remove.set_defaults(func=cmd_remove)

    # upgrade
    p_upgrade = sub.add_parser('upgrade', help='Upgrade packages')
    p_upgrade.add_argument('packages', nargs='*')
    p_upgrade.add_argument('--via', help='Force specific backend')
    p_upgrade.add_argument('--dry-run', action='store_true')
    p_upgrade.set_defaults(func=cmd_upgrade)

    # search
    p_search = sub.add_parser('search', help='Search for packages')
    p_search.add_argument('query')
    p_search.add_argument('--via', help='Force specific backend')
    p_search.set_defaults(func=cmd_search)

    # info
    p_info = sub.add_parser('info', help='Show package details')
    p_info.add_argument('package')
    p_info.add_argument('--via', help='Force specific backend')
    p_info.set_defaults(func=cmd_info)

    # list
    p_list = sub.add_parser('list', help='List installed packages')
    p_list.set_defaults(func=cmd_list)

    # doctor
    p_doctor = sub.add_parser('doctor', help='Diagnose system and backends')
    p_doctor.set_defaults(func=cmd_doctor)

    # rollback
    p_rollback = sub.add_parser('rollback', help='Undo last transaction')
    p_rollback.set_defaults(func=cmd_rollback)

    # manifests
    p_manifests = sub.add_parser('manifests', help='List available manifests')
    p_manifests.set_defaults(func=cmd_manifests)


    # seed
    p_seed = sub.add_parser('seed', help='Download package into clonepool')
    p_seed.add_argument('packages', nargs='+')
    p_seed.set_defaults(func=cmd_seed)

    # gloss
    p_gloss = sub.add_parser('gloss', help='Glossary management')
    gloss_sub = p_gloss.add_subparsers(dest='gloss_cmd', metavar='subcommand')
    gloss_sub.required = True

    pg_list = gloss_sub.add_parser('list', help='List glossary entries')
    pg_list.add_argument('--state',    help='Filter by state (white/evicted)')
    pg_list.add_argument('--category', help='Filter by category name or hex')
    pg_list.set_defaults(func=cmd_gloss)

    pg_info = gloss_sub.add_parser('info', help='Show glossary entry')
    pg_info.add_argument('identifier', help='Name or hex')
    pg_info.set_defaults(func=cmd_gloss)

    pg_amend = gloss_sub.add_parser('amend', help='Amend a glossary definition')
    pg_amend.add_argument('identifier',   help='Name or hex')
    pg_amend.add_argument('description',  help='New description')
    pg_amend.add_argument('--category',   help='Set category name or hex')
    pg_amend.set_defaults(func=cmd_gloss)

    pg_check = gloss_sub.add_parser('check', help='Evict unamended expired entries')
    pg_check.set_defaults(func=cmd_gloss)

    pg_cats = gloss_sub.add_parser('categories', help='List all categories')
    pg_cats.set_defaults(func=cmd_gloss)

    # intake-dir
    p_intake_dir = sub.add_parser('intake-dir', help='Intake entire directory into clonepool')
    p_intake_dir.add_argument('directory',         help='Directory to intake')
    p_intake_dir.add_argument('--pool',  default='/mnt/d/clonepool', help='Pool path')
    p_intake_dir.add_argument('--state', default='white',            help='white/grey/black')
    p_intake_dir.add_argument('--desc',  default='',                 help='Description prefix')
    p_intake_dir.set_defaults(func=cmd_intake_dir)
    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__':
    main()
