#!/usr/bin/env bash
# Renders the launch video. Usage: bash scripts/render.sh [16x9|9x16|both] [out-dir]
set -euo pipefail
cd "$(dirname "$0")/.."
FORMAT="${1:-both}"
OUT="${2:-out}"
mkdir -p "$OUT"

# Reuse a preinstalled headless Chromium when present (cloud containers); otherwise Remotion downloads its own.
BROWSER_FLAG=()
for shell in "${PLAYWRIGHT_BROWSERS_PATH:-/opt/pw-browsers}"/chromium_headless_shell-*/chrome-linux/headless_shell; do
  [ -x "$shell" ] && BROWSER_FLAG=(--browser-executable="$shell") && break
done

NAME=$(node -e "console.log(require('./src/brand.json').domain.replace(/[^a-z0-9]+/gi,'-'))")
render() {
  npx remotion render src/index.ts "$1" "$OUT/$NAME-$2.mp4" --codec=h264 --crf=18 "${BROWSER_FLAG[@]}"
}
case "$FORMAT" in
  16x9) render Launch16x9 16x9 ;;
  9x16) render Launch9x16 9x16 ;;
  both) render Launch16x9 16x9; render Launch9x16 9x16 ;;
  *) echo "Unknown format: $FORMAT" >&2; exit 1 ;;
esac
ls -lh "$OUT"
