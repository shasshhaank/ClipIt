#!/usr/bin/env bash
# claude-clipper installer: ffmpeg, a Python 3.10+ venv, and the Python packages (Whisper, yt-dlp, ...).
# Usage: bash install.sh [--yes] [--with-cutout]
#   --yes          the user already agreed, so missing ffmpeg / Python are installed with Homebrew without asking.
#   --with-cutout  also install the optional subject cut-out model (rembg, about 200 MB): text behind people, rim light.
set -euo pipefail
cd "$(dirname "$0")"
YES=0; CUT=0
for a in "$@"; do case "$a" in --yes) YES=1;; --with-cutout) CUT=1;; esac; done
ask() { [ "$YES" = 1 ] && return 0; [ -t 0 ] || return 1; read -r -p "$1 [y/N] " r; [[ "$r" =~ ^[Yy] ]]; }

if ! command -v ffmpeg >/dev/null; then
  if command -v brew >/dev/null && ask "ffmpeg is missing. Install it with Homebrew?"; then
    brew install ffmpeg
  else
    echo "ffmpeg not found. Install it first:"
    echo "  macOS:  brew install ffmpeg"
    echo "  Ubuntu: sudo apt install ffmpeg"
    exit 1
  fi
fi

PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  if command -v brew >/dev/null && ask "Python 3.10+ is missing. Install python@3.12 with Homebrew?"; then
    brew install python@3.12; PY=python3.12
  else
    echo "Python 3.10+ required (macOS: brew install python@3.12, Ubuntu: sudo apt install python3-venv)"; exit 1
  fi
fi

[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
# free display fonts (SIL Open Font License, via the Google Fonts API) for poster frames and labels;
# optional, system fonts are used otherwise
for pair in "Anton|Anton-Regular.ttf" "Archivo+Black|ArchivoBlack-Regular.ttf" "Space+Mono:wght@700|SpaceMono-Bold.ttf" \
            "Amatic+SC:wght@700|AmaticSC-Bold.ttf"; do
  n="fonts/${pair#*|}"
  [ -f "$n" ] && continue
  url=$(curl -fsS "https://fonts.googleapis.com/css2?family=${pair%%|*}" | grep -o 'https://[^)]*\.ttf' | head -1) || url=""
  { [ -n "$url" ] && curl -fsSL "$url" -o "$n.part" && mv "$n.part" "$n"; } \
    || { rm -f "$n.part"; echo "could not download ${n#fonts/} (optional, using system fonts)"; }
done
if [ "$CUT" = 1 ] || { [ "$YES" = 0 ] && ask "Install the optional subject cut-out (rembg, about 200 MB) for text behind people and rim light?"; }; then
  .venv/bin/pip install -q rembg onnxruntime || echo "subject cut-out install failed (optional)"
fi
.venv/bin/python clip.py doctor
echo
echo "Installed. Run:  $(pwd)/.venv/bin/python $(pwd)/clip.py --help"
