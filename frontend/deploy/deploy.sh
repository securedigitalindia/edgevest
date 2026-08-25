#!/usr/bin/env bash
# Versioned S3 + CloudFront deploy, with fast rollback.
#
# Each deploy uploads dist/ to its own S3 prefix (releases/<release-id>/)
# instead of overwriting the bucket root, then repoints the CloudFront
# distribution's OriginPath at that prefix. Nothing already deployed is ever
# touched, so rollback is just repointing OriginPath at an older prefix +
# invalidating — one API call, no rebuild/reupload, old release still intact.
#
# Usage:
#   deploy.sh deploy   <prod|staging|dev> [release-id]
#   deploy.sh rollback <prod|staging|dev> <release-id>
#   deploy.sh list     <prod|staging|dev>
#   deploy.sh current  <prod|staging|dev>
#
# release-id defaults to `git describe --tags --always --dirty` (e.g. "v5.0",
# or "v5.0-3-gabc1234" if HEAD is 3 commits past the tag, or "-dirty" appended
# if the working tree has uncommitted changes — deploying dirty is allowed but
# flagged in the id so it's obvious later which release that was).
#
# Requires: aws CLI (configured, profile "default"), python3, node/npm.
# Does NOT require jq — CloudFront config is edited via a small python3
# snippet instead, so this runs on a bare AWS CLI + python3 install.

set -euo pipefail

FRONTEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AWS_PROFILE="default"

usage() {
  echo "Usage:"
  echo "  $0 deploy   <prod|staging|dev> [release-id]"
  echo "  $0 rollback <prod|staging|dev> <release-id>"
  echo "  $0 list     <prod|staging|dev>"
  echo "  $0 current  <prod|staging|dev>"
  exit 1
}

env_config() {
  case "$1" in
    prod)    BUCKET="edgevest-frontend";         DIST_ID="EN3ECQGE4B933"; BUILD_CMD="npm run build" ;;
    staging) BUCKET="edgevest-frontend-staging"; DIST_ID="E3P4LNBWP838MK"; BUILD_CMD="npm run build:staging" ;;
    dev)     BUCKET="edgevest-frontend-dev";     DIST_ID="E1JHFOPTMLOMJT"; BUILD_CMD="npm run build:dev" ;;
    *) echo "Unknown env '$1' — must be prod, staging, or dev." >&2; exit 1 ;;
  esac
}

confirm() {
  read -r -p "$1 [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 1; }
}

# Fetches the distribution config, edits OriginPath for the origin that
# DefaultCacheBehavior actually routes to (not just Origins[0] — robust if a
# second origin is ever added), and calls update-distribution with the
# matching ETag. $1 = new OriginPath (e.g. "/releases/v5.0").
set_origin_path() {
  local new_path="$1"
  local cfg_file etag
  cfg_file="$(mktemp)"
  aws cloudfront get-distribution-config --id "$DIST_ID" --profile "$AWS_PROFILE" > "$cfg_file"
  etag="$(python3 -c "import json; print(json.load(open('$cfg_file'))['ETag'])")"

  local new_cfg_file
  new_cfg_file="$(mktemp)"
  python3 - "$cfg_file" "$new_path" > "$new_cfg_file" <<'PYEOF'
import json, sys
cfg_file, new_path = sys.argv[1], sys.argv[2]
d = json.load(open(cfg_file))
cfg = d["DistributionConfig"]
target_id = cfg["DefaultCacheBehavior"]["TargetOriginId"]
matched = False
for origin in cfg["Origins"]["Items"]:
    if origin["Id"] == target_id:
        origin["OriginPath"] = new_path
        matched = True
if not matched:
    sys.exit(f"Could not find origin matching TargetOriginId {target_id!r}")
json.dump(cfg, sys.stdout)
PYEOF

  aws cloudfront update-distribution \
    --id "$DIST_ID" \
    --distribution-config "file://$new_cfg_file" \
    --if-match "$etag" \
    --profile "$AWS_PROFILE" \
    > /dev/null
  rm -f "$cfg_file" "$new_cfg_file"
}

get_current_origin_path() {
  aws cloudfront get-distribution-config --id "$DIST_ID" --profile "$AWS_PROFILE" \
    | python3 -c "
import json, sys
cfg = json.load(sys.stdin)['DistributionConfig']
target_id = cfg['DefaultCacheBehavior']['TargetOriginId']
for o in cfg['Origins']['Items']:
    if o['Id'] == target_id:
        print(o.get('OriginPath', '') or '(root — pre-versioning deploy)')
"
}

invalidate() {
  echo "Creating CloudFront invalidation for /* ..."
  aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/*" --profile "$AWS_PROFILE" \
    | python3 -c "import json,sys; print('Invalidation:', json.load(sys.stdin)['Invalidation']['Id'])"
}

cmd_deploy() {
  local env="$1"; env_config "$env"
  local release_id="${2:-$(git -C "$FRONTEND_DIR" describe --tags --always --dirty)}"

  echo "Env:        $env"
  echo "Bucket:     $BUCKET"
  echo "Distribution: $DIST_ID"
  echo "Release id: $release_id"
  echo "Current origin path: $(get_current_origin_path)"
  confirm "Build, upload to releases/$release_id/, and switch $env live traffic to it?"

  echo "--- Building ($BUILD_CMD) ---"
  (cd "$FRONTEND_DIR" && $BUILD_CMD)

  echo "--- Uploading dist/ to s3://$BUCKET/releases/$release_id/ ---"
  aws s3 sync "$FRONTEND_DIR/dist/" "s3://$BUCKET/releases/$release_id/" --profile "$AWS_PROFILE"

  echo "--- Switching origin path to /releases/$release_id ---"
  set_origin_path "/releases/$release_id"

  invalidate

  echo ""
  echo "Deployed. CloudFront edges pick up the change over the next few"
  echo "minutes (distribution status goes InProgress -> Deployed)."
  echo "Previous release stays in S3 untouched — roll back any time with:"
  echo "  $0 rollback $env <previous-release-id>"
}

cmd_rollback() {
  local env="$1"; env_config "$env"
  local release_id="${2:-}"
  [[ -n "$release_id" ]] || { echo "rollback needs a release-id — see: $0 list $env" >&2; exit 1; }

  if ! aws s3 ls "s3://$BUCKET/releases/$release_id/" --profile "$AWS_PROFILE" > /dev/null 2>&1; then
    echo "No release found at s3://$BUCKET/releases/$release_id/ — see: $0 list $env" >&2
    exit 1
  fi

  echo "Env:    $env"
  echo "Current origin path: $(get_current_origin_path)"
  confirm "Roll back $env live traffic to releases/$release_id/ ?"

  set_origin_path "/releases/$release_id"
  invalidate

  echo ""
  echo "Rolled back to $release_id."
}

cmd_list() {
  local env="$1"; env_config "$env"
  echo "Releases in s3://$BUCKET/releases/ (current: $(get_current_origin_path)):"
  # `aws s3 ls` exits 1 on an empty/nonexistent prefix (e.g. before the first
  # versioned deploy has ever run) — that's a normal state here, not an error.
  local listing
  listing="$(aws s3 ls "s3://$BUCKET/releases/" --profile "$AWS_PROFILE" 2>/dev/null || true)"
  if [[ -z "$listing" ]]; then
    echo "  (none yet)"
  else
    echo "$listing" | awk '{print "  "$2}' | sed 's#/$##'
  fi
}

cmd_current() {
  local env="$1"; env_config "$env"
  echo "$env is currently serving: $(get_current_origin_path)"
}

[[ $# -ge 1 ]] || usage
subcmd="$1"; shift
case "$subcmd" in
  deploy)   [[ $# -ge 1 ]] || usage; cmd_deploy "$@" ;;
  rollback) [[ $# -ge 1 ]] || usage; cmd_rollback "$@" ;;
  list)     [[ $# -ge 1 ]] || usage; cmd_list "$@" ;;
  current)  [[ $# -ge 1 ]] || usage; cmd_current "$@" ;;
  *) usage ;;
esac
