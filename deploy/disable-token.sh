#!/usr/bin/env bash
# Explicit operator opt-in: this makes the application's data and queue public.
set -Eeuo pipefail
umask 077
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
override="${JOBS_VPS_OVERRIDE:-$(dirname "$repo")/candidaturas.vps.json}"
project="${JOBS_COMPOSE_PROJECT:-candidaturas-jobs}"
JOBS_VPS_OVERRIDE="$override" bash "$repo/deploy/update-ui.sh" --check
backup="$(mktemp "${override}.before-public.XXXXXX")"
cp -p -- "$override" "$backup"
restore_config() {
  result=$?
  trap - EXIT
  if (( result != 0 )); then
    set +e
    cp -p -- "$backup" "$override"
    docker compose --project-directory "$repo" -p "$project" -f "$repo/compose.yaml" -f "$override" up -d --no-deps --force-recreate api
    printf 'Falha: configuracao anterior restaurada em disco e recriacao da API solicitada. Confira a saude do projeto antes de continuar.\n' >&2
  fi
  exit "$result"
}
trap restore_config EXIT
python3 - "$override" <<'PY'
import json,os,sys,tempfile
from pathlib import Path
p=Path(sys.argv[1]); data=json.loads(p.read_text())
api=data.setdefault('services',{}).setdefault('api',{})
env=api.get('environment') or {}
if isinstance(env,list):
    env=dict(item.split('=',1) if '=' in item else (item,None) for item in env)
env['JOBS_AUTH_MODE']='none'
api['environment']=env
fd,name=tempfile.mkstemp(prefix=p.name+'.',dir=p.parent)
try:
    with os.fdopen(fd,'w') as f: json.dump(data,f); f.write('\n')
    os.replace(name,p)
finally:
    if os.path.exists(name): os.unlink(name)
PY
JOBS_VPS_OVERRIDE="$override" bash "$repo/deploy/update-ui.sh"
cd "$repo"
api_id="$(docker compose -p "$project" -f compose.yaml -f "$override" ps -q api)"
docker exec "$api_id" python -c "import json,urllib.request; b='http://127.0.0.1:8787'; assert json.load(urllib.request.urlopen(b+'/auth/config'))=={'required':False}; assert urllib.request.urlopen(b+'/applications').status==200"
printf 'ACESSO_SEM_TOKEN_ATIVADO. Qualquer pessoa com o endereco pode acessar dados e adicionar vagas.\n'
printf 'Configuracao anterior preservada em: %s\n' "$backup"
