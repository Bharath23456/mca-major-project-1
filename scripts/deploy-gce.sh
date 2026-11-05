#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIRECTORY="${1:?Application directory is required}"
NEW_IMAGE="${2:?New image URI is required}"
REGISTRY_HOST="${3:?Artifact Registry host is required}"
DEPLOYMENT_ID="${4:?Deployment commit SHA is required}"

if [[ ! "$APP_DIRECTORY" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
  echo "APP_DIRECTORY must be an absolute path without spaces." >&2
  exit 2
fi
if [[ ! "$NEW_IMAGE" =~ ^[a-z0-9-]+-docker\.pkg\.dev/[a-z0-9][a-z0-9-]*/[a-z][a-z0-9_-]*/[a-z0-9][a-z0-9._-]*:[0-9a-f]{40}$ ]]; then
  echo "The image URI is not a valid commit-SHA Artifact Registry image URI." >&2
  exit 2
fi
if [[ ! "$REGISTRY_HOST" =~ ^[a-z0-9-]+-docker\.pkg\.dev$ || ! "$DEPLOYMENT_ID" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Invalid registry host or deployment SHA." >&2
  exit 2
fi

REMOTE_SCRIPT="$0"
trap 'rm -f -- "$REMOTE_SCRIPT"' EXIT

if [[ ! -f "$APP_DIRECTORY/docker-compose.yml" ]]; then
  echo "Compose file not found at $APP_DIRECTORY/docker-compose.yml" >&2
  exit 1
fi

cd "$APP_DIRECTORY"
COMPOSE_FILE="$APP_DIRECTORY/docker-compose.yml"
OVERRIDE_FILE="$(mktemp)"
printf 'services: {}\n' > "$OVERRIDE_FILE"
trap 'rm -f -- "$REMOTE_SCRIPT" "$OVERRIDE_FILE"' EXIT
ROLLBACK_IMAGE="cloudnetops-rollback:${DEPLOYMENT_ID}"
DEPLOY_STARTED=0

compose() {
  docker compose \
    --project-directory "$APP_DIRECTORY" \
    -f "$COMPOSE_FILE" \
    -f "$OVERRIDE_FILE" \
    "$@"
}

write_override() {
  printf 'services:\n  app:\n    image: "%s"\n' "$1" > "$OVERRIDE_FILE"
}

wait_until_ready() {
  local container_id state health port_mapping host_port attempt

  port_mapping="$(compose port app 8000)"
  host_port="${port_mapping##*:}"
  if [[ -z "$host_port" || "$host_port" == "$port_mapping" ]]; then
    echo "Could not determine the published application port." >&2
    return 1
  fi

  for attempt in $(seq 1 60); do
    container_id="$(compose ps -q app)"
    if [[ -n "$container_id" ]]; then
      state="$(docker inspect --format '{{.State.Status}}' "$container_id")"
      health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$container_id")"
      if [[ "$state" == "running" && "$health" == "healthy" ]] \
        && curl --fail --silent --show-error --max-time 5 \
          "http://127.0.0.1:${host_port}/health/ready" > /dev/null; then
        echo "Compose app is running and /health/ready returned HTTP success."
        return 0
      fi
    fi
    sleep 5
  done

  echo "Application did not become healthy within 5 minutes." >&2
  return 1
}

on_error() {
  local exit_code=$?
  trap - ERR
  set +e

  echo "Deployment failed with exit code $exit_code. Current app status and logs:" >&2
  compose ps -a app >&2
  compose logs --no-color --tail=100 app >&2

  if [[ "$DEPLOY_STARTED" == "1" ]]; then
    echo "Attempting rollback to $ROLLBACK_IMAGE." >&2
    write_override "$ROLLBACK_IMAGE"
    if compose up --no-build --pull never --detach --no-deps app; then
      if wait_until_ready; then
        echo "Rollback restored the previous app image and readiness is healthy." >&2
      else
        echo "Rollback started, but readiness verification also failed." >&2
        compose ps -a app >&2
        compose logs --no-color --tail=100 app >&2
      fi
    else
      echo "Rollback could not restart the previous app image." >&2
      compose ps -a app >&2
      compose logs --no-color --tail=100 app >&2
    fi
  else
    echo "The app was not changed; rollback was not needed." >&2
  fi

  exit "$exit_code"
}
trap on_error ERR

container_id="$(compose ps -q app)"
if [[ -z "$container_id" ]]; then
  echo "No existing Compose app container was found; refusing an unbacked first deployment." >&2
  exit 1
fi

previous_image_id="$(docker inspect --format '{{.Image}}' "$container_id")"
if [[ -z "$previous_image_id" ]]; then
  echo "Could not determine the currently deployed app image." >&2
  exit 1
fi

docker image tag "$previous_image_id" "$ROLLBACK_IMAGE"
gcloud auth configure-docker "$REGISTRY_HOST" --quiet
write_override "$NEW_IMAGE"
compose pull app

DEPLOY_STARTED=1
compose up --no-build --pull never --detach --no-deps app
wait_until_ready

echo "Deployment succeeded: $NEW_IMAGE"
echo "Previous app image retained locally as $ROLLBACK_IMAGE."
