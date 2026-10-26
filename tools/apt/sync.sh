#!/usr/bin/env bash
# ============================================================================
#  Publish the Wallisoft apt repository.
#
#  Collects the newest .deb Bob has built for each app (~/.cache/bob/<App>/Linux),
#  rebuilds the signed repo with tools/apt/publish.sh, and rsyncs it live to tw1.
#  Idempotent: run it as often as you like. Meant to be run from Bob
#  (Kind=command, cwd = repo root) or by hand after a Linux build.
#
#  Config via env:
#    APT_REPO        where the repo tree is built   (default ~/apt-repo)
#    APT_SUITE       the suite                        (default stable)
#    BOB_CACHE       Bob's build cache               (default ~/.cache/bob)
#    APT_RSYNC_DEST  where it goes live              (default tw1:<api docroot>/apt/)
#    GPGKEY          signing key (passed through to publish.sh; default repo@wallisoft.uk)
# ============================================================================
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
REPO_OUT=${APT_REPO:-$HOME/apt-repo}
SUITE=${APT_SUITE:-stable}
CACHE=${BOB_CACHE:-$HOME/.cache/bob}
DEST=${APT_RSYNC_DEST:-tw1:/var/www/html/api.tiny-web.uk/public_html/apt/}

# the newest _amd64.deb Bob has built for each app (one per app folder)
debs=()
for d in "$CACHE"/*/Linux; do
    [ -d "$d" ] || continue
    newest=$(ls -t "$d"/*_amd64.deb 2>/dev/null | head -1 || true)
    [ -n "$newest" ] && debs+=("$newest")
done
[ "${#debs[@]}" -ge 1 ] || { echo "no .deb under $CACHE/*/Linux — build a Linux package first" >&2; exit 1; }

echo "== rebuilding '$SUITE' from: $(for f in "${debs[@]}"; do printf '%s ' "${f##*/}"; done)=="
rm -rf "$REPO_OUT/pool" "$REPO_OUT/dists"          # clean rebuild: only the current debs (the signing key stays)
"$HERE/publish.sh" "$REPO_OUT" "$SUITE" "${debs[@]}"

echo "== pushing live -> $DEST =="
rsync -a --delete "$REPO_OUT/" "$DEST"
echo "== live: https://api.tiny-web.uk/apt =="
