#!/usr/bin/env bash
# CI helper that runs alongside live_trade_v2.py inside the GitHub Actions job.
#
#  - every 20s: if a `trading-control` branch exists on the remote, touch data/STOP
#    (live_trade_v2.py sees it, squares off, and exits).
#  - every PUBLISH_EVERY seconds (and once more on exit): publish data/status.json
#    plus the static page to the `status` branch, served by GitHub Pages.
#
# Env: GITHUB_TOKEN, GITHUB_REPOSITORY (provided by the workflow)
set -u

PUBLISH_EVERY="${PUBLISH_EVERY:-360}"   # Pages soft limit is ~10 builds/hour
STATUS_FILE="data/status.json"
STOP_FILE="data/STOP"
REPO_URL="https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
ROOT="$(pwd)"

publish() {
  [ -f "$STATUS_FILE" ] || return 0
  local work
  work="$(mktemp -d)"
  cp "$STATUS_FILE" "$work/status.json"
  cp docs/status/index.html "$work/index.html"
  touch "$work/.nojekyll"
  (
    cd "$work" || exit 0
    git init -q
    git config user.name "trading-bot"
    git config user.email "trading-bot@users.noreply.github.com"
    git add -A
    git commit -q -m "status $(date -u +%FT%TZ)"
    git push -q --force "$REPO_URL" HEAD:refs/heads/status >/dev/null 2>&1 \
      || echo "[publisher] status push failed"
  )
  cd "$ROOT" || true
  rm -rf "$work"
}

check_stop() {
  if git ls-remote --exit-code --heads "$REPO_URL" trading-control >/dev/null 2>&1; then
    if [ ! -f "$STOP_FILE" ]; then
      echo "[publisher] stop requested (trading-control branch found)"
      mkdir -p data && touch "$STOP_FILE"
    fi
  fi
}

if [ "${1:-}" = "once" ]; then
  publish
  exit 0
fi

last_publish=0
while true; do
  check_stop
  now=$(date +%s)
  if [ $((now - last_publish)) -ge "$PUBLISH_EVERY" ]; then
    publish
    last_publish=$now
  fi
  sleep 20
done
