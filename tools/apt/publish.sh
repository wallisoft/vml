#!/usr/bin/env bash
# ============================================================================
#  Wallisoft apt repository publisher
#
#  Builds a *signed* flat apt repo from .deb files using only stock tools
#  (apt-ftparchive + gpg) — no reprepro. The output is a static tree you serve
#  from any web server (nginx/apache serve every file type as-is) and that
#  `apt` reads directly. Re-run it to add or refresh packages; it rebuilds the
#  indexes and re-signs each time.
#
#    tools/apt/publish.sh OUT_DIR SUITE DEB [DEB ...]
#      OUT_DIR  where the repo tree is built (created/updated in place)
#      SUITE    the distribution name, e.g. stable
#      DEB...   .deb files to include
#
#  Env: GPGKEY (signing key id/email in the local keyring; default repo@wallisoft.uk),
#       ORIGIN, LABEL, ARCH (default amd64), COMP (default main).
# ============================================================================
set -euo pipefail

OUT=${1:?usage: publish.sh OUT_DIR SUITE DEB [DEB ...]}
SUITE=${2:?need a suite name, e.g. stable}
shift 2
[ "$#" -ge 1 ] || { echo "no .deb files given" >&2; exit 1; }

GPGKEY=${GPGKEY:-repo@wallisoft.uk}
ORIGIN=${ORIGIN:-Wallisoft}
LABEL=${LABEL:-Wallisoft}
ARCH=${ARCH:-amd64}
COMP=${COMP:-main}

mkdir -p "$OUT"

# 1) drop each .deb into pool/<comp>/<first-letter>/<package>/
for deb in "$@"; do
    [ -f "$deb" ] || { echo "no such .deb: $deb" >&2; exit 1; }
    pkg=$(dpkg-deb -f "$deb" Package)
    dest="$OUT/pool/$COMP/${pkg:0:1}/$pkg"
    mkdir -p "$dest"
    cp -f "$deb" "$dest/"
done

cd "$OUT"

# 2) the Packages index for this arch
bindir="dists/$SUITE/$COMP/binary-$ARCH"
mkdir -p "$bindir"
apt-ftparchive packages pool > "$bindir/Packages"
gzip -9kf "$bindir/Packages"

# 3) the Release file (with checksums of everything above), signed two ways:
#    InRelease (inline clear-sign, what modern apt prefers) and Release.gpg (detached, older apt)
apt-ftparchive \
    -o APT::FTPArchive::Release::Origin="$ORIGIN" \
    -o APT::FTPArchive::Release::Label="$LABEL" \
    -o APT::FTPArchive::Release::Suite="$SUITE" \
    -o APT::FTPArchive::Release::Codename="$SUITE" \
    -o APT::FTPArchive::Release::Architectures="$ARCH" \
    -o APT::FTPArchive::Release::Components="$COMP" \
    -o APT::FTPArchive::Release::Description="$ORIGIN apt repository" \
    release "dists/$SUITE" > "dists/$SUITE/Release"

rm -f "dists/$SUITE/Release.gpg" "dists/$SUITE/InRelease"
gpg --batch --yes --default-key "$GPGKEY" -abs        -o "dists/$SUITE/Release.gpg" "dists/$SUITE/Release"
gpg --batch --yes --default-key "$GPGKEY" --clearsign -o "dists/$SUITE/InRelease"  "dists/$SUITE/Release"

# 4) the public key, for users to install into /usr/share/keyrings
gpg --export "$GPGKEY" > "wallisoft-archive-keyring.gpg"

echo "== built '$SUITE' in $OUT =="
find pool dists wallisoft-archive-keyring.gpg -type f | sort
