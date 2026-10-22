#!/usr/bin/env bash
# Add (or rotate the key of) one project on a deployed notification service. No redeploy needed.
# Makes a random key, stores only its SHA-256 in the service's KV (k:<project>), and saves the key as the repo secret
# SDLC_NOTIFY_KEY. The key itself is never printed. Run it from the folder you deployed the service from.
# Usage: ./add-project.sh <project-name> <owner/repo>      project-name must equal `project:` in the repo's .sdlc/config.yml
set -euo pipefail
project=${1:?usage: add-project.sh <project-name> <owner/repo>}
repo=${2:?usage: add-project.sh <project-name> <owner/repo>}
[[ $project =~ ^[a-z0-9][a-z0-9._-]*$ ]] || { echo "project-name: lowercase letters, digits, . _ - only" >&2; exit 1; }
cd "$(dirname "$0")"
key=$(openssl rand -hex 24)
hash=$(printf %s "$key" | shasum -a 256 | cut -d' ' -f1)
# KV commands write to local storage unless --remote is given, which would silently leave the live service without the key.
npx --yes wrangler@4 kv key put --binding STATE --remote "k:$project" "$hash"
printf %s "$key" | gh secret set SDLC_NOTIFY_KEY --repo "$repo"
echo "Project '$project' added. Next: set notify.url in $repo's .sdlc/config.yml (through a PR), then run the sdlc-notify-test workflow."
