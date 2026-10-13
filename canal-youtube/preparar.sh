#!/usr/bin/env bash
# Prepara el entorno del agente: dependencias de Python y comprobación final.
# Uso: bash preparar.sh   (desde canal-youtube/ o desde cualquier sitio)
set -uo pipefail
cd "$(dirname "$0")"
if ! command -v ffmpeg >/dev/null; then
  echo "Falta ffmpeg (con libass). Ubuntu/Debian: sudo apt-get install -y ffmpeg · macOS: brew install ffmpeg"
  exit 1
fi
PY=${PYTHON:-python3}
# num2words depende de docopt, que no compila en algunos Python recientes: se instala aparte sin ella
grep -v '^num2words' requirements.txt > /tmp/canal-req.txt
$PY -m pip install --quiet -r /tmp/canal-req.txt
$PY -m pip install --quiet --no-deps "num2words>=0.5.13"
$PY -m canal comprobar
