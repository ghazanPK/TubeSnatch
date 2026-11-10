# PyInstaller spec for the Windows build. Run via scripts/build_windows.ps1.
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH)
BUILD = ROOT / ".build"

datas = [(str(ROOT / "src" / "tubesnatch" / "assets"), "assets")]
datas += collect_data_files("yt_dlp_ejs")
datas += [(str(ROOT / "THIRD_PARTY_NOTICES.md"), "."), (str(ROOT / "README.md"), ".")]

# ffmpeg/ffprobe (+ their DLLs) and deno.exe, staged by the build script
binaries = [(str(p), "bin") for p in (BUILD / "bin").iterdir() if p.is_file()]

hiddenimports = collect_submodules("yt_dlp_ejs")

a = Analysis(
    [str(ROOT / "scripts" / "launch.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "deno", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TubeSnatch",
    icon=str(BUILD / "icon.ico"),
    console=False,
    upx=False,
    version=str(BUILD / "version_info.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="TubeSnatch", upx=False)
