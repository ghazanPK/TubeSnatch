"""Shared small widgets and helpers."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPainterPath, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from .. import __version__
from . import theme


def card() -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    shadow = QGraphicsDropShadowEffect(f)
    shadow.setBlurRadius(28)
    shadow.setOffset(0, 6)
    shadow.setColor(QColor(0, 0, 0, 110))
    f.setGraphicsEffect(shadow)
    return f


def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(wrap)
    return lb


def button(text: str, name: str | None = None, tip: str | None = None) -> QPushButton:
    b = QPushButton(text)
    if name:
        b.setObjectName(name)
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)


def rounded(pix: QPixmap, w: int, h: int, radius: int) -> QPixmap:
    scaled = pix.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    x = (scaled.width() - w) // 2
    y = (scaled.height() - h) // 2
    scaled = scaled.copy(x, y, w, h)
    out = QPixmap(w, h)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, w, h, radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, scaled)
    p.end()
    return out


def placeholder_pix(w: int, h: int, radius: int) -> QPixmap:
    out = QPixmap(w, h)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(theme.SURFACE_2))
    p.drawRoundedRect(0, 0, w, h, radius, radius)
    p.end()
    return out


class ThumbLoader:
    """Async thumbnail fetcher with an in-memory cache."""

    def __init__(self, parent):
        self.nam = QNetworkAccessManager(parent)
        self.cache: dict[str, QPixmap] = {}
        self.waiting: dict[str, list] = {}

    def get(self, url: str | None, callback) -> None:
        if not url:
            return
        if url in self.cache:
            callback(self.cache[url])
            return
        if url in self.waiting:
            self.waiting[url].append(callback)
            return
        self.waiting[url] = [callback]
        req = QNetworkRequest(QUrl(url))
        req.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, f"TubeSnatch/{__version__}")
        reply = self.nam.get(req)
        reply.finished.connect(lambda r=reply, u=url: self._done(r, u))

    def _done(self, reply: QNetworkReply, url: str) -> None:
        pix = QPixmap()
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pix.loadFromData(reply.readAll())
        reply.deleteLater()
        callbacks = self.waiting.pop(url, [])
        if pix.isNull():
            return
        self.cache[url] = pix
        for cb in callbacks:
            try:
                cb(pix)
            except RuntimeError:  # widget already deleted
                pass


def centered(w: QWidget, margins: int = 6) -> QWidget:
    holder = QWidget()
    lay = QHBoxLayout(holder)
    lay.setContentsMargins(margins, 0, margins, 0)
    w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    lay.addWidget(w)
    holder.setProperty("inner", w)
    return holder


def select_data(combo: QComboBox, value) -> bool:
    for i in range(combo.count()):
        if combo.itemData(i) == value:
            combo.setCurrentIndex(i)
            return True
    return False


def height_label(h: int) -> str:
    tag = {2160: " 4K", 1440: " 2K", 1080: " FHD", 720: " HD"}.get(h, "")
    return f"{h}p{tag}"


def nearest_height(target: int, available: list[int]) -> int:
    if not target or not available:
        return target
    lower = [h for h in available if h <= target]
    return max(lower) if lower else min(available)


def reveal(path: str) -> None:
    p = Path(path)
    if sys.platform == "win32":
        if p.is_dir():
            subprocess.Popen(["explorer", os.path.normpath(path)])
        else:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p if p.is_dir() else p.parent)))


def open_folder(path: str) -> None:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
