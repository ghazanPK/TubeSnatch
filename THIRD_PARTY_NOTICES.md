# Third-party software & credits

TubeSnatch is a graphical front-end. It does not contact YouTube directly. All extraction, downloading and
conversion is done by the projects below, which are bundled in the Windows build. Thanks to their authors.

| Project | What it does in TubeSnatch | License | Link |
|---|---|---|---|
| **yt-dlp** | Extracts video and playlist metadata, picks formats, downloads streams, runs FFmpeg post-processing | The Unlicense | https://github.com/yt-dlp/yt-dlp |
| **yt-dlp-ejs** | JavaScript challenge solver scripts yt-dlp needs for YouTube | Unlicense, plus MIT/ISC for bundled parts | https://github.com/yt-dlp/ejs |
| **Deno** (PyPI `deno` package) | JavaScript runtime that runs the yt-dlp-ejs scripts | MIT | https://deno.com · https://pypi.org/project/deno/ |
| **FFmpeg** (gyan.dev release "essentials" build) | Merges video and audio, converts to MP3, embeds cover art and tags | GPL-3.0 (this build), see `FFMPEG_LICENSE.txt` | https://ffmpeg.org · https://www.gyan.dev/ffmpeg/builds/ |
| **Qt / Qt for Python (PySide6)** | GUI toolkit | LGPL-3.0 | https://doc.qt.io/qtforpython-6/ |
| **mutagen** | Audio metadata (used by yt-dlp) | GPL-2.0-or-later | https://github.com/quodlibet/mutagen |
| **requests, urllib3, certifi, brotli, websockets** | Networking helpers used by yt-dlp | Apache-2.0 / MIT / MPL-2.0 / BSD | see each project on PyPI |
| **CPython** (python.org NuGet package) | The signed Python runtime in the portable Windows build | PSF License | https://www.python.org |
| **PyInstaller** (optional build) | Packages the alternative single-exe Windows build | GPL-2.0 with bootloader exception | https://pyinstaller.org |
| **uv** (build time only) | Python and dependency management for the build | MIT / Apache-2.0 | https://github.com/astral-sh/uv |

## Inspiration

- **Elephant** by meowcateatrat (https://github.com/meowcateatrat/elephant), a yt-dlp front-end. Its playlist-first
  workflow inspired this app. No code was copied.

## Source code for LGPL/GPL components

Qt for Python (LGPL-3.0) is used as unmodified shared libraries (`PySide6\*.dll`, `Qt6*.dll`) inside the app folder,
so you can swap them for your own build. FFmpeg's source is available from https://ffmpeg.org, and the build
configuration is documented at https://www.gyan.dev/ffmpeg/builds/.

## Content & trademarks

Video titles, thumbnails and media belong to their creators and are fetched from YouTube through yt-dlp.
YouTube is a trademark of Google LLC. TubeSnatch is not affiliated with or endorsed by Google.
Only download content you have the right to download, and follow YouTube's Terms of Service and the copyright
law where you live.
