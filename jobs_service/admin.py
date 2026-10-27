"""Private data initialization, consistent backup, restore and retention."""
import argparse
import fcntl
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
from pathlib import Path
from .store import Store


def private_root(path):
    path=Path(path).resolve()
    checkout=Path(__file__).resolve().parents[1]
    if path==checkout or path.is_relative_to(checkout):
        raise ValueError('PRIVATE_DATA_MUST_BE_OUTSIDE_CHECKOUT')
    return path


def initialize(path):
    os.umask(0o077)
    path=private_root(path)
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    path.chmod(0o700)
    token=path/'api-token'
    if not token.exists():
        with token.open('x') as f: f.write(secrets.token_urlsafe(48))
        token.chmod(0o600)
    Store(path/'queue.sqlite3')
    for folder in ('applications','contexts'):
        (path/folder).mkdir(exist_ok=True,mode=0o700)


def backup(source,target):
    source,target=private_root(source),private_root(target)
    if target.exists(): raise ValueError('BACKUP_TARGET_EXISTS')
    if target.is_relative_to(source): raise ValueError('BACKUP_MUST_BE_SEPARATE')
    # Stop only this service's worker before backup. API may remain online;
    # SQLite's backup API takes a transactionally consistent snapshot.
    with (source/'worker.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('STOP_WORKER_BEFORE_BACKUP') from None
        target.mkdir(parents=True,mode=0o700)
        with sqlite3.connect(source/'queue.sqlite3') as src, sqlite3.connect(target/'queue.sqlite3') as dst:
            src.backup(dst)
        for item in ('profile.json','applications','contexts'):
            p=source/item
            if p.exists():
                if p.is_symlink() or (p.is_dir() and any(x.is_symlink() for x in p.rglob('*'))):
                    raise ValueError('PRIVATE_STORAGE_SYMLINK_REJECTED')
                if p.is_dir(): shutil.copytree(p,target/item)
                else: shutil.copy2(p,target/item)
        hashes={}
        for p in target.rglob('*'):
            p.chmod(0o700 if p.is_dir() else 0o600)
            if p.is_file(): hashes[str(p.relative_to(target))]=hashlib.sha256(p.read_bytes()).hexdigest()
        (target/'backup-manifest.json').write_text(json.dumps(hashes,indent=2))
        (target/'backup-manifest.json').chmod(0o600)


def restore(source,target):
    source,target=private_root(source),private_root(target)
    if target.exists(): raise ValueError('RESTORE_TARGET_EXISTS')
    manifest=json.loads((source/'backup-manifest.json').read_text())
    for name,expected in manifest.items():
        p=(source/name).resolve()
        if not p.is_relative_to(source) or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
            raise ValueError('BACKUP_INTEGRITY_FAILURE')
    target.mkdir(parents=True,mode=0o700)
    for name in manifest:
        dst=target/name
        dst.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        shutil.copy2(source/name,dst)
        dst.chmod(0o600)
    initialize(target)  # Issue fresh API token. OAuth and sessions are not backed up.


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('init','backup','restore','import-profile'))
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--source',type=Path)
    parser.add_argument('--target',type=Path)
    args=parser.parse_args()
    if args.action=='init': initialize(args.data_dir)
    elif args.action=='backup': backup(args.data_dir,args.target)
    elif args.action=='restore': restore(args.source,args.data_dir)
    else:
        initialize(args.data_dir)
        dest=private_root(args.data_dir)/'profile.json'
        if dest.exists(): raise ValueError('PROFILE_ALREADY_EXISTS')
        data=json.loads(args.source.read_text())
        # Retain original provenance; caller supplies confirmed facts separately.
        with dest.open('x') as f: json.dump(data,f,ensure_ascii=False,indent=2)
        dest.chmod(0o600)
    print('Private storage operation completed; no credential values displayed.')


if __name__=='__main__': main()
