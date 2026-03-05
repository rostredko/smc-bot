#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"

if [[ ! -f "${repo_root}/.githooks/pre-push" ]]; then
  echo "Missing hook file: ${repo_root}/.githooks/pre-push" >&2
  exit 1
fi

chmod +x "${repo_root}/.githooks/pre-push"
git config core.hooksPath ".githooks"

echo "Git hooks installed."
echo "Active hooks path: $(git config core.hooksPath)"
