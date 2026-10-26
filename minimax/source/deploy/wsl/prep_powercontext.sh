#!/usr/bin/env bash
set -e
REPO_DIR=/opt/powercontext
REPO_URL=https://github.com/oceanbase/powercontext.git
REF=master

if [ ! -d "$REPO_DIR/.git" ]; then
  git clone "$REPO_URL" "$REPO_DIR"
fi
git -C "$REPO_DIR" fetch --tags --force
git -C "$REPO_DIR" checkout "$REF"
git -C "$REPO_DIR" reset --hard "origin/$REF"
git -C "$REPO_DIR" pull --ff-only origin "$REF"

echo "powercontext source ready at $REPO_DIR (ref=$REF)"
git -C "$REPO_DIR" log -1 --oneline
ls -la "$REPO_DIR/uv.lock"
