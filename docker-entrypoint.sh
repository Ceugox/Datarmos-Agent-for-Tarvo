#!/bin/sh
# Starts as root so it can fix the ownership of the mounted volume, then drops to the app user.
set -eu
DIR="${DATA_DIR:-/data}"
mkdir -p "$DIR" || true
chown -R app:app "$DIR" 2>/dev/null || true
if ! runuser -u app -- sh -c 't="$1/.write-test.$$" && : > "$t" && rm -f "$t"' sh "$DIR"; then
    echo "docker-entrypoint: o usuario app nao consegue escrever em $DIR (DATA_DIR); confira o volume e as permissoes" >&2
    exit 1
fi
exec runuser -u app -- "$@"
