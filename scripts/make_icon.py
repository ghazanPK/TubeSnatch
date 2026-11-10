"""Render assets/icon.svg to a multi-size Windows .ico (uses Qt + Pillow-free path)."""

import struct
import sys
from io import BytesIO
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QGuiApplication, QIcon

src = Path(__file__).resolve().parents[1] / "src" / "tubesnatch" / "assets" / "icon.svg"
out = Path(sys.argv[1])

app = QGuiApplication([])
icon = QIcon(str(src))
sizes = [16, 24, 32, 48, 64, 128, 256]
pngs = []
for s in sizes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    icon.pixmap(s, s).toImage().save(buf, "PNG")
    pngs.append(bytes(ba))

# ICO container with embedded PNGs
data = BytesIO()
data.write(struct.pack("<HHH", 0, 1, len(sizes)))
offset = 6 + 16 * len(sizes)
for s, png in zip(sizes, pngs):
    d = 0 if s >= 256 else s
    data.write(struct.pack("<BBBBHHII", d, d, 0, 0, 1, 32, len(png), offset))
    offset += len(png)
for png in pngs:
    data.write(png)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(data.getvalue())
print(f"icon -> {out}")
