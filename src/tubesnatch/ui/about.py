"""About dialog with credits for every third-party project used."""

from __future__ import annotations

import PySide6
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QTextBrowser, QVBoxLayout

from .. import __version__, engine, paths

CREDITS_HTML = """
<style>
  h3 {{ color:#e8eaf2; margin: 14px 0 4px 0; }}
  p, li {{ color:#c4c8d8; line-height: 140%; }}
  a {{ color:#9d86ff; text-decoration:none; }}
  .muted {{ color:#8b91a7; }}
</style>
<p>TubeSnatch is a graphical front-end. It does not talk to YouTube itself: every
video lookup, download and conversion is handled by the open-source projects below.
Thank you to their authors and contributors.</p>

<h3>Download engine</h3>
<ul>
<li><a href="https://github.com/yt-dlp/yt-dlp"><b>yt-dlp</b></a> {ytdlp} — extracts metadata and
downloads video/audio streams. <span class="muted">The Unlicense (public domain).</span></li>
<li><a href="https://github.com/yt-dlp/ejs"><b>yt-dlp-ejs</b></a> — scripts yt-dlp runs to solve YouTube's
JavaScript challenges. <span class="muted">Unlicense / MIT / ISC.</span></li>
<li><a href="https://deno.com"><b>Deno</b></a> — the JavaScript runtime those scripts run in,
from the <a href="https://pypi.org/project/deno/">deno</a> PyPI package. <span class="muted">MIT License.</span></li>
</ul>

<h3>Online services</h3>
<ul>
<li><a href="https://sponsor.ajay.app"><b>SponsorBlock</b></a> — community-submitted sponsor segments, used only when
“Remove sponsor segments” is on (via yt-dlp). <span class="muted">Data under CC BY-NC-SA 4.0.</span></li>
<li><a href="https://pypi.org"><b>PyPI JSON API</b></a> — checks for new yt-dlp versions for the engine updater.</li>
<li><a href="https://docs.github.com/en/rest/releases"><b>GitHub Releases API</b></a> — checks for and downloads
new TubeSnatch releases.</li>
</ul>

<h3>Media processing</h3>
<ul>
<li><a href="https://ffmpeg.org"><b>FFmpeg</b></a> — merges video + audio, converts to MP3 and embeds
cover art and tags, normalises loudness and powers the Convert tab. <span class="muted">GPL-3.0 build from
<a href="https://www.gyan.dev/ffmpeg/builds/">gyan.dev</a>.</span></li>
<li><a href="https://github.com/quodlibet/mutagen"><b>mutagen</b></a> — audio tag handling.
<span class="muted">GPL-2.0-or-later.</span></li>
</ul>

<h3>User interface</h3>
<ul>
<li><a href="https://doc.qt.io/qtforpython-6/"><b>Qt for Python (PySide6)</b></a> {pyside} — the GUI toolkit.
<span class="muted">LGPL-3.0.</span></li>
<li><a href="https://www.python.org"><b>CPython</b></a> — the signed Python runtime the Windows app ships with.
<span class="muted">PSF License.</span></li>
<li><a href="https://github.com/astral-sh/uv"><b>uv</b></a> and <a href="https://pyinstaller.org"><b>PyInstaller</b></a> — environment management and packaging.
<span class="muted">MIT/Apache-2.0 · GPL-2.0 with bootloader exception.</span></li>
</ul>

<h3>Inspiration</h3>
<ul>
<li><a href="https://github.com/meowcateatrat/elephant"><b>Elephant</b></a> by meowcateatrat — a yt-dlp
front-end whose playlist-first workflow inspired this app. No code was copied.</li>
</ul>

<h3>Content &amp; trademarks</h3>
<p class="muted">Video titles, thumbnails and media belong to their creators and are fetched from
YouTube through yt-dlp. YouTube is a trademark of Google LLC; this app is not affiliated with or
endorsed by Google. Only download content you have the right to download, and respect
YouTube's Terms of Service and copyright law in your country.</p>
"""


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About TubeSnatch")
        self.resize(640, 620)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 20, 22, 16)
        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QIcon(str(paths.asset("icon.svg"))).pixmap(56, 56))
        head.addWidget(logo)
        t = QLabel(
            f"<span style='font-size:18pt;font-weight:800'>TubeSnatch</span><br>"
            f"<span style='color:#8b91a7'>Version {__version__} · built on yt-dlp {engine.ytdlp_version()}</span>"
        )
        t.setTextFormat(Qt.TextFormat.RichText)
        head.addWidget(t, 1)
        v.addLayout(head)
        tb = QTextBrowser()
        tb.setOpenExternalLinks(True)
        tb.setStyleSheet("QTextBrowser { background: #161922; border: 1px solid #272c3b; border-radius: 12px; padding: 10px; }")
        tb.setHtml(CREDITS_HTML.format(ytdlp=engine.ytdlp_version(), pyside=PySide6.__version__))
        v.addWidget(tb, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
