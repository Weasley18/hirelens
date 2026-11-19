#!/usr/bin/env bash
# Build, migrate and (re)start HireLens on this VM from the current checkout. Run ON the VM,
# from the repository root, for the first deploy and every update:
#   git pull && bash deploy/update.sh
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
for file in deploy/production.env deploy/ml.env; do
  [ -f "$file" ] || { echo "Missing $file (copy $file.example and fill it in)" >&2; exit 1; }
done
chmod 600 deploy/production.env deploy/ml.env

APP_REVISION="$(git rev-parse --short HEAD)"
API_DOMAIN="$(grep -E '^API_DOMAIN=' deploy/production.env | cut -d= -f2- | tr -d '"')"
[ -n "$API_DOMAIN" ] || { echo "Set API_DOMAIN in deploy/production.env" >&2; exit 1; }
export APP_REVISION API_DOMAIN
compose=(docker compose -f deploy/docker-compose.prod.yml --env-file deploy/production.env)

# POSTGRES_PASSWORD set: run Postgres on this VM (deploy/docker-compose.db.yml). Otherwise
# DATABASE_URL points at a managed database.
POSTGRES_PASSWORD="$(grep -E '^POSTGRES_PASSWORD=' deploy/production.env | cut -d= -f2- | tr -d '"' || true)"
if [ -n "$POSTGRES_PASSWORD" ]; then
  [[ "$POSTGRES_PASSWORD" =~ ^[A-Za-z0-9]{24,}$ ]] || {
    echo "POSTGRES_PASSWORD must be 24+ letters/digits (it goes inside a URL): openssl rand -hex 24" >&2; exit 1; }
  compose+=(-f deploy/docker-compose.db.yml)
  mkdir -p deploy/backups
  echo "Database: Postgres on this VM"
else
  echo "Database: DATABASE_URL from production.env"
fi

echo "Building $APP_REVISION (the first build takes several minutes)..."
"${compose[@]}" build
"${compose[@]}" --profile release build migrate

echo "Applying database migrations..."
"${compose[@]}" run --rm migrate

echo "Loading the knowledge base..."
"${compose[@]}" run --rm --no-deps ml python -m rag.ingest

echo "Starting..."
"${compose[@]}" up -d --remove-orphans
docker image prune -f >/dev/null
"${compose[@]}" ps
echo
echo "Deployed $APP_REVISION. Check: curl https://$API_DOMAIN/ready"
