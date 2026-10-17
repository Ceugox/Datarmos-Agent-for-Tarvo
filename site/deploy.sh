#!/usr/bin/env sh
# The Railway service root is /site; never upload the API Dockerfile as its root.
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
STAGE=$(mktemp -d)
REPORT=${1:-"$ROOT/saida"}
test -r "$REPORT/manifest.json" && test -r "$REPORT/index.html"
mkdir -p "$STAGE/site/relatorio"
cp -R "$ROOT/site/." "$STAGE/site/"
cp -R "$REPORT/." "$STAGE/site/relatorio/"
railway up "$STAGE" --path-as-root --project 7d7a98a0-96b7-430c-a9db-8747c81ad8bb --environment production --service site --detach
