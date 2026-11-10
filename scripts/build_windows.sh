#!/usr/bin/env bash
# Build the Windows app from inside WSL.
# PyInstaller cannot cross-compile, so this hands the build to Windows PowerShell
# (which uses its own portable uv + Python under .build/ — nothing system-wide).
#   ./scripts/build_windows.sh [-UpdateYtDlp] [-Clean]
set -euo pipefail
cd "$(dirname "$0")/.."
WIN_ROOT="$(wslpath -w "$PWD")"
exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$WIN_ROOT\\scripts\\build_windows.ps1" "$@"
