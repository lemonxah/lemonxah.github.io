#!/usr/bin/env bash
# Build the ZestEngine docs website into ./docs (plain HTML, ready for GitHub Pages).
#
#   ./build.sh                 sync guides from the engine repo, build the book, build the API reference
#   ./build.sh --no-sync       build from what is already in src/
#   ./build.sh --no-api        skip `cargo doc` (the API reference stays as it was)
#
# Needs: mdbook (cargo install mdbook --locked --version 0.5.4), python3, and for the API reference a
# checkout of the engine repo (ENGINE=path, default ~/storage/git/zestengine) with a Rust toolchain.
set -euo pipefail

cd "$(dirname "$0")"
ENGINE="${ENGINE:-$HOME/storage/git/zestengine}"
sync=1
api=1
for arg in "$@"; do
  case "$arg" in
    --no-sync) sync=0 ;;
    --no-api) api=0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

command -v mdbook >/dev/null || { echo "mdbook not found: cargo install mdbook --locked --version 0.5.4" >&2; exit 1; }

[ "$sync" = 1 ] && python3 -I ./sync.py "$ENGINE"

# mdbook empties docs/, so keep the (large, slow to build) API reference aside while it runs.
keep=""
if [ -d docs/api ]; then
  keep="$(mktemp -d)"
  mv docs/api "$keep/api"
fi
mdbook build
# mdbook copies every non-markdown file in src/, including editor backups such as api.md~.
find docs -maxdepth 1 -name '*~' -delete
[ -n "$keep" ] && mv "$keep/api" docs/api && rmdir "$keep"

if [ "$api" = 1 ]; then
  (cd "$ENGINE" && cargo doc -p zestengine-core --no-deps)
  rm -rf docs/api
  mkdir -p docs/api
  cp -r "$ENGINE/target/doc/." docs/api/
  rm -f docs/api/.lock
fi

echo "built docs/ ($(find docs -type f | wc -l) files). Preview: python3 -m http.server -d . and open /zestengine/docs/"
