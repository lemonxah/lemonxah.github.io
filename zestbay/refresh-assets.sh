#!/bin/bash
# Re-pull the screenshots from a ZestBay checkout and rebuild the web-sized images.
# Run after each release so the site never shows an older UI than the one people install.
#
#   ./refresh-assets.sh [path to the zestbay repo]     # default: ../../zestbay
#
# Needs ImageMagick (with WebP support). The repo's own screenshots come from
# design/screenshots/render.sh in the zestbay repo, so render those first.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "${1:-$HERE/../../zestbay}" && pwd)
SRC="$REPO/docs/screenshots"
OUT="$HERE/assets/img"
[ -d "$SRC" ] || { echo "no screenshots in $SRC" >&2; exit 1; }

conv() { # source name, output name, width
    magick "$SRC/$1.png" -resize "$3"x -strip -quality 80 -define webp:method=6 "$OUT/$2.webp"
    magick "$SRC/$1.png" -resize "$3"x -strip -define png:compression-level=9 "$OUT/$2.png"
}
conv main-dark  hero        2000
conv main-light main-light  1600
conv add-plugin add-plugin  1120
conv rules      rules       1040
conv presets    presets      600
conv parameters parameters   720
conv cpu-usage  cpu-usage   1040
# Open Graph / Twitter card: top 1200x630 of the dark main window
magick "$SRC/main-dark.png" -resize 1200x -gravity north -crop 1200x630+0+0 +repage -strip -quality 85 "$OUT/og.png"

VERSION=$(grep '^version' "$REPO/Cargo.toml" | head -1 | sed 's/.*"\(.*\)".*/\1/')
echo "Images refreshed. Repo is at v$VERSION."
echo "The page reads its version from the newest GitHub tag (version.js); nothing to update there."
