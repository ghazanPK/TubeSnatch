#!/usr/bin/env bash
# Run TubeSnatch from source inside WSL (shows up on the Windows desktop via WSLg).
# The Linux venv lives outside the repo so it never clashes with the Windows build venv.
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$HOME/.venvs/tubesnatch}"
command -v ffmpeg >/dev/null || echo "Tip: sudo apt install ffmpeg  (needed for MP3 + HD merging)"
exec uv run tubesnatch "$@"
