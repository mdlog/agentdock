#!/usr/bin/env bash
# Build the frontend without ever putting the live site at risk.
#
# `npm run build` empties build/ before it writes anything, so a compile error
# leaves no site at all — serve_frontend.py then refuses to start and systemd
# restart-loops behind a 502. That is exactly how a stray brace in App.css took
# agents.mdloglabs.org down for four minutes. This builds to a staging
# directory and only swaps it in once the output is verifiably complete.
set -euo pipefail

cd "$(dirname "$0")/../frontend"

rm -rf build.next
BUILD_PATH=build.next GENERATE_SOURCEMAP=false npx craco build

# A zero-exit build with no entry point still cannot serve traffic.
if [[ ! -s build.next/index.html || ! -d build.next/static/js ]]; then
  echo "Build produced no usable output — keeping the current site." >&2
  rm -rf build.next
  exit 1
fi

rm -rf build.prev
[[ -d build ]] && mv build build.prev
mv build.next build
rm -rf build.prev

echo "Published $(du -sh build | cut -f1) to frontend/build"
