#!/bin/bash
# One-time setup: Python venv with whisper (transcription), Pillow (graphics), SciPy (audio).
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v ffmpeg >/dev/null || { echo "ffmpeg is missing. Install it with: brew install ffmpeg"; exit 1; }
python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install -q --upgrade pip
"$DIR/.venv/bin/pip" install -q -r "$DIR/requirements.txt"
echo "Setup complete."
