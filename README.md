# TubeSnatch

A desktop app for downloading YouTube **videos and whole playlists**: as video (**MP4 / MKV / WebM**) at the resolution
you pick, or as audio (**MP3 / M4A / Opus / FLAC / WAV**) with cover art and tags. It can also **trim clips**,
**split albums into tracks by chapter**, and **convert files you already have**. It keeps itself up to date.

Under the hood it uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) and [FFmpeg](https://ffmpeg.org).

## Features

**Download**
- Paste or drop a video or playlist link → every video lands in a list with thumbnail, title, channel and length.
- Per-video **format** and **quality**: resolution (only the ones that video really has) or audio bitrate.
- **Bulk actions**: check all or none, filter by title, *Apply default output to checked*, *Download checked*.
- **✂ Trim**: download only `1:20 → 3:45` of a video, optionally frame-accurate.
- **📑 Split by chapters**: one file per chapter, great for full albums and DJ mixes.
- **Only new videos**: TubeSnatch remembers what you downloaded. Re-fetch a playlist and only new videos are checked.
- Parallel downloads with live progress, speed and ETA. Cancel, and retry failed rows.
- Extras: **subtitles** (embedded or `.srt`), **SponsorBlock** (cuts sponsor segments), **volume normalisation**
  (EBU R128), **speed limit**, **clipboard watch** (copy a YouTube link and it's fetched).
- Playlists can go into their own folder with numbered files (`007 - Title.mp3`).

**Convert**
- Drop any local audio or video file (or folder) and convert it to MP4, MKV, WebM, MP3, M4A, Opus, FLAC or WAV.
- Optional max resolution or bitrate, and a lossless *fast copy* for container changes (MKV → MP4).

**Stays working**
- **Engine updates**: one click (or automatic) updates yt-dlp in place from PyPI, *stable* or *nightly*. That fixes
  most "YouTube changed something" breakages without a new TubeSnatch release.
- **App updates**: checks GitHub Releases. Pick *install automatically* or *notify me*, then *Update now* or *Later*.
  Updates are SHA-256 verified, and your settings and history are kept.

## Install (Windows)

1. Download **`TubeSnatch-<version>-win64-portable.zip`** from
   [Releases](https://github.com/ghazanPK/TubeSnatch/releases/latest).
2. Unzip it to a folder you own, for example `C:\Apps\TubeSnatch` (not *Program Files*, which isn't writable for updates).
3. Double-click **`TubeSnatch.exe`**. For Desktop or Start-menu shortcuts, go to *Settings → Shortcuts*.

Nothing else needs installing: Python, FFmpeg and Deno are inside the folder.

### Why does TubeSnatch.exe have the Python icon?

Windows 11's **Smart App Control** blocks unsigned programs it hasn't seen before. That covers every self-built
PyInstaller `.exe`, and even `.cmd`/`.lnk` launchers that came from the internet. So the portable build *is* the
official python.org runtime: `TubeSnatch.exe` is Python's own `pythonw.exe`, signed by the Python Software
Foundation and renamed. A tiny startup hook launches the app. Changing the icon would break the signature. The
window, the taskbar and the shortcuts from *Settings → Shortcuts* use the TubeSnatch icon.

## Development (WSL)

Requirements in WSL (Ubuntu): [uv](https://docs.astral.sh/uv/) and `ffmpeg` (`sudo apt install ffmpeg`).
WSLg shows the window on your Windows desktop.

```bash
./scripts/dev.sh                                         # run from source (venv in ~/.venvs/tubesnatch)
./scripts/dev.sh "https://youtube.com/playlist?list=..."  # …and fetch straight away
uv run pytest -q                                         # unit + offline FFmpeg + offscreen GUI tests
uv run pytest -q --live                                  # + real YouTube downloads
./scripts/build_windows.sh                               # build the Windows package (see below)
```

### Project layout

```
src/tubesnatch/
  engine.py          yt-dlp wrapper: probe, build options (formats, trim, chapters, subs, SponsorBlock…), download
  convert.py         local file converter (FFmpeg)
  ffmpeg.py          run/probe the bundled FFmpeg with progress + cancel
  archive.py         download history (yt-dlp --download-archive format)
  updates.py         engine (PyPI) + app (GitHub Releases) updates, shortcuts
  _swap.py           finishes an app update from the new build (wait → mirror → relaunch)
  _autostart.py      starts the GUI when the runtime runs as TubeSnatch.exe
  paths.py           finds bundled ffmpeg / deno, or system ones in dev
  ui/                Qt (PySide6) UI: main_window, download_tab, convert_tab, settings_tab, update_flow, …
scripts/
  build_windows.ps1  Windows build (portable; -PyInstaller for a classic exe)
  build_windows.sh   run the Windows build from WSL
  bump_version.py · lock_diff.py · release_notes.py   used by the release pipeline
tests/               pytest suite (run by CI on Linux and against the packaged Windows build)
.github/workflows/   CI, release and daily dependency update
```

## Building the Windows package

```bash
./scripts/build_windows.sh            # from WSL
# or in PowerShell:  powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

Windows binaries can't be built from Linux, so the script runs on the Windows side. It installs nothing
system-wide; everything is cached in `.build\`:
- a portable `uv.exe` ([astral-sh/uv](https://github.com/astral-sh/uv)) installs the locked dependencies
- signed CPython 3.13 from python.org's [NuGet package](https://www.nuget.org/packages/python)
- FFmpeg "essentials" from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) (via its GitHub mirror)

Output: `dist\TubeSnatch\` (about 450 MB), `dist\TubeSnatch-<version>-win64-portable.zip` (about 175 MB) and
`dist\SHA256SUMS.txt`. Options: `-UpdateYtDlp`, `-Clean`, and `-PyInstaller` (classic exe, for PCs without Smart App Control).

## Releases & automation (GitHub Actions)

| Workflow | When | What |
|---|---|---|
| `ci.yml` | every push / PR | Linux tests, plus a Windows build whose **packaged app** is tested |
| `release.yml` | push a `v*` tag (or run by hand) | builds, tests, publishes the zip and `SHA256SUMS.txt` as a GitHub Release with notes |
| `deps-update.yml` | **daily** at 05:23 UTC (or by hand) | if yt-dlp / yt-dlp-ejs / Deno / certifi have a new version: update `uv.lock`, run the tests, bump the patch version, commit, tag and publish the release |

yt-dlp has no fixed release schedule, so a daily check is how new versions get picked up. Live YouTube tests run in
CI but are informational only, because YouTube often bot-blocks cloud runners.

**Manual release:** `python scripts/bump_version.py minor`, commit, then `git tag v1.2.0 && git push --tags`.

The in-app updater reads releases from `GITHUB_REPO` in [`src/tubesnatch/__init__.py`](src/tubesnatch/__init__.py).

## Credits

TubeSnatch is a GUI over excellent open-source projects and services:

- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** does all extraction and downloading (Unlicense). **[yt-dlp-ejs](https://github.com/yt-dlp/ejs)** + **[Deno](https://deno.com)** solve YouTube's JS challenges.
- **[FFmpeg](https://ffmpeg.org)** handles merging, conversion, chapters, normalisation and cover art. Windows builds come from **[gyan.dev](https://www.gyan.dev/ffmpeg/builds/)**.
- **[SponsorBlock](https://sponsor.ajay.app)** provides community-submitted sponsor segments (optional feature, via yt-dlp).
- **[PyPI JSON API](https://pypi.org)** and the **[GitHub Releases API](https://docs.github.com/en/rest/releases)** power the update checks.
- **[Qt for Python / PySide6](https://doc.qt.io/qtforpython-6/)** provides the GUI. **[CPython](https://www.python.org)** is the bundled runtime. **[uv](https://github.com/astral-sh/uv)** and **[PyInstaller](https://pyinstaller.org)** handle packaging.
- The playlist-first workflow is inspired by **[Elephant](https://github.com/meowcateatrat/elephant)** by meowcateatrat.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for licenses. The same credits are in the app under **About & credits**.

## Disclaimer

Not affiliated with YouTube or Google. Only download content you have the right to download (your own uploads,
Creative Commons or public-domain material, or anything else you have permission for), and follow YouTube's Terms
of Service and your local copyright law.
