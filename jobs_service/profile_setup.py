"""Operator-issued, expiring, single-use profile import. Never a public profile editor."""
import argparse
import fcntl
import hashlib
import json
import math
import os
import secrets
import shutil
import tempfile
import time
from pathlib import Path
from .policy import verified_fact


def atomic_json(path,value):
    fd,name=tempfile.mkstemp(prefix=path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f: json.dump(value,f,ensure_ascii=False,indent=2)
        os.chmod(name,0o600);os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)


def issue_link(root,now=None):
    root=Path(root);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    token=secrets.token_urlsafe(32)
    with (root/'profile-import.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        atomic_json(root/'profile-setup.json',{'sha256':hashlib.sha256(token.encode()).hexdigest(),'expires':(time.time() if now is None else now)+900})
    return token


def link_valid(root,token):
    if not isinstance(token,str) or not 32<=len(token)<=128: return False
    try:
        p=Path(root)/'profile-setup.json'
        if p.stat().st_mode&0o077: return False
        value=json.loads(p.read_text())
        return value['expires']>time.time() and secrets.compare_digest(value['sha256'],hashlib.sha256(token.encode()).hexdigest())
    except (OSError,ValueError,KeyError,TypeError): return False


def validate_profile(profile):
    if not isinstance(profile,dict): raise ValueError('INVALID_PROFILE')
    identity=profile.get('identity')
    if not isinstance(identity,dict): raise ValueError('PROFILE_IDENTITY_MISSING')
    for key in ('full_name','preferred_email'):
        if not isinstance(identity.get(key),str) or not 2<=len(identity[key])<=300: raise ValueError('PROFILE_IDENTITY_MISSING')
    if '@' not in identity['preferred_email']: raise ValueError('PROFILE_EMAIL_INVALID')
    locations=profile.get('locations')
    if not isinstance(locations,dict): raise ValueError('PROFILE_LOCATION_MISSING')
    found=False
    for key in ('brazil','united_states'):
        if key not in locations: continue
        loc=locations[key]
        if not isinstance(loc,dict) or not isinstance(loc.get('cv_location'),str) or not 2<=len(loc['cv_location'])<=300: raise ValueError('INVALID_PROFILE_LOCATION')
        found=True
    if not found: raise ValueError('PROFILE_LOCATION_MISSING')
    for key in ('phone','linkedin'):
        value=identity.get(key)
        if value is not None and not isinstance(value,(str,dict)): raise ValueError('INVALID_PROFILE_CONTACT')
        if isinstance(value,dict):
            if value.get('value') is not None and not isinstance(value['value'],str): raise ValueError('INVALID_PROFILE_CONTACT')
            if 'source_kind' in value and not isinstance(value['source_kind'],str): raise ValueError('INVALID_PROFILE_CONTACT')
    for key in ('compensation','work_authorization'):
        if key in profile and not isinstance(profile[key],dict): raise ValueError('INVALID_PROFILE_SECTION')
    floors=profile.get('compensation',{}).get('salary_base_floors',{})
    if not isinstance(floors,dict) or any(not isinstance(v,dict) for v in floors.values()): raise ValueError('INVALID_SALARY_FLOORS')
    for values in floors.values():
        for key in ('monthly','annual'):
            if key in values and (type(values[key]) not in (int,float) or not math.isfinite(values[key]) or values[key]<=0): raise ValueError('INVALID_SALARY_FLOORS')
    work=profile.get('work_authorization',{})
    if 'united_states' in work and not isinstance(work['united_states'],dict): raise ValueError('INVALID_WORK_AUTHORIZATION')
    facts=profile.get('facts')
    if not isinstance(facts,list) or not 1<=len(facts)<=500: raise ValueError('CONFIRMED_FACTS_MISSING')
    if any(not isinstance(f,dict) or not isinstance(f.get('id'),str) or not isinstance(f.get('text'),str) for f in facts): raise ValueError('INVALID_FACTS')
    for fact in facts:
        if not fact['id'] or not fact['text'] or len(fact['id'])>200 or len(fact['text'])>10000: raise ValueError('INVALID_FACTS')
        if 'source_kind' in fact and not isinstance(fact['source_kind'],str): raise ValueError('INVALID_FACTS')
        if 'translations' in fact and (not isinstance(fact['translations'],dict) or any(not isinstance(v,str) or not v or len(v)>10000 for v in fact['translations'].values())): raise ValueError('INVALID_TRANSLATIONS')
    if len({f['id'] for f in facts})!=len(facts): raise ValueError('DUPLICATE_FACT_IDS')
    count=sum(verified_fact(f) for f in facts)
    if not count: raise ValueError('CONFIRMED_FACTS_MISSING')
    return count


def consume_link(root,token,profile):
    root=Path(root)
    with (root/'profile-import.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if not link_valid(root,token): raise PermissionError('PROFILE_SETUP_UNAVAILABLE')
        count=validate_profile(profile)
        dest=root/'profile.json'
        if dest.exists():
            backup=root/('profile-before-import-'+str(time.time_ns())+'.json')
            shutil.copy2(dest,backup);backup.chmod(0o600)
        # Consume authorization before commit: a crash cannot enable replay.
        # If the write fails, the old profile remains and the operator issues a new link.
        (root/'profile-setup.json').unlink()
        atomic_json(dest,profile)
        return count


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',type=Path,required=True)
    print(issue_link(parser.parse_args().data_dir))
