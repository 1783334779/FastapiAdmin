#!/usr/bin/env bash
# Transport only: preserve stdin for bundles / short-lived registry credentials.
set -euo pipefail
action=${1:?missing action}
sha=${2:?missing SHA}
[[ "$action" =~ ^(baseline|receive|deploy|status)$ && "$sha" =~ ^[0-9a-f]{40}$ ]]
test -n "${DEPLOY_HOST:?}" && test -n "${DEPLOY_USER:?}"
test -n "${DEPLOY_SSH_KEY:?}" && test -n "${DEPLOY_KNOWN_HOSTS:?}"
umask 077
key_dir=$(mktemp -d "${RUNNER_TEMP:-/tmp}/deploy-key.XXXXXXXX")
trap 'rm -f "$key_dir/id_ed25519" "$key_dir/known_hosts"; rmdir "$key_dir"' EXIT
printf '%s\n' "$DEPLOY_SSH_KEY" > "$key_dir/id_ed25519"
printf '%s\n' "$DEPLOY_KNOWN_HOSTS" > "$key_dir/known_hosts"
unset DEPLOY_SSH_KEY DEPLOY_KNOWN_HOSTS
ssh -T -i "$key_dir/id_ed25519" -p "${DEPLOY_PORT:-22}" \
  -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  -o "UserKnownHostsFile=$key_dir/known_hosts" -o ConnectTimeout=15 \
  -o ServerAliveInterval=15 -o ServerAliveCountMax=8 \
  "$DEPLOY_USER@$DEPLOY_HOST" "$action $sha"
