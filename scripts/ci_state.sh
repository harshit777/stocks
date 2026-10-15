#!/usr/bin/env bash
# Persist paper-trading state between GitHub Actions runs on a `paper-data` branch.
#
#   ci_state.sh restore   copy state from the branch into ./data (first run: no-op)
#   ci_state.sh save      commit ./data state to the branch
#
# State = reports + capital history (data/paper), trained models (data/ml),
# pattern/sentiment models (data/ai_data). Never includes .env or secrets.
# Env: GITHUB_TOKEN, GITHUB_REPOSITORY
set -eu

BRANCH="paper-data"
DIRS="data/paper data/ml data/ai_data"
REPO_URL="${STATE_REPO_URL:-https://x-access-token:${GITHUB_TOKEN:-}@github.com/${GITHUB_REPOSITORY:-}.git}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

clone_branch() {
  git clone -q --depth 1 --branch "$BRANCH" "$REPO_URL" "$TMP/repo" 2>/dev/null
}

case "${1:-}" in
  restore)
    if clone_branch; then
      for d in $DIRS; do
        if [ -d "$TMP/repo/$d" ]; then
          rm -rf "$d"; mkdir -p "$(dirname "$d")"; cp -R "$TMP/repo/$d" "$d"
        fi
      done
      echo "[state] restored from $BRANCH"
    else
      echo "[state] no saved state yet (first run)"
    fi
    ;;
  save)
    if ! clone_branch; then
      rm -rf "$TMP/repo"; mkdir -p "$TMP/repo"
      git -C "$TMP/repo" init -q
      git -C "$TMP/repo" checkout -q -b "$BRANCH"
      git -C "$TMP/repo" remote add origin "$REPO_URL"
    fi
    for d in $DIRS; do
      if [ -d "$d" ]; then
        rm -rf "$TMP/repo/$d"; mkdir -p "$(dirname "$TMP/repo/$d")"; cp -R "$d" "$TMP/repo/$d"
      fi
    done
    cd "$TMP/repo"
    git config user.name "trading-bot"
    git config user.email "trading-bot@users.noreply.github.com"
    git add -A
    if git diff --cached --quiet; then echo "[state] nothing to save"; exit 0; fi
    git commit -q -m "paper state $(date -u +%FT%TZ)"
    git push -q origin "HEAD:refs/heads/$BRANCH"
    echo "[state] saved to $BRANCH"
    ;;
  *)
    echo "usage: $0 restore|save" >&2; exit 2 ;;
esac
