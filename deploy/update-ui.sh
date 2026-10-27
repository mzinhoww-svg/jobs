#!/usr/bin/env bash
# Update only an existing candidaturas stack. Never prints or replaces its token.
set -Eeuo pipefail
umask 077
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
project="${JOBS_COMPOSE_PROJECT:-candidaturas-jobs}"
override="${JOBS_VPS_OVERRIDE:-$(dirname "$repo")/candidaturas.vps.json}"
alias_image=candidaturas-jobs:local
check_only=false
[[ ${1:-} != --check ]] || check_only=true
fail() { printf '%s\n' "$1" >&2; exit 1; }
[[ -f "$override" && ! -L "$override" ]] || fail VPS_OVERRIDE_MISSING
cd "$repo"
compose=(docker compose -p "$project" -f compose.yaml -f "$override")
"${compose[@]}" config --quiet
api_id="$("${compose[@]}" ps -q api)"
worker_id="$("${compose[@]}" ps -q worker)"
[[ -n "$api_id" && -n "$worker_id" ]] || fail EXISTING_STACK_NOT_FOUND
for cid in "$api_id" "$worker_id"; do
  [[ "$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$cid")" == "$repo" ]] || fail STACK_BELONGS_TO_ANOTHER_DIRECTORY
  [[ "$(docker inspect -f '{{.Config.Image}}' "$cid")" == "$alias_image" ]] || fail UNEXPECTED_STACK_IMAGE
done
volume_of() { docker inspect -f '{{range .Mounts}}{{if eq .Destination "/var/lib/jobs"}}{{.Name}}{{end}}{{end}}' "$1"; }
data_volume="$(volume_of "$api_id")"
[[ -n "$data_volume" && "$(volume_of "$worker_id")" == "$data_volume" ]] || fail PRIVATE_VOLUME_MISMATCH
[[ "$("${compose[@]}" config --images | sort -u)" == "$alias_image" ]] || fail UNEXPECTED_COMPOSE_IMAGES
# Refuse mount drift before touching either container; rollback uses this same config.
"${compose[@]}" config --format json | python3 -c '
import json,sys
config=json.load(sys.stdin)
expected=sys.argv[1]
for service in ("api","worker"):
    mounts=[v for v in config["services"][service].get("volumes",[]) if v.get("target")=="/var/lib/jobs"]
    assert len(mounts)==1 and mounts[0].get("type")=="volume", "PRIVATE_COMPOSE_VOLUME_MISMATCH"
    source=mounts[0]["source"]
    assert config.get("volumes",{}).get(source,{}).get("name")==expected, "PRIVATE_COMPOSE_VOLUME_MISMATCH"
' "$data_volume"
printf 'UPDATE_PREFLIGHT_OK: projeto e volume privados existentes preservados.\n'
$check_only && exit 0
exec 9>"${override}.update.lock"
flock -n 9 || fail ANOTHER_UPDATE_IS_RUNNING
old_image="$(docker inspect -f '{{.Image}}' "$api_id")"
stamp="ui-$(date -u +%Y%m%dT%H%M%SZ)"
rollback_tag="candidaturas-jobs:rollback-$stamp"
docker tag "$old_image" "$rollback_tag"
builder="${JOBS_BUILDER:-candidaturas-builder}"
builder_used=false
worker_stopped=false
activated=false
cleanup() {
  result=$?
  trap - EXIT
  set +e
  if (( result != 0 )); then
    if $activated; then
      printf 'Atualizacao interrompida; restaurando somente API e worker deste projeto.\n' >&2
      docker tag "$old_image" "$alias_image"
      "${compose[@]}" up -d --no-deps --force-recreate api worker
    elif $worker_stopped; then
      "${compose[@]}" start worker
    fi
  fi
  if $builder_used; then docker buildx stop "$builder" >/dev/null 2>&1; fi
  exit "$result"
}
trap cleanup EXIT
new_image="${JOBS_PREBUILT_IMAGE:-candidaturas-jobs:$stamp}"
if [[ -z ${JOBS_PREBUILT_IMAGE:-} ]]; then
  if ! docker buildx inspect "$builder" >/dev/null 2>&1; then
    docker buildx create --name "$builder" --driver docker-container \
      --driver-opt memory=768m,memory-swap=1024m,cpu-period=100000,cpu-quota=70000
  fi
  builder_used=true
  docker buildx build --builder "$builder" --load \
    --secret id=system_ca,src=/etc/ssl/certs/ca-certificates.crt -t "$new_image" .
  docker buildx stop "$builder"
else
  docker image inspect "$new_image" >/dev/null
fi
printf 'Validando nova imagem sem rede externa.\n'
docker run --rm --network none --memory=768m --memory-swap=1024m --cpus=0.70 \
  --shm-size=256m --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges \
  "$new_image" python -m unittest discover -s tests -v

# Pause only this worker. SQLite backup tolerates concurrent API reads/queue entry.
"${compose[@]}" stop -t 120 worker
worker_stopped=true
backup_volume="${project}_ui-backups"
if docker volume inspect "$backup_volume" >/dev/null 2>&1; then
  [[ "$(docker volume inspect -f '{{index .Labels "io.candidaturas.source"}}' "$backup_volume")" == "$repo" ]] || fail BACKUP_VOLUME_NOT_OWNED
else
  docker volume create --label "io.candidaturas.source=$repo" "$backup_volume" >/dev/null
fi
docker run --rm --network none --memory=192m --cpus=0.25 --cap-drop ALL --security-opt no-new-privileges \
  -v "$data_volume:/source" -v "$backup_volume:/var/lib/jobs" "$old_image" \
  python -m jobs_service.admin backup --data-dir /source --target "/var/lib/jobs/$stamp"

docker tag "$new_image" "$alias_image"
activated=true
"${compose[@]}" up -d --no-deps --force-recreate api worker
ready=false
for ((attempt=0; attempt<90; attempt++)); do
  api_id="$("${compose[@]}" ps -q api)"
  worker_id="$("${compose[@]}" ps -q worker)"
  if [[ -n "$api_id" && -n "$worker_id" ]]; then
    api_health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$api_id")"
    worker_health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$worker_id")"
    if [[ "$api_health" == healthy && "$worker_health" == healthy ]]; then ready=true; break; fi
  fi
  sleep 2
done
$ready || fail UPDATE_HEALTHCHECK_FAILED
[[ "$(volume_of "$api_id")" == "$data_volume" && "$(volume_of "$worker_id")" == "$data_volume" ]] || fail PRIVATE_VOLUME_CHANGED
docker exec -i "$api_id" python - <<'PY'
import http.client,json
from pathlib import Path
token=Path('/var/lib/jobs/api-token').read_text().strip()
c=http.client.HTTPConnection('127.0.0.1',8787,timeout=10)
c.request('GET','/system/status',headers={'Authorization':'Bearer '+token})
r=c.getresponse()
assert r.status==200, 'AUTHENTICATED_STATUS_FAILED'
assert json.loads(r.read())['version']=='0.2.0', 'UNEXPECTED_APP_VERSION'
c.close()
c=http.client.HTTPConnection('127.0.0.1',8787,timeout=10)
c.request('GET','/applications')
assert c.getresponse().status==401, 'AUTHENTICATION_WAS_DISABLED'
print('AUTH_OK: token atual preservado; acesso anonimo continua bloqueado.')
PY
activated=false
printf 'PAINEL_ATUALIZADO: salvar token, acompanhamento e historico disponiveis.\n'
printf 'Backup privado: volume %s, snapshot %s. Imagem anterior: %s.\n' "$backup_volume" "$stamp" "$rollback_tag"
printf 'Caddy, outros containers, Gmail, perfil e token nao foram alterados.\n'
