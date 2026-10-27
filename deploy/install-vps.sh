#!/usr/bin/env bash
# Installs only this project. Does not reconfigure SSH, firewall, Docker or HTTPS.
set -Eeuo pipefail
umask 077

root="${JOBS_INSTALL_ROOT:-/opt/candidaturas-cloud}"
port="${JOBS_HTTP_PORT:-8787}"
project=candidaturas-jobs
source_url=https://github.com/mzinhoww-svg/jobs.git
check_only=false
if [[ "${1:-}" == --check && $# -eq 1 ]]; then
  check_only=true
elif [[ $# -ne 0 ]]; then
  printf 'Uso: bash install-vps.sh [--check]\n' >&2
  exit 2
fi

fail() { printf '%s\n' "$1" >&2; exit 1; }
[[ "$root" == /* && "$root" != / && "$root" != /opt && "$root" != /srv ]] || fail INVALID_INSTALL_ROOT
[[ "$(readlink -m -- "$root")" == "$root" ]] || fail INSTALL_ROOT_NOT_CANONICAL
[[ "$port" =~ ^[0-9]{1,5}$ ]] || fail INVALID_PORT
(( 10#$port >= 1024 && 10#$port <= 65535 )) || fail INVALID_PORT
[[ ! -L "$root" ]] || fail INSTALL_ROOT_IS_SYMLINK
# Only root/current-user-owned parents, with no group/world writable ancestors
# except root-owned sticky directories such as /tmp used by preflight tests.
fs_root_owner="$(stat -c %u /)"
parent="$root"
while [[ ! -e "$parent" ]]; do parent="$(dirname "$parent")"; done
while :; do
  owner="$(stat -c %u -- "$parent")"
  mode="$(stat -c %a -- "$parent")"
  [[ "$owner" == "$fs_root_owner" || "$owner" == "$(id -u)" ]] || fail UNTRUSTED_INSTALL_PARENT
  if (( (8#$mode & 0022) != 0 )); then
    [[ "$owner" == "$fs_root_owner" ]] && (( (8#$mode & 01000) != 0 )) || fail WRITABLE_INSTALL_PARENT
  fi
  [[ "$parent" == / ]] && break
  parent="$(dirname "$parent")"
done
if [[ -e "$root" ]]; then
  [[ -d "$root" && -f "$root/INSTALLATION_OWNER" && ! -L "$root/INSTALLATION_OWNER" ]] || fail EXISTING_DIRECTORY_NOT_OWNED
  [[ "$(cat "$root/INSTALLATION_OWNER")" == mzinhoww-svg/jobs ]] || fail EXISTING_DIRECTORY_NOT_OWNED
fi

command -v docker >/dev/null || fail DOCKER_MISSING
docker info >/dev/null 2>&1 || fail DOCKER_UNAVAILABLE
existing_containers="$(docker ps -aq --filter "label=com.docker.compose.project=$project")"
existing_volumes="$(docker volume ls -q --filter "label=com.docker.compose.project=$project")"
existing_networks="$(docker network ls -q --filter "label=com.docker.compose.project=$project")"
if [[ -n "$existing_containers$existing_volumes$existing_networks" ]]; then
  [[ -f "$root/INSTALLATION_OWNER" ]] || fail PROJECT_ALREADY_EXISTS
  for resource in $existing_containers; do
    working_dir="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$resource")"
    [[ "$working_dir" == "$root/app" ]] || fail PROJECT_ROOT_MISMATCH
  done
  for resource in $existing_volumes; do
    resource_root="$(docker volume inspect -f '{{ index .Labels "io.candidaturas.install-root" }}' "$resource")"
    [[ "$resource_root" == "$root" ]] || fail PROJECT_VOLUME_ROOT_MISMATCH
  done
  for resource in $existing_networks; do
    resource_root="$(docker network inspect -f '{{ index .Labels "io.candidaturas.install-root" }}' "$resource")"
    [[ "$resource_root" == "$root" ]] || fail PROJECT_NETWORK_ROOT_MISMATCH
  done
fi

# Reject an occupied port before creating files or installing anything.
if timeout 2 bash -c 'exec 3<>"/dev/tcp/127.0.0.1/$1"' _ "$port" 2>/dev/null; then
  owned=''
  for resource in $existing_containers; do
    service="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.service" }}' "$resource")"
    if [[ "$service" == api ]]; then
      bindings="$(docker inspect -f '{{range (index .NetworkSettings.Ports "8787/tcp")}}{{.HostIp}} {{.HostPort}}{{println}}{{end}}' "$resource")"
      if grep -Fxq "127.0.0.1 $port" <<< "$bindings"; then owned="$resource"; fi
    fi
  done
  [[ -n "$owned" ]] || fail "PORT_IN_USE: $port; nenhum servico existente foi alterado."
fi

docker compose version >/dev/null 2>&1 || fail DOCKER_COMPOSE_MISSING
docker buildx version >/dev/null 2>&1 || fail DOCKER_BUILDX_MISSING
for required in curl df awk timeout flock sha256sum; do
  command -v "$required" >/dev/null || fail "REQUIRED_COMMAND_MISSING: $required"
done
[[ -r /etc/ssl/certs/ca-certificates.crt ]] || fail SYSTEM_CA_MISSING
probe="$root"
while [[ ! -d "$probe" ]]; do probe="$(dirname "$probe")"; done
free_kb="$(df -Pk "$probe" | awk 'NR==2 {print $4}')"
(( free_kb >= 8*1024*1024 )) || fail NEED_8GB_FREE_DISK
available_mb="$(awk '/^MemAvailable:/ {print int($2/1024)}' /proc/meminfo)"
(( available_mb >= 384 )) || fail NEED_384MB_AVAILABLE_RAM
printf 'PREFLIGHT_OK: Docker/Compose, porta %s, disco e memoria verificados.\n' "$port"
if $check_only; then exit 0; fi
[[ $(id -u) -eq 0 ]] || fail RUN_AS_ROOT

if ! command -v git >/dev/null; then
  command -v apt-get >/dev/null || fail GIT_MISSING
  apt-get update
  apt-get install -y --no-install-recommends git
fi

if [[ ! -e "$root" ]]; then
  install -d -m 0750 "$root"
  printf 'mzinhoww-svg/jobs\n' > "$root/INSTALLATION_OWNER"
fi
exec 9>"$root/installer.lock"
flock -n 9 || fail ANOTHER_INSTALLER_IS_RUNNING
[[ ! -L "$root/app" ]] || fail APP_DIRECTORY_IS_SYMLINK
if [[ -e "$root/app" ]]; then
  [[ -d "$root/app/.git" ]] || fail EXISTING_APP_IS_NOT_CHECKOUT
  [[ -z "$(git -C "$root/app" status --porcelain)" ]] || fail APP_HAS_LOCAL_CHANGES
  remote="$(git -C "$root/app" remote get-url origin)"
  [[ "$remote" == "$source_url" || "$remote" == "${source_url%.git}" ]] || fail UNEXPECTED_ORIGIN
  git -C "$root/app" fetch origin main
  git -C "$root/app" merge --ff-only FETCH_HEAD
else
  git clone --depth 1 --branch main "$source_url" "$root/app"
fi
cd "$root/app"
export JOBS_HTTP_PORT="$port"
export JOBS_INSTALL_ROOT="$root"
export JOBS_IMAGE_TAG="$(git rev-parse --short=12 HEAD)"
compose=(docker compose -p "$project" -f compose.yaml -f deploy/compose.vps.yaml)
"${compose[@]}" config --quiet

printf 'Construindo imagem isolada; pode levar varios minutos nesta VPS.\n'
builder="candidaturas-$(printf '%s' "$root" | sha256sum | cut -c1-12)"
if ! docker buildx inspect "$builder" >/dev/null 2>&1; then
  docker buildx create --name "$builder" --driver docker-container \
    --driver-opt memory=768m,memory-swap=1024m,cpu-quota=70000,cpu-period=100000
fi
trap 'docker buildx stop "$builder" >/dev/null 2>&1 || true' EXIT
docker buildx build --builder "$builder" --load --secret id=system_ca,src=/etc/ssl/certs/ca-certificates.crt \
  -t "candidaturas-jobs:$JOBS_IMAGE_TAG" .
docker buildx stop "$builder"
printf 'Executando testes controlados, sem rede externa.\n'
docker run --rm --network none --shm-size=256m --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges \
  --memory=768m --memory-swap=1024m --cpus=0.70 \
  "candidaturas-jobs:$JOBS_IMAGE_TAG" python -m unittest discover -s tests -v
"${compose[@]}" up -d
ready=false
for ((attempt=0; attempt<90; attempt++)); do
  if curl --fail --silent --max-time 3 "http://127.0.0.1:$port/healthz" >/dev/null; then ready=true; break; fi
  sleep 2
done
$ready || fail API_HEALTHCHECK_FAILED
worker_ready=false
for ((attempt=0; attempt<90; attempt++)); do
  worker_id="$("${compose[@]}" ps -q worker)"
  if [[ -n "$worker_id" ]]; then
    health="$(docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' "$worker_id")"
    if [[ "$health" == 'running healthy' ]]; then worker_ready=true; break; fi
  fi
  sleep 2
done
$worker_ready || fail WORKER_HEALTHCHECK_FAILED
init_id="$("${compose[@]}" ps -aq init)"
[[ -n "$init_id" && "$(docker inspect -f '{{.State.ExitCode}}' "$init_id")" == 0 ]] || fail STORAGE_INIT_FAILED
status="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 5 "http://127.0.0.1:$port/applications")"
[[ "$status" == 401 ]] || fail AUTHENTICATION_CHECK_FAILED
"${compose[@]}" ps
printf '\nBACKEND_INSTALADO: projeto %s; API em loopback, porta %s.\n' "$project" "$port"
printf 'Os outros containers, as portas 80/443, o proxy e o firewall foram preservados.\n'
printf 'Ainda faltam: perfil privado, OAuth Gmail e rota HTTPS no proxy existente.\n'
printf 'Nao foi enviada candidatura real. O backend ainda nao e declarado operacional em producao.\n'
