#!/usr/bin/env bash
# Build the API/worker image on THIS machine for the VM's CPU, copy it over SSH, and
# (re)start HireLens on the VM. Run from the repository root:
#
#   SSH_KEY=~/.ssh/hirelens-vm.key bash deploy/micro/ship.sh ubuntu@<VM_PUBLIC_IP>
#
# Needs: Docker with buildx (Docker Desktop has it), and deploy/production.env filled in.
set -euo pipefail

HOST="${1:?usage: bash deploy/micro/ship.sh ubuntu@<vm-ip>}"
cd "$(git rev-parse --show-toplevel)"
ENV_FILE=deploy/production.env
[ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE (copy deploy/production.env.example)" >&2; exit 1; }
API_DOMAIN="$(grep -E '^API_DOMAIN=' "$ENV_FILE" | cut -d= -f2- | tr -d '"')"
[ -n "$API_DOMAIN" ] || { echo "Set API_DOMAIN in $ENV_FILE" >&2; exit 1; }
if [ -n "$(git status --porcelain -- apps packages package.json package-lock.json)" ]; then
  echo "Commit or stash app changes first, so the image matches APP_REVISION." >&2; exit 1
fi
APP_REVISION="$(git rev-parse --short HEAD)"
SSH=(ssh -o StrictHostKeyChecking=accept-new ${SSH_KEY:+-i "$SSH_KEY"})
SCP=(scp -q -o StrictHostKeyChecking=accept-new ${SSH_KEY:+-i "$SSH_KEY"})
PLATFORM="${PLATFORM:-linux/amd64}"   # E2.1.Micro is AMD; use linux/arm64 for an A1 VM

echo "Building hirelens-api:$APP_REVISION for $PLATFORM (slow the first time on Apple Silicon)..."
docker buildx build --platform "$PLATFORM" -f apps/api/Dockerfile --target runtime \
  -t "hirelens-api:$APP_REVISION" --load .

echo "Copying the image to $HOST..."
docker save "hirelens-api:$APP_REVISION" | gzip -1 | "${SSH[@]}" "$HOST" 'gunzip | docker load'

echo "Copying configuration..."
"${SSH[@]}" "$HOST" 'mkdir -p ~/hirelens && umask 077 && touch ~/hirelens/production.env'
"${SCP[@]}" deploy/micro/docker-compose.yml deploy/Caddyfile "$HOST:hirelens/"
"${SCP[@]}" "$ENV_FILE" "$HOST:hirelens/production.env"

echo "Starting HireLens $APP_REVISION..."
"${SSH[@]}" "$HOST" "set -e; cd ~/hirelens; chmod 600 production.env
  # Compose reads .env for \${APP_REVISION} and \${API_DOMAIN}, so later 'docker compose logs' etc. work too.
  printf 'APP_REVISION=%s\nAPI_DOMAIN=%s\n' $APP_REVISION $API_DOMAIN > .env
  docker compose up -d --remove-orphans
  # Keep only the image just deployed; old revisions would slowly fill the 47 GB disk.
  docker images hirelens-api --format '{{.Tag}}' | { grep -vx $APP_REVISION || true; } \
    | xargs -r -I{} docker rmi -f hirelens-api:{} >/dev/null
  docker image prune -f >/dev/null
  docker compose ps"

echo
echo "Deployed $APP_REVISION. Check: curl https://$API_DOMAIN/ready"
