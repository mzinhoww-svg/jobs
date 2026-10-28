#!/usr/bin/env bash
# Issue a short-lived profile-upload link without placing private data in Git.
set -Eeuo pipefail
umask 077
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
base="${1:?Informe o endereco HTTPS do painel}"
python3 - "$base" <<'PY'
import sys
from urllib.parse import urlsplit
p=urlsplit(sys.argv[1])
assert p.scheme=='https' and p.hostname and not p.username and not p.password and p.path in ('','/') and not p.query and not p.fragment, 'INVALID_PUBLIC_URL'
PY
bash "$repo/deploy/update-ui.sh" --check
project="${JOBS_COMPOSE_PROJECT:-candidaturas-jobs}"
override="${JOBS_VPS_OVERRIDE:-$(dirname "$repo")/candidaturas.vps.json}"
cd "$repo"
api="$(docker compose -p "$project" -f compose.yaml -f "$override" ps -q api)"
[[ -n "$api" ]] || { echo API_NOT_FOUND >&2;exit 1; }
if ! docker exec "$api" python -c 'import jobs_service.profile_setup' >/dev/null 2>&1; then
  bash "$repo/deploy/update-ui.sh"
  api="$(docker compose -p "$project" -f compose.yaml -f "$override" ps -q api)"
fi
setup_token="$(docker exec "$api" python -m jobs_service.profile_setup --data-dir /var/lib/jobs)"
printf '\nAbra este link no navegador e selecione seu arquivo de perfil JSON:\n%s/profile-setup#%s\n' "${base%/}" "$setup_token"
printf 'O link expira em 15 minutos e funciona uma unica vez.\n'
