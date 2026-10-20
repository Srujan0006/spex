#!/usr/bin/env bash
# Install TChecker v0.8 (github.com/ticktac-project/tchecker, MIT) into $1 (default: tchecker/install).
# Uses the release's Linux x86_64 binary, checked against a pinned SHA-256; with --source it builds the same tag
# instead (needs cmake, flex, bison, Boost and Catch2). The old fredher/tchecker master (2021) does not compile with
# GCC 13 (CI run 39415576016), which is why this script uses the ticktac-project repository.
set -euo pipefail
PREFIX="${1:-$PWD/tchecker/install}"
TAG=v0.8
TARBALL=tchecker-Linux_x86_64-0.8.tar.gz
SHA256=8ff847bf8105fbe662ae3c19fd2b70c555f5fa5f5e6f6314170a3fe058aa70e2
mkdir -p "$PREFIX"
if [ "${2:-}" != "--source" ]; then
    tmp=$(mktemp -d)
    curl -fsSL -o "$tmp/$TARBALL" "https://github.com/ticktac-project/tchecker/releases/download/$TAG/$TARBALL"
    echo "$SHA256  $tmp/$TARBALL" | sha256sum -c -
    tar xzf "$tmp/$TARBALL" -C "$tmp"
    cp -r "$tmp"/tchecker-0.8/* "$PREFIX"/
    rm -rf "$tmp"
else
    src=$(mktemp -d)
    git clone -q --depth 1 -b "$TAG" https://github.com/ticktac-project/tchecker "$src"
    cmake -S "$src" -B "$src/build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PREFIX" > /dev/null
    make -C "$src/build" -j"$(nproc)" install > /dev/null
fi
"$PREFIX/bin/tck-reach" -h > /dev/null 2>&1 || true
echo "TChecker $TAG in $PREFIX"
