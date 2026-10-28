#!/usr/bin/env bash
# Operator-only setup. Never save AI credentials in the checkout or print them.
set -Eeuo pipefail
umask 077
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
provider="${1:-openrouter}"
case "$provider" in openrouter|gateway) ;; *) echo 'Use: bash deploy/configure-ai.sh [openrouter|gateway]' >&2;exit 2;; esac
bash "$repo/deploy/update-ui.sh"
project="${JOBS_COMPOSE_PROJECT:-candidaturas-jobs}"
override="${JOBS_VPS_OVERRIDE:-$(dirname "$repo")/candidaturas.vps.json}"
cd "$repo"
worker="$(docker compose -p "$project" -f compose.yaml -f "$override" ps -q worker)"
[[ -n "$worker" ]] || { echo WORKER_NOT_FOUND >&2; exit 1; }
if [[ "$provider" == openrouter ]]; then key="${OPENROUTER_API_KEY:-}";else key="${AI_GATEWAY_API_KEY:-}";fi
if [[ -z "$key" ]]; then
  read -r -s -p "Cole a chave de API do $provider (entrada oculta): " key
  printf '\n'
fi
[[ -n "$key" && "$key" != *$'\n'* ]] || { echo INVALID_API_KEY >&2;exit 1; }
export JOBS_SETUP_KEY="$key" JOBS_SETUP_PROVIDER="$provider"
unset key
# Send secret through stdin, never argv or Docker environment/config metadata.
python3 - <<'PY' | docker exec -i "$worker" python -c '
import asyncio,json,os,sys
from pathlib import Path
from jobs_service.intelligence import analyze_posting,DEFAULT_MODEL
from jobs_service.policy import Blocked
config=json.load(sys.stdin)
async def verify():
    source="Payments Lead at Fictional Labs. This is a synthetic job posting for a payments professional to lead payment partnerships and product operations in Brazil."
    facts=[{"id":"fixture","text":"Structured payment partnerships.","source":"synthetic test","confirmation":"confirmed","source_kind":"candidate_declaration","date":"2026-10-27"}]
    try: await analyze_posting(source,facts,config["api_key"],DEFAULT_MODEL,config["provider"])
    except Blocked as error:
        print("AI_SETUP_FAILED: "+error.code);raise SystemExit(1)
asyncio.run(verify())
path=Path("/var/lib/jobs/ai-config.json")
tmp=path.with_suffix(".pending")
fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,"w") as f: json.dump(config,f)
os.chmod(tmp,0o600);tmp.replace(path)
print("AI_CONFIGURED: chamada real validada; chave salva apenas no volume privado.")
'
import json,os
json.dump({'provider':os.environ['JOBS_SETUP_PROVIDER'],'api_key':os.environ['JOBS_SETUP_KEY'].strip(),'model':'deepseek/deepseek-v4.1-flash','enabled':True},__import__('sys').stdout)
PY
unset JOBS_SETUP_KEY JOBS_SETUP_PROVIDER
