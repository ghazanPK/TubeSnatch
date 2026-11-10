# TubeSnatch

A desktop app for downloading YouTube **videos and whole playlists** as **MP4/MKV video** at the resolution you
choose, or as **MP3 audio** with cover art and tags. Under the hood it uses
[yt-dlp](https://github.com/yt-dlp/yt-dlp) and [FFmpeg](https://ffmpeg.org).

## Features

- Paste (or drag in) a video or playlist link and click **Fetch**. Every video lands in the download list with its thumbnail, title, channel and length.
- **Per-video control**: each row has its own *Format* (🎬 Video / 🎵 MP3) and *Quality* (resolution or bitrate).
  For a single video, the list shows only the resolutions it actually has.
- **Bulk actions for playlists**: check all or none, filter by title, **Apply default output to checked**, then
  **Download checked**.
- Parallel downloads (1 to 6), live per-row progress (size, speed, ETA), cancel, and retry by re-checking failed rows.
- MP4 prefers H.264 + AAC so files play everywhere. MKV keeps the best codec available (VP9/AV1).
- MP3 at 320/256/192/128 kbps or best VBR, with embedded cover art and tags.
- Playlist downloads can go into a folder named after the playlist, with files numbered `001 - Title.mp3`.
- Settings are remembered between runs. A log panel helps with troubleshooting.

## Using the Windows build

1. Unzip `TubeSnatch-<version>-win64-portable.zip` anywhere, for example `C:\Apps\TubeSnatch`.
2. Double-click **`TubeSnatch.lnk`**, or `TubeSnatch.cmd`. Nothing else needs installing: Python, FFmpeg and Deno are bundled.
3. Optional: run **`Create shortcuts.cmd`** to add TubeSnatch to the Desktop and Start menu. Run it again if you move the folder.

**Why a shortcut and not an `.exe`?** Windows 11's *Smart App Control* blocks any unsigned `.exe` that Microsoft
hasn't seen before, and that includes every self-built PyInstaller app. The portable build avoids this by running
the app on the official python.org Python (`runtime\pythonw.exe`, signed by the Python Software Foundation),
with FFmpeg from gyan.dev and Deno, which Smart App Control already trusts.

> If you copy the zip to another PC through a browser or chat app, Windows may mark it as "from the internet".
> Before unzipping, right-click the zip, open **Properties**, and tick **Unblock**.

## Development (WSL)

Requirements in WSL (Ubuntu): [uv](https://docs.astral.sh/uv/) and `ffmpeg` (`sudo apt install ffmpeg`).
WSLg shows the window on your Windows desktop.

```bash
./scripts/dev.sh                       # creates ~/.venvs/tubesnatch and launches the app
./scripts/dev.sh "https://youtube.com/playlist?list=..."   # launch and fetch straight away
```

The Linux virtualenv lives outside the repo (`~/.venvs/tubesnatch`) so it never clashes with the Windows build env.

### Project layout

```
src/tubesnatch/
  engine.py          yt-dlp wrapper (probe, build options, download with progress/cancel). No Qt here.
  paths.py           finds bundled ffmpeg / deno (Windows builds) or system ones (dev)
  ui/main_window.py  the window: URL bar, preview card, default options, download list
  ui/workers.py      QRunnable workers that run engine calls off the UI thread
  ui/theme.py        the dark coral→violet stylesheet
  ui/about.py        About dialog with credits
scripts/
  dev.sh             run from source in WSL
  build_windows.sh   build the Windows package from WSL (calls build_windows.ps1)
  build_windows.ps1  the actual Windows build (portable runtime, or PyInstaller with -PyInstaller)
  make_icon.py       renders assets/icon.svg into a multi-size .ico
tubesnatch.spec      PyInstaller spec (only for the -PyInstaller flavour)
```

## Building the Windows package

From WSL:

```bash
./scripts/build_windows.sh               # or: ./scripts/build_windows.sh -UpdateYtDlp
```

Or from PowerShell: `powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1`.

Windows binaries can't be built from Linux, so the script hands the build to Windows PowerShell. It still installs
nothing system-wide. Everything it downloads is cached under `.build\`:

- a portable `uv.exe` ([astral-sh/uv](https://github.com/astral-sh/uv)) that installs the locked dependencies
- the signed CPython 3.13 from python.org's [NuGet package](https://www.nuget.org/packages/python)
- FFmpeg's release "essentials" build from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/)

Output:

- `dist\TubeSnatch\`, the app folder (`TubeSnatch.lnk`, `runtime\`, `bin\`), about 440 MB
- `dist\TubeSnatch-<version>-win64-portable.zip`, about 170 MB, ready to share

Options: `-UpdateYtDlp` (see below), `-Clean` (re-download everything), and `-PyInstaller`, which builds a classic
`TubeSnatch.exe` folder instead. Use that one only for PCs without Smart App Control, because SAC blocks it.

### Keeping it working

YouTube changes often and yt-dlp releases fixes frequently. If downloads start failing, rebuild with
`-UpdateYtDlp`. That upgrades yt-dlp, yt-dlp-ejs and Deno in `uv.lock` before building.

## Credits

TubeSnatch is a thin GUI over excellent open-source work:

- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** does all the extraction and downloading (Unlicense).
- **[yt-dlp-ejs](https://github.com/yt-dlp/ejs)** and **[Deno](https://deno.com)** solve YouTube's JavaScript challenges.
- **[FFmpeg](https://ffmpeg.org)** handles merging, MP3 conversion and cover art. The Windows build ships [gyan.dev](https://www.gyan.dev/ffmpeg/builds/)'s build.
- **[Qt for Python / PySide6](https://doc.qt.io/qtforpython-6/)** provides the GUI.
- **[CPython](https://www.python.org)** is the bundled runtime. **[uv](https://github.com/astral-sh/uv)** and **[PyInstaller](https://pyinstaller.org)** handle environments and packaging.
- UI workflow inspired by **[Elephant](https://github.com/meowcateatrat/elephant)** by meowcateatrat.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for licenses. The same credits are in the app under **About & credits**.

## Disclaimer

Not affiliated with YouTube or Google. Only download content you have the right to download (your own uploads,
Creative Commons or public-domain material, or anything else you have permission for), and follow YouTube's Terms
of Service and your local copyright law.
