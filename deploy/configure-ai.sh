#!/usr/bin/env bash
# Operator-only setup. Never save AI credentials in the checkout or print them.
set -Eeuo pipefail
umask 077
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
provider="${1:-openrouter}"
case "$provider" in openrouter|gateway) ;; *) echo 'Use: bash deploy/configure-ai.sh [openrouter|gateway]' >&2;exit 2;; esac
bash "$repo/deploy/update-ui.sh" --check
project="${JOBS_COMPOSE_PROJECT:-candidaturas-jobs}"
override="${JOBS_VPS_OVERRIDE:-$(dirname "$repo")/candidaturas.vps.json}"
cd "$repo"
worker="$(docker compose -p "$project" -f compose.yaml -f "$override" ps -q worker)"
[[ -n "$worker" ]] || { echo WORKER_NOT_FOUND >&2; exit 1; }
# Existing 0.3 containers can run the updated setup from stdin/argv directly.
# Avoid rebuilding and rerunning the whole suite for each credential attempt.
if ! docker exec "$worker" python -c 'import jobs_service.intelligence' >/dev/null 2>&1; then
  bash "$repo/deploy/update-ui.sh"
  worker="$(docker compose -p "$project" -f compose.yaml -f "$override" ps -q worker)"
fi
if [[ "$provider" == openrouter ]]; then key="${OPENROUTER_API_KEY:-}";else key="${AI_GATEWAY_API_KEY:-}";fi
if [[ -z "$key" ]]; then
  read -r -s -p "Cole a chave de API do $provider (entrada oculta): " key
  printf '\n'
fi
[[ -n "$key" && "$key" != *$'\n'* ]] || { echo INVALID_API_KEY >&2;exit 1; }
export JOBS_SETUP_KEY="$key" JOBS_SETUP_PROVIDER="$provider"
unset key
# Send secret through stdin, never argv or Docker environment/config metadata.
python3 - <<'PY' | docker exec -i "$worker" python -c "$(cat "$repo/jobs_service/ai_setup.py")"
import json,os
json.dump({'provider':os.environ['JOBS_SETUP_PROVIDER'],'api_key':os.environ['JOBS_SETUP_KEY'].strip(),'model':'deepseek/deepseek-v4.1-flash','enabled':True},__import__('sys').stdout)
PY
unset JOBS_SETUP_KEY JOBS_SETUP_PROVIDER
