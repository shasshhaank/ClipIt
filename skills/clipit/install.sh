#!/usr/bin/env bash
# ClipIt setup: one Python environment with everything the skill needs, kept in ~/.clipit
# (CLIPIT_HOME) so it survives skill and plugin updates. No Homebrew and no admin rights: ffmpeg comes with the
# imageio-ffmpeg package, and if this computer's Python is older than 3.10, uv (from PyPI) fetches a private one.
# Usage: bash install.sh [--with-cutout] [--with-hindi]
#   --with-cutout  also install the optional subject cut-out (rembg, about 200 MB), for text behind people and rim
#                  light. Only when the user asks for one of those.
#   --with-hindi   OpenAI's full Whisper large-v3 model (about 3 GB) for Hindi and other languages the fast model
#                  gets wrong, plus correct Hindi text shaping and a Devanagari font. Only when the user wants
#                  subtitles for such a video.
set -euo pipefail
cd "$(dirname "$0")"
HOME_DIR="${CLIPIT_HOME:-$HOME/.clipit}"
VENV="$HOME_DIR/venv"
CUT=0; HINDI=0
for a in "$@"; do case "$a" in --with-cutout) CUT=1;; --with-hindi) HINDI=1;; esac; done
mkdir -p "$HOME_DIR/fonts"

if [ ! -x "$VENV/bin/python" ]; then
  PY=""
  for c in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      PY="$c"; break
    fi
  done
  if [ -n "$PY" ]; then
    "$PY" -m venv "$VENV"
  elif command -v python3 >/dev/null; then
    echo "This Python is older than 3.10; fetching a private Python 3.12 with uv (no admin rights needed)..."
    python3 -m pip install -q --user uv
    UV="$(python3 -c 'import os, site; print(os.path.join(site.USER_BASE, "bin", "uv"))')"
    "$UV" venv -q --seed --python 3.12 "$VENV"
  else
    echo "Python 3 is missing. On macOS run:  xcode-select --install   (Apple's free command line tools), then try again."
    exit 1
  fi
fi

"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q -r requirements.txt

# free display fonts (SIL Open Font License, via the Google Fonts API) for poster frames and labels;
# optional, system fonts are used otherwise
for pair in "Anton|Anton-Regular.ttf" "Archivo+Black|ArchivoBlack-Regular.ttf" "Space+Mono:wght@700|SpaceMono-Bold.ttf" \
            "Amatic+SC:wght@700|AmaticSC-Bold.ttf"; do
  n="$HOME_DIR/fonts/${pair#*|}"
  [ -f "$n" ] && continue
  url=$(curl -fsS "https://fonts.googleapis.com/css2?family=${pair%%|*}" | grep -o 'https://[^)]*\.ttf' | head -1) || url=""
  { [ -n "$url" ] && curl -fsSL "$url" -o "$n.part" && mv "$n.part" "$n"; } \
    || { rm -f "$n.part"; echo "could not download $(basename "$n") (optional, using system fonts)"; }
done

if [ "$CUT" = 1 ]; then
  "$VENV/bin/python" -m pip install -q rembg onnxruntime || echo "subject cut-out install failed (optional)"
fi
if [ "$HINDI" = 1 ]; then
  "$VENV/bin/python" -m pip install -q uharfbuzz freetype-py
  n="$HOME_DIR/fonts/NotoSansDevanagari-Bold.ttf"
  if [ ! -f "$n" ]; then
    url=$(curl -fsS "https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@700" | grep -o 'https://[^)]*\.ttf' | head -1) || url=""
    { [ -n "$url" ] && curl -fsSL "$url" -o "$n.part" && mv "$n.part" "$n"; } || { rm -f "$n.part"; echo "could not download the Devanagari font (system fonts are used)"; }
  fi
  echo "Downloading OpenAI Whisper large-v3 (about 3 GB, once)..."
  "$VENV/bin/python" - <<'PY'
import os
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
try:
    import mlx_whisper  # noqa: F401
    from huggingface_hub import snapshot_download
    snapshot_download("mlx-community/whisper-large-v3-mlx")
except ImportError:
    from faster_whisper import WhisperModel
    WhisperModel("large-v3")
print("Whisper large-v3 ready")
PY
fi
"$VENV/bin/python" clip.py doctor
