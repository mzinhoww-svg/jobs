#!/usr/bin/env bash
# Import an operator-provided private profile into an existing volume, never Git.
set -Eeuo pipefail
umask 077
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
source_file="${1:?Informe o caminho absoluto do perfil JSON privado, fora do checkout}"
source_file="$(readlink -f -- "$source_file")"
[[ -f "$source_file" && "$source_file" != "$repo/"* ]] || { echo PROFILE_MUST_BE_OUTSIDE_CHECKOUT >&2; exit 1; }
chmod 600 "$source_file"
project="${JOBS_COMPOSE_PROJECT:-candidaturas-jobs}"
override="${JOBS_VPS_OVERRIDE:-$(dirname "$repo")/candidaturas.vps.json}"
cd "$repo"
api="$(docker compose -p "$project" -f compose.yaml -f "$override" ps -q api)"
[[ -n "$api" ]] || { echo API_NOT_FOUND >&2;exit 1; }
docker exec -i "$api" python -c '
import fcntl,json,os,shutil,sys,tempfile,time
from pathlib import Path
from jobs_service.policy import verified_fact
profile=json.load(sys.stdin)
assert profile.get("identity",{}).get("full_name") and profile["identity"].get("preferred_email"), "PROFILE_IDENTITY_MISSING"
assert any(verified_fact(f) for f in profile.get("facts",[])), "CONFIRMED_FACTS_MISSING"
root=Path("/var/lib/jobs");dest=root/"profile.json"
with (root/"profile-import.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if dest.exists():
        backup=root/("profile-before-import-"+str(time.time_ns())+".json")
        shutil.copy2(dest,backup);backup.chmod(0o600)
    fd,name=tempfile.mkstemp(prefix="profile-import-",dir=root)
    try:
        with os.fdopen(fd,"w") as f: json.dump(profile,f,ensure_ascii=False,indent=2)
        os.chmod(name,0o600);os.replace(name,dest)
    finally:
        if os.path.exists(name): os.unlink(name)
print("PRIVATE_PROFILE_IMPORTED: perfil salvo no volume privado; proxima tarefa usa os dados novos.")
' < "$source_file"
