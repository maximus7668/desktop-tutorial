#!/usr/bin/env bash
# Renderiza el anuncio del panel. Uso: bash render.sh [salida.mp4] [voz.mp3] [musica.mp3]
# La voz y la música van en public/ y se pasan por nombre.
set -euo pipefail
cd "$(dirname "$0")"
OUT="${1:-out/deika-anuncio-panel.mp4}"
PROPS="{}"
[ -n "${2:-}" ] && PROPS="{\"voz\":\"$2\"${3:+,\"musica\":\"$3\"}}"
FLAG=()
for shell in "${PLAYWRIGHT_BROWSERS_PATH:-/opt/pw-browsers}"/chromium_headless_shell-*/chrome-linux/headless_shell; do
  [ -x "$shell" ] && FLAG=(--browser-executable="$shell") && break
done
npx remotion render src/index.ts AnuncioPanel "$OUT" --codec=h264 --crf=18 --props="$PROPS" "${FLAG[@]}"
