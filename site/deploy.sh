#!/usr/bin/env sh
# Publica o site no serviço "site" do projeto Railway tarvo-fechamento.
# Monta uma pasta limpa com site/ e saida/ (como relatorio/) e roda railway up nela.
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
STAGE=$(mktemp -d)
cp -R "$ROOT/site/." "$STAGE/"
mkdir -p "$STAGE/relatorio" && cp -R "$ROOT/saida/." "$STAGE/relatorio/"
railway up "$STAGE" --path-as-root --project 7d7a98a0-96b7-430c-a9db-8747c81ad8bb --environment production --service site --detach
