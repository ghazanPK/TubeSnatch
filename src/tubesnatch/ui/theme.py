"""Dark theme with a coral → violet accent."""

ACCENT_A = "#ff4d6d"
ACCENT_B = "#7c5cff"
BG = "#0e1016"
SURFACE = "#161922"
SURFACE_2 = "#1d2130"
BORDER = "#272c3b"
TEXT = "#e8eaf2"
MUTED = "#8b91a7"
SUCCESS = "#34d399"
ERROR = "#f87171"

GRADIENT = f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT_A}, stop:1 {ACCENT_B})"
GRADIENT_HOVER = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff6b85, stop:1 #957bff)"

QSS = f"""
* {{
    font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", sans-serif;
    font-size: 10pt;
    color: {TEXT};
}}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget#central {{ background: {BG}; }}
QToolTip {{ background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px; border-radius: 6px; }}

QFrame#card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QLabel {{ background: transparent; }}
QLabel#brand {{ font-size: 20pt; font-weight: 800; letter-spacing: 0.5px; }}
QLabel#tagline, QLabel#muted {{ color: {MUTED}; }}
QLabel#sectionTitle {{ color: {MUTED}; font-size: 8.5pt; font-weight: 700; letter-spacing: 1.5px; }}
QLabel#heroTitle {{ font-size: 15pt; font-weight: 700; }}
QLabel#pill {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 10px;
    padding: 2px 10px; color: {MUTED}; font-size: 9pt;
}}
QLabel#error {{ color: {ERROR}; }}
QLabel#ok {{ color: {SUCCESS}; }}
QLabel a {{ color: {ACCENT_B}; }}

QLineEdit, QComboBox, QSpinBox {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 7px 10px;
    selection-background-color: {ACCENT_B};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {ACCENT_B}; }}
QLineEdit#urlInput {{ font-size: 11.5pt; padding: 11px 14px; border-radius: 11px; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url(__CHEVRON__); width: 12px; height: 12px; margin-right: 8px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px;
    selection-background-color: {ACCENT_B}; outline: 0; padding: 4px;
}}
QComboBox#cellCombo {{ padding: 3px 8px; border-radius: 7px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}

QPushButton {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 7px 14px;
    font-weight: 600;
}}
QPushButton:hover {{ border-color: {ACCENT_B}; background: #242a3c; }}
QPushButton:pressed {{ background: #151925; }}
QPushButton:disabled {{ color: #5b6075; border-color: #20242f; background: #171a23; }}
QPushButton#primary {{
    background: {GRADIENT}; border: none; color: white; padding: 9px 20px; font-size: 10.5pt;
}}
QPushButton#primary:hover {{ background: {GRADIENT_HOVER}; }}
QPushButton#primary:disabled {{ background: #3a3550; color: #a9a3c4; }}
QPushButton#danger:hover {{ border-color: {ERROR}; color: {ERROR}; }}
QPushButton#cellBtn {{ padding: 4px 8px; border-radius: 7px; font-weight: 600; }}
QPushButton#ghost {{ background: transparent; border: none; color: {MUTED}; padding: 6px 10px; }}
QPushButton#ghost:hover {{ color: {TEXT}; }}

QPushButton#segment {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; padding: 8px 16px; border-radius: 0px;
}}
QPushButton#segment[pos="left"] {{ border-top-left-radius: 9px; border-bottom-left-radius: 9px; }}
QPushButton#segment[pos="right"] {{ border-top-right-radius: 9px; border-bottom-right-radius: 9px; border-left: none; }}
QPushButton#segment:checked {{ background: {GRADIENT}; color: white; border-color: transparent; }}

QPushButton#nav {{
    background: transparent; border: 1px solid transparent; border-radius: 10px; padding: 8px 16px;
    color: {MUTED}; font-size: 10.5pt;
}}
QPushButton#nav:hover {{ color: {TEXT}; background: {SURFACE}; }}
QPushButton#nav:checked {{ color: {TEXT}; background: {SURFACE_2}; border: 1px solid {BORDER};
    border-bottom: 2px solid {ACCENT_A}; }}
QPushButton#badge {{
    background: rgba(124, 92, 255, 0.18); border: 1px solid {ACCENT_B}; color: #cfc4ff;
    border-radius: 14px; padding: 6px 14px;
}}
QPushButton#badge:hover {{ background: rgba(124, 92, 255, 0.32); }}
QLabel#dropZone {{
    border: 2px dashed #343a4f; border-radius: 14px; color: {MUTED}; font-size: 11pt; padding: 30px;
}}
QRadioButton {{ spacing: 8px; background: transparent; }}
QRadioButton::indicator {{ width: 16px; height: 16px; border-radius: 9px; border: 1px solid #4a5068;
    background: {SURFACE_2}; }}
QRadioButton::indicator:checked {{ border: 5px solid {ACCENT_B}; background: white; }}
QMessageBox QLabel {{ min-width: 320px; }}

QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 5px; border: 1px solid #3a4054; background: {SURFACE_2};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT_B}; }}
QCheckBox::indicator:checked {{ background: {ACCENT_B}; border-color: {ACCENT_B};
    image: url(__CHECK__); }}

QTableWidget {{
    background: {SURFACE};
    alternate-background-color: #191c26;
    border: none;
    gridline-color: transparent;
    selection-background-color: #2a2550;
    selection-color: {TEXT};
    outline: 0;
}}
QTableWidget::item {{ padding: 4px; border-bottom: 1px solid #1f2330; }}
QTableView::indicator {{
    width: 16px; height: 16px; border-radius: 5px; border: 1px solid #4a5068; background: {SURFACE_2};
}}
QTableView::indicator:hover {{ border-color: {ACCENT_B}; }}
QTableView::indicator:checked {{ background: {ACCENT_B}; border-color: {ACCENT_B}; image: url(__CHECK__); }}
QHeaderView::section {{
    background: {SURFACE}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
    padding: 8px 6px; font-weight: 700; font-size: 8.5pt;
}}
QTableCornerButton::section {{ background: {SURFACE}; border: none; }}

QProgressBar {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 7px;
    text-align: center; color: {TEXT}; font-size: 8.5pt; min-height: 18px;
}}
QProgressBar::chunk {{ background: {GRADIENT}; border-radius: 6px; }}
QProgressBar[state="done"]::chunk {{ background: {SUCCESS}; }}
QProgressBar[state="error"]::chunk {{ background: {ERROR}; }}
QProgressBar#overall {{ min-height: 8px; max-height: 8px; border: none; border-radius: 4px; }}

QPlainTextEdit {{
    background: #0b0d12; border: 1px solid {BORDER}; border-radius: 10px;
    font-family: "Cascadia Mono", "Consolas", monospace; font-size: 9pt; color: #b8bdd0;
}}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #2f3446; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #454b62; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #2f3446; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle {{ background: transparent; }}
QStatusBar {{ background: {BG}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QStatusBar QLabel {{ color: {MUTED}; padding: 0 6px; }}
"""


def stylesheet(assets_dir: str) -> str:
    base = assets_dir.replace("\\", "/").rstrip("/")
    return QSS.replace("__CHECK__", f"{base}/check.svg").replace("__CHEVRON__", f"{base}/chevron.svg")
