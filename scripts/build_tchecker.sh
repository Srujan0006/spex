#!/usr/bin/env bash
# Build TChecker (github.com/fredher/tchecker, MIT) at a pinned commit into $1 (default: tchecker/install).
# Dependencies on Ubuntu: cmake flex bison libboost-all-dev catch2 (the CI workflow installs them with apt).
set -euo pipefail
PREFIX="${1:-$PWD/tchecker/install}"
REV=9a9c83df5b2a4f56d5c2862765c437c08791b7c1      # master, 2026-10-20
SRC="${TCHECKER_SRC:-$PWD/tchecker/src}"
mkdir -p "$SRC" && cd "$SRC"
if [ ! -d .git ]; then git init -q && git remote add origin https://github.com/fredher/tchecker.git; fi
git fetch -q --depth 1 origin "$REV" && git checkout -q FETCH_HEAD
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PREFIX" > cmake.log 2>&1 || { tail -40 cmake.log; exit 1; }
make -j"$(nproc)" > make.log 2>&1 || { tail -60 make.log; exit 1; }
make install > install.log 2>&1
echo "TChecker $REV installed in $PREFIX"
