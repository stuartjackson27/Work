#!/usr/bin/env bash
# Config Check: one-shot deploy onto a fresh VM.
# Supported: Ubuntu 22.04/24.04 (Debian family) and AlmaLinux / Rocky / RHEL 9-10 (RHEL family).
#
#   curl/scp this script to the VM, then:
#     sudo REPO_URL=git@github.com:stuartjackson27/config-check.git \
#          DEPLOY_KEY=/root/.ssh/gh_deploy \
#          OLLAMA_URL=http://192.168.1.232:11434 \
#          BACKUP_DIR=/mnt/backup \
#          bash deploy.sh
#
# Idempotent: safe to re-run (it pulls the latest code and restarts the stack).
#
# Env vars (all optional except REPO_URL when the repo isn't already in place):
#   REPO_URL     git URL of the repo (https for public, git@ with DEPLOY_KEY for private)
#   REPO_REF     branch/tag to deploy (default: main)
#   DEPLOY_KEY   path to a read-only GitHub deploy key for a private repo
#   APP_DIR      install dir (default: /opt/config-check)
#   APP_USER     owner of the install (default: the sudo user, else root)
#   OLLAMA_URL   writes llm.base_url in config/settings.yaml
#   OLLAMA_MODEL writes llm.model in config/settings.yaml
#   BACKUP_DIR   if set, a nightly tarball of data/config/knowledge goes here (keeps 14)
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/config-check}
REPO_REF=${REPO_REF:-main}
APP_USER=${APP_USER:-${SUDO_USER:-root}}
log() { printf '\n\033[1;36m>> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run as root (sudo)"
. /etc/os-release
case " ${ID} ${ID_LIKE:-} " in
  *" ubuntu "*|*" debian "*)                         OS=debian ;;
  *" rhel "*|*" centos "*|*" fedora "*|*" almalinux "*|*" rocky "*) OS=rhel ;;
  *) die "unsupported OS: ${PRETTY_NAME:-$ID} (Ubuntu/Debian or Alma/Rocky/RHEL)" ;;
esac
echo "   OS: ${PRETTY_NAME} -> ${OS} family"
id "$APP_USER" >/dev/null 2>&1 || die "user $APP_USER does not exist (set APP_USER)"

log "1/7 Packages"
if [ "$OS" = debian ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq git curl ca-certificates python3 python3-yaml qemu-guest-agent cron >/dev/null
else
  dnf -y -q install git curl ca-certificates python3 python3-pyyaml qemu-guest-agent cronie \
      dnf-plugins-core policycoreutils-python-utils >/dev/null
  systemctl enable --now crond >/dev/null 2>&1 || true
fi
systemctl enable --now qemu-guest-agent >/dev/null 2>&1 || true

log "2/7 Docker"
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  if [ "$OS" = debian ]; then
    curl -fsSL https://get.docker.com | sh >/dev/null
  else
    # RHEL family ships Podman; Docker CE conflicts with podman-docker/buildah/runc (Docker install docs)
    dnf -y -q remove docker docker-client docker-client-latest docker-common docker-latest \
        docker-latest-logrotate docker-logrotate docker-engine podman-docker podman buildah runc >/dev/null 2>&1 || true
    # Docker publishes Alma/Rocky/CentOS packages under /centos, real RHEL under /rhel
    repo=centos; [ "${ID}" = "rhel" ] && repo=rhel
    dnf config-manager --add-repo "https://download.docker.com/linux/${repo}/docker-ce.repo" >/dev/null
    dnf -y -q install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null \
      || die "Docker CE install failed - check that download.docker.com has packages for ${PRETTY_NAME}"
  fi
fi
systemctl enable --now docker >/dev/null
docker compose version | sed 's/^/   /'

if [ "$OS" = rhel ]; then
  if systemctl is-active -q firewalld; then
    firewall-cmd -q --permanent --add-port=8080/tcp && firewall-cmd -q --reload
    echo "   firewalld: opened 8080/tcp"
  fi
  echo "   SELinux: $(getenforce 2>/dev/null || echo n/a)"
fi
usermod -aG docker "$APP_USER"

log "3/7 Code -> $APP_DIR ($REPO_REF)"
if [ -n "${DEPLOY_KEY:-}" ]; then
  [ -f "$DEPLOY_KEY" ] || die "DEPLOY_KEY $DEPLOY_KEY not found"
  chmod 600 "$DEPLOY_KEY"
  export GIT_SSH_COMMAND="ssh -i $DEPLOY_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
fi
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch -q origin "$REPO_REF"
  git -C "$APP_DIR" checkout -q "$REPO_REF"
  git -C "$APP_DIR" pull -q --ff-only origin "$REPO_REF"
elif [ -f "$APP_DIR/docker-compose.yml" ]; then
  log "   $APP_DIR already has the code (not a git checkout) - using it as is"
else
  [ -n "${REPO_URL:-}" ] || die "set REPO_URL (or copy the repo to $APP_DIR first)"
  mkdir -p "$(dirname "$APP_DIR")"
  git clone -q --branch "$REPO_REF" "$REPO_URL" "$APP_DIR"
fi
chown -R "$APP_USER": "$APP_DIR"
if [ "$OS" = rhel ] && [ "$(getenforce 2>/dev/null)" = Enforcing ]; then
  sed -i -E 's#^(\s+- \./[^ ]+:ro)$#\1,z#; s#^(\s+- \./data:[^ :]+)$#\1:z#' "$APP_DIR/docker-compose.yml"
  echo "   SELinux Enforcing: added :z labels to the docker-compose.yml volumes"
fi

log "4/7 Settings"
S="$APP_DIR/config/settings.yaml"
if [ -n "${OLLAMA_URL:-}" ]; then
  sed -i -E "s#^(  base_url: ).*#\1${OLLAMA_URL}#" "$S"
fi
if [ -n "${OLLAMA_MODEL:-}" ]; then
  sed -i -E "s#^(  model: )[^ ]+#\1${OLLAMA_MODEL}#" "$S"
fi
grep -E "^  (base_url|model):" "$S" | sed 's/^/   /'
OURL=$(grep -E "^  base_url:" "$S" | awk '{print $2}')
if curl -fsS -m 5 "$OURL/api/tags" >/dev/null 2>&1; then
  echo "   Ollama reachable at $OURL"
else
  echo "   WARNING: Ollama not reachable at $OURL - rules will run, LLM review will be skipped until it is"
fi

log "5/7 Secrets, MCP server, token, containers (scripts/setup.sh)"
cd "$APP_DIR"
bash scripts/setup.sh

log "6/7 Health check"
for i in $(seq 1 30); do
  curl -fsS -m 3 localhost:8080/api/state >/dev/null 2>&1 && { echo "   dashboard up"; break; }
  [ "$i" -eq 30 ] && { docker compose ps; die "dashboard did not come up - see: docker compose logs"; }
  sleep 4
done
docker compose ps --format '   {{.Name}}  {{.Status}}'

log "7/7 Backups"
if [ -n "${BACKUP_DIR:-}" ]; then
  mkdir -p "$BACKUP_DIR"
  cat > /etc/cron.d/config-check-backup <<EOF
# Nightly Config Check backup (scan history, config backups, settings, knowledge). Keeps 14.
0 2 * * * root tar czf ${BACKUP_DIR}/config-check-\$(date +\%F).tgz -C ${APP_DIR} data config knowledge && ls -1t ${BACKUP_DIR}/config-check-*.tgz | tail -n +15 | xargs -r rm -f
EOF
  echo "   nightly backup -> $BACKUP_DIR (02:00, keeps 14)"
else
  echo "   BACKUP_DIR not set - no backup job. Strongly recommended: data/ is your scan history."
fi

IP=$(hostname -I | awk '{print $1}')
cat <<EOF

$(printf '\033[1;32m')Config Check is running: http://${IP}:8080$(printf '\033[0m')

Next: give every switch the new read-only key (the old one died with the old VM):

  set system login user configcheck authentication ssh-ed25519 "$(cat "$APP_DIR/secrets/configcheck_ed25519.pub")"

Then press "Run scan" on the dashboard.
EOF
