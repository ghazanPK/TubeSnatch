"""Per-video options: trim to a time range, or split by chapters."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
)

from .. import engine
from .widgets import label


class RowOptionsDialog(QDialog):
    """Returns (trim, split_chapters): trim is (start, end|None) or None."""

    def __init__(self, parent, title: str, duration: float | None, trim, split_chapters: bool):
        super().__init__(parent)
        self.setWindowTitle("Video options")
        self.setMinimumWidth(460)
        self.duration = duration
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 14)
        v.setSpacing(12)
        t = label(title, "heroTitle", wrap=True)
        v.addWidget(t)
        v.addWidget(label(f"Length: {engine.fmt_duration(duration)}", "muted"))

        self.r_full = QRadioButton("Whole video")
        self.r_trim = QRadioButton("✂  Only part of it (trim)")
        self.r_chap = QRadioButton("📑  Split into one file per chapter")
        self.r_chap.setToolTip("Great for albums and mixes uploaded as one video. Needs the video to have chapters.")
        grp = QButtonGroup(self)
        for r in (self.r_full, self.r_trim, self.r_chap):
            grp.addButton(r)
            v.addWidget(r)

        form = QFormLayout()
        form.setContentsMargins(28, 0, 0, 0)
        self.start = QLineEdit()
        self.start.setPlaceholderText("0:00")
        self.end = QLineEdit()
        self.end.setPlaceholderText(engine.fmt_duration(duration) if duration else "end")
        row = QHBoxLayout()
        row.addWidget(self.start)
        row.addWidget(label("to"))
        row.addWidget(self.end)
        form.addRow("From", row)
        form.addRow("", label("Times as 1:23, 1:02:03 or seconds. Leave the end empty to go to the end.", "muted", wrap=True))
        v.addLayout(form)

        self.err = label("", "error", wrap=True)
        v.addWidget(self.err)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

        if trim:
            self.r_trim.setChecked(True)
            self.start.setText(engine.fmt_duration(trim[0]))
            if trim[1] is not None:
                self.end.setText(engine.fmt_duration(trim[1]))
        elif split_chapters:
            self.r_chap.setChecked(True)
        else:
            self.r_full.setChecked(True)
        for r in (self.r_full, self.r_trim, self.r_chap):
            r.toggled.connect(self._sync)
        self.start.textEdited.connect(lambda _t: self.r_trim.setChecked(True))
        self.end.textEdited.connect(lambda _t: self.r_trim.setChecked(True))
        self._sync()
        self.result_value = (trim, split_chapters)

    def _sync(self):
        on = self.r_trim.isChecked()
        self.start.setEnabled(True)
        self.end.setEnabled(True)
        if not on:
            self.err.setText("")

    def _accept(self):
        if self.r_trim.isChecked():
            try:
                s = engine.parse_time(self.start.text()) or 0.0
                e = engine.parse_time(self.end.text())
            except ValueError as ex:
                self.err.setText(str(ex))
                return
            if e is not None and e <= s:
                self.err.setText("The end must be after the start.")
                return
            if self.duration and s >= self.duration:
                self.err.setText("The start is past the end of the video.")
                return
            if self.duration and e is not None and e >= self.duration:
                e = None
            if s == 0 and e is None:
                self.result_value = (None, False)
            else:
                self.result_value = ((s, e), False)
        else:
            self.result_value = (None, self.r_chap.isChecked())
        self.accept()
