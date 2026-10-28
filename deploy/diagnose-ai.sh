#!/usr/bin/env bash
# Diagnose the existing container without rebuilding, persisting keys or changes.
set -Eeuo pipefail
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
provider="${1:-openrouter}"
case "$provider" in openrouter|gateway) ;; *) echo 'Use openrouter ou gateway' >&2;exit 2;; esac
project="${JOBS_COMPOSE_PROJECT:-candidaturas-jobs}"
override="${JOBS_VPS_OVERRIDE:-$(dirname "$repo")/candidaturas.vps.json}"
cd "$repo"
worker="$(docker compose -p "$project" -f compose.yaml -f "$override" ps -q worker)"
[[ -n "$worker" ]] || { echo WORKER_NOT_FOUND >&2;exit 1; }
if [[ "$provider" == openrouter ]]; then key="${OPENROUTER_API_KEY:-}";else key="${AI_GATEWAY_API_KEY:-}";fi
if [[ -z "$key" ]]; then read -r -s -p "Cole somente a chave do $provider (entrada oculta): " key;printf '\n';fi
[[ -n "$key" ]] || { echo API_KEY_REQUIRED >&2;exit 1; }
export JOBS_SETUP_KEY="$key" JOBS_SETUP_PROVIDER="$provider"
unset key
python3 - <<'PY' | docker exec -i "$worker" python -c "$(cat "$repo/jobs_service/ai_diagnostics.py")"
import json,os,sys
json.dump({'provider':os.environ['JOBS_SETUP_PROVIDER'],'api_key':os.environ['JOBS_SETUP_KEY'].strip()},sys.stdout)
PY
unset JOBS_SETUP_KEY JOBS_SETUP_PROVIDER
