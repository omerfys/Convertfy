"""Persistent settings + the Settings and Welcome windows."""
from __future__ import annotations

import sys

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QSlider, QVBoxLayout)

from . import __version__, glass
from .util import CONFIG
from .window import GlassWindow

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
APP = "Convertfy"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

DEFAULTS = {
    "output": "next",
    "jpg_quality": 90,
    "pdf_dpi": 200,
    "trigger": "shift",
    "welcomed": False,
    "theme": "neon",
}

class Settings:
    def __init__(self):
        self.q = QSettings(APP, APP)

    def get(self, key):
        v = self.q.value(key, DEFAULTS[key])
        d = DEFAULTS[key]
        if isinstance(d, bool):
            return v in (True, "true", "1", 1)
        if isinstance(d, int):
            try:
                return int(v)
            except (TypeError, ValueError):
                return d
        return v

    def set(self, key, value):
        self.q.setValue(key, value)
        self.apply()

    def apply(self):
        for k in ("output", "jpg_quality", "pdf_dpi"):
            CONFIG[k] = self.get(k)
        glass.apply_theme(self.get("theme"))
# ---------------------------------------------------------------- autostart (Windows)
def launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --quiet'
    return f'"{sys.executable}" -m convertfy --quiet'


def autostart_enabled() -> bool:
    if IS_LINUX:
        from . import platform_linux
        return platform_linux.autostart_enabled()
    if IS_MAC:
        from . import platform_mac
        return platform_mac.autostart_enabled()
    if not IS_WIN:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP)
            return True
    except OSError:
        return False


def set_autostart(on: bool):
    if IS_LINUX:
        from . import platform_linux
        platform_linux.set_autostart(on)
        return
    if IS_MAC:
        from . import platform_mac
        platform_mac.set_autostart(on)
        return
    if not IS_WIN:
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(k, APP)
            except OSError:
                pass


TRIGGERS = ([("shift", "Shift ⇧"), ("ctrl", "Control ⌃"), ("alt", "Option ⌥")] if IS_MAC
            else [("shift", "Shift"), ("ctrl", "Ctrl"), ("alt", "Alt")])
OUTPUTS = [("next", "Next to the original"), ("folder", "In a “Convertfy” subfolder")]
DPIS = [(150, "150 dpi · small"), (200, "200 dpi · balanced"), (300, "300 dpi · print")]


class SettingsWindow(GlassWindow):
    changed = Signal()

    def __init__(self, settings: Settings):
        super().__init__("Settings & Preferences", size=(580, 560))
        self.s = settings

        def card() -> tuple[QFrame, QVBoxLayout]:
            box = QFrame()
            box.setObjectName("glassCard")
            lay = QVBoxLayout(box)
            lay.setContentsMargins(14, 12, 14, 12)
            lay.setSpacing(10)
            return box, lay

        def combo(options, current):
            c = QComboBox()
            for v, label in options:
                c.addItem(label, v)
            idx = max(0, [v for v, _ in options].index(current) if current in [v for v, _ in options] else 0)
            c.setCurrentIndex(idx)
            return c

        # Card 1: Theme & Style
        c1, l1 = card()
        l1.addWidget(QLabel("GLASS THEME & ACCENT"))
        t_row = QHBoxLayout()
        t_row.setSpacing(8)
        self.theme_btns = {}
        current_theme = self.s.get("theme")
        for t_key, t_info in glass.THEMES.items():
            btn = QPushButton(t_info["name"].split(" ")[0])
            btn.setObjectName("pill")
            btn.setCheckable(True)
            btn.setChecked(t_key == current_theme)
            btn.setToolTip(t_info["name"])
            btn.clicked.connect(lambda _, k=t_key: self._set_theme(k))
            self.theme_btns[t_key] = btn
            t_row.addWidget(btn)
        l1.addLayout(t_row)
        self.body.addWidget(c1)

        # Card 2: Workflow & Trigger
        c2, l2 = card()
        l2.addWidget(QLabel("WORKFLOW & TRIGGER"))
        g2 = QGridLayout()
        g2.setHorizontalSpacing(14)
        g2.setVerticalSpacing(8)

        g2.addWidget(QLabel("Trigger Key"), 0, 0)
        self.trigger = combo(TRIGGERS, self.s.get("trigger"))
        self.trigger.currentIndexChanged.connect(lambda _: self._save("trigger", self.trigger.currentData()))
        g2.addWidget(self.trigger, 0, 1)

        g2.addWidget(QLabel("Save Destination"), 1, 0)
        self.output = combo(OUTPUTS, self.s.get("output"))
        self.output.currentIndexChanged.connect(lambda _: self._save("output", self.output.currentData()))
        g2.addWidget(self.output, 1, 1)
        l2.addLayout(g2)
        self.body.addWidget(c2)

        # Card 3: Quality & Presets
        c3, l3 = card()
        l3.addWidget(QLabel("CONVERSION & IMAGE QUALITY"))
        g3 = QGridLayout()
        g3.setHorizontalSpacing(14)
        g3.setVerticalSpacing(8)

        g3.addWidget(QLabel("JPG / WebP Quality"), 0, 0)
        q_row = QHBoxLayout()
        self.q = QSlider(Qt.Horizontal)
        self.q.setRange(50, 100)
        self.q.setValue(self.s.get("jpg_quality"))
        self.qv = QLabel(f"{self.q.value()}%")
        self.qv.setObjectName("dim")
        self.qv.setFixedWidth(42)
        self.q.valueChanged.connect(lambda v: (self.qv.setText(f"{v}%"), self._save("jpg_quality", v)))
        q_row.addWidget(self.q)
        q_row.addWidget(self.qv)

        # quick preset buttons
        p_row = QHBoxLayout()
        p_row.setSpacing(6)
        for val, name in ((75, "Web"), (90, "Balanced"), (98, "Ultra")):
            p_btn = QPushButton(f"{name} ({val}%)")
            p_btn.setObjectName("pill")
            p_btn.clicked.connect(lambda _, v=val: self.q.setValue(v))
            p_row.addWidget(p_btn)
        p_row.addStretch(1)

        q_vbox = QVBoxLayout()
        q_vbox.addLayout(q_row)
        q_vbox.addLayout(p_row)
        g3.addLayout(q_vbox, 0, 1)

        g3.addWidget(QLabel("PDF → Image DPI"), 1, 0)
        self.dpi = combo(DPIS, self.s.get("pdf_dpi"))
        self.dpi.currentIndexChanged.connect(lambda _: self._save("pdf_dpi", self.dpi.currentData()))
        g3.addWidget(self.dpi, 1, 1)
        l3.addLayout(g3)
        self.body.addWidget(c3)

        # Card 4: System
        if IS_WIN or IS_MAC or IS_LINUX:
            c4, l4 = card()
            l4.addWidget(QLabel("SYSTEM INTEGRATION"))
            self.auto = QCheckBox("Start Convertfy automatically on system sign-in")
            self.auto.setChecked(autostart_enabled())
            self.auto.toggled.connect(set_autostart)
            l4.addWidget(self.auto)
            if IS_MAC:
                from . import platform_mac
                if not platform_mac.has_screen_recording():
                    glass_btn = QPushButton("Enable Full Liquid Glass…")
                    glass_btn.setToolTip("Lets the glass refract windows behind it (Screen Recording permission)")
                    glass_btn.clicked.connect(platform_mac.request_screen_recording)
                    l4.addWidget(glass_btn)
            self.body.addWidget(c4)

        self.body.addStretch(1)

        # Footer bar
        foot = QHBoxLayout()
        about = QLabel(f"Convertfy {__version__}  ·  Original files are never overwritten")
        about.setObjectName("dim")
        foot.addWidget(about)
        foot.addStretch(1)
        done = QPushButton("Save & Close")
        done.setObjectName("primary")
        done.clicked.connect(self.close)
        foot.addWidget(done)
        self.body.addLayout(foot)

    def _set_theme(self, theme_key: str):
        self.s.set("theme", theme_key)
        glass.apply_theme(theme_key)
        for k, b in self.theme_btns.items():
            b.setChecked(k == theme_key)
        self.setStyleSheet(glass.QSS)
        self.changed.emit()
        self.update()

    def _save(self, key, value):
        self.s.set(key, value)
        self.changed.emit()


class WelcomeWindow(GlassWindow):
    def __init__(self, settings: Settings, trigger_label: str = "Shift"):
        super().__init__("Welcome to Convertfy", size=(580, 480))
        self.s = settings

        intro = QLabel("The fast, liquid-glass radial converter & editor.")
        intro.setObjectName("dim")
        self.body.addWidget(intro)

        steps = [
            ("1", "Start dragging any file",
             "In Finder or desktop" if IS_MAC else
             "In Thunar, Nautilus, or desktop" if IS_LINUX else
             "In File Explorer or on the desktop"),
            ("2", f"Press {trigger_label} while dragging",
             "The liquid-glass radial menu blooms instantly under your cursor"),
            ("3", "Drop onto any slice",
             "Converted output or tool saves beside original, never overwriting"),
            ("⇄", f"Tap {trigger_label} again to switch rings",
             "Quickly toggle between Convert (formats) and Tools (editing & filters)"),
        ]

        card_box = QFrame()
        card_box.setObjectName("glassCard")
        card_lay = QVBoxLayout(card_box)
        card_lay.setContentsMargins(14, 10, 14, 10)
        card_lay.setSpacing(12)

        for n, head, sub in steps:
            row = QHBoxLayout()
            row.setSpacing(12)
            badge = QLabel(n)
            badge.setAlignment(Qt.AlignCenter)
            badge.setFixedSize(36, 36)
            badge.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #00f5d4, stop:1 #00bbf9);"
                                "border-radius: 18px; font-weight: 800; font-size: 12pt; color: #070a14;")
            row.addWidget(badge)
            col = QVBoxLayout()
            col.setSpacing(1)
            h = QLabel(head)
            h.setStyleSheet("font-size: 11pt; font-weight: 700;")
            d = QLabel(sub)
            d.setObjectName("dim")
            col.addWidget(h)
            col.addWidget(d)
            row.addLayout(col, 1)
            card_lay.addLayout(row)

        self.body.addWidget(card_box)
        self.body.addStretch(1)

        foot = QHBoxLayout()
        if IS_WIN or IS_MAC or IS_LINUX:
            self.auto = QCheckBox("Start Convertfy at login")
            self.auto.setChecked(True)
            foot.addWidget(self.auto)
        foot.addStretch(1)
        b = QPushButton("Get Started")
        b.setObjectName("primary")
        b.clicked.connect(self._done)
        foot.addWidget(b)
        self.body.addLayout(foot)

    def _done(self):
        self.s.set("welcomed", True)
        if hasattr(self, "auto") and self.auto.isChecked():
            set_autostart(True)
        self.close()
