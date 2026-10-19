"""Watches for "left button held + mouse moved + Shift pressed" anywhere on screen, which
is what a Shift+drag of a file looks like. Polling global input state is simple, needs no
admin rights and can't stall the system the way a broken hook can.
Windows: GetAsyncKeyState. macOS: NSEvent.pressedMouseButtons / modifierFlags (no
Accessibility or Input Monitoring permission required)."""
from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import QObject, QPoint, QTimer, Signal
from PySide6.QtGui import QCursor

VK_LBUTTON, VK_SHIFT, VK_ESCAPE = 0x01, 0x10, 0x1B
DRAG_THRESHOLD = 10   # px the mouse must travel with the button held
NO_DRAG_TIMEOUT = 50  # ticks (≈ 0.75 s) to wait for a file drag to enter before hiding


class ConvertfyWatcher(QObject):
    show_menu = Signal(QPoint)
    toggle_ring = Signal()
    hide_menu = Signal()

    def __init__(self, menu_visible, menu_got_drag, parent=None):
        super().__init__(parent)
        self.menu_visible = menu_visible
        self.menu_got_drag = menu_got_drag
        self.enabled = True
        self.vk = VK_SHIFT
        self.key_name = "shift"
        self._down_at: QPoint | None = None
        self._shift_was = False
        self._fired = False
        self._idle_ticks = 0
        self._shown_at = QPoint()
        self._can_trigger = False
        self._user32 = ctypes.windll.user32 if sys.platform == "win32" else None
        self._kernel32 = ctypes.windll.kernel32 if sys.platform == "win32" else None
        self._mac = None
        if sys.platform == "darwin":
            from . import platform_mac
            self._mac = platform_mac if platform_mac.OK else None
        elif sys.platform.startswith("linux"):
            from . import platform_linux
            # same interface as platform_mac: left_button_down / key_down / escape_down
            self._mac = platform_linux if platform_linux.available() else None
        self.timer = QTimer(self, interval=15, timeout=self._tick)

    def set_key(self, name: str):
        self.key_name = name
        self.vk = {"shift": VK_SHIFT, "ctrl": 0x11, "alt": 0x12}.get(name, VK_SHIFT)

    def start(self):
        if self._user32 is not None or self._mac is not None:
            self.timer.start()

    def _down(self, vk: int) -> bool:
        return bool(self._user32.GetAsyncKeyState(vk) & 0x8000)

    def _state(self) -> tuple[bool, bool, bool]:
        """(left button, trigger key, escape)"""
        if self._mac is not None:
            m = self._mac
            return m.left_button_down(), m.key_down(self.key_name), m.escape_down()
        return self._down(VK_LBUTTON), self._down(self.vk), self._down(VK_ESCAPE)

    def _tick(self):
        lbtn, shift, esc = self._state()
        pos = QCursor.pos()

        if self.menu_visible():
            if not lbtn or esc:
                # drop happened (or was cancelled) – give the drop event a moment to land
                QTimer.singleShot(120, self.hide_menu.emit)
            elif shift and not self._shift_was and self.menu_got_drag():
                self.toggle_ring.emit()       # tap Shift again to flip Convert ⇄ Tools
            elif not self.menu_got_drag() and (pos - self._shown_at).manhattanLength() > 6:
                # the cursor is moving over us but no file drag arrived: it's a window
                # move or text selection, so get out of the way
                self._idle_ticks += 1
                if self._idle_ticks > NO_DRAG_TIMEOUT:
                    self.hide_menu.emit()
        else:
            if lbtn:
                if self._down_at is None:
                    self._down_at = pos
                    self._fired = False
                    self._can_trigger = self._is_desktop_or_file_manager(pos)
                moved = (pos - self._down_at).manhattanLength() >= DRAG_THRESHOLD
                if self.enabled and self._can_trigger and moved and shift and not self._fired:
                    self._fired = True
                    self._idle_ticks = 0
                    self._shown_at = pos
                    self.show_menu.emit(pos)
            else:
                self._down_at = None
                self._fired = False
                self._can_trigger = False
        self._shift_was = shift

    def _is_desktop_or_file_manager(self, pos: QPoint) -> bool:
        """Only permit radial menu to trigger from Desktop or File Explorer; suppress in games."""
        if sys.platform == "win32":
            return self._win_is_desktop_or_explorer(pos)
        if sys.platform == "darwin":
            return self._mac_is_finder()
        if sys.platform.startswith("linux"):
            return self._linux_is_file_manager()
        return True

    def _win_is_desktop_or_explorer(self, pos: QPoint) -> bool:
        if self._user32 is None:
            return True
        try:
            from ctypes import wintypes
            # 1. Fullscreen game detection: if foreground window covers screen and is not desktop, block
            fg = self._user32.GetForegroundWindow()
            if fg and self._win_is_fullscreen_game(fg):
                return False

            # 2. Check window under cursor
            class POINT(ctypes.Structure):
                _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]
            pt = POINT(pos.x(), pos.y())
            hwnd = self._user32.WindowFromPoint(pt)
            if not hwnd:
                return False

            ALLOWED_CLASSES = {
                "Progman", "WorkerW", "CabinetWClass", "ExploreWClass",
                "SHELLDLL_DefView", "SysListView32", "Shell_TrayWnd",
                "Shell_SecondaryTrayWnd"
            }

            buf = ctypes.create_unicode_buffer(256)
            self._user32.GetClassNameW(hwnd, buf, 256)
            if buf.value in ALLOWED_CLASSES:
                return True

            GA_ROOT = 2
            root = self._user32.GetAncestor(hwnd, GA_ROOT)
            if root:
                self._user32.GetClassNameW(root, buf, 256)
                if buf.value in ALLOWED_CLASSES:
                    return True

            pname = self._win_process_name(hwnd)
            ALLOWED_PROCS = {
                "explorer.exe", "totalcmd.exe", "totalcmd64.exe",
                "dopus.exe", "files.exe", "onecommander.exe",
                "convertfy.exe", "python.exe", "pythonw.exe"
            }
            return pname in ALLOWED_PROCS
        except Exception:
            return True

    def _win_is_fullscreen_game(self, hwnd) -> bool:
        try:
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(256)
            self._user32.GetClassNameW(hwnd, buf, 256)
            if buf.value in ("Progman", "WorkerW", "Shell_TrayWnd"):
                return False
            class RECT(ctypes.Structure):
                _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                            ("right", wintypes.LONG), ("bottom", wintypes.LONG)]
            class MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                            ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]
            r = RECT()
            if not self._user32.GetWindowRect(hwnd, ctypes.byref(r)):
                return False
            hmon = self._user32.MonitorFromWindow(hwnd, 2)
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if not self._user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                return False
            return (r.left <= mi.rcMonitor.left and r.top <= mi.rcMonitor.top and
                    r.right >= mi.rcMonitor.right and r.bottom >= mi.rcMonitor.bottom)
        except Exception:
            return False

    def _win_process_name(self, hwnd) -> str:
        try:
            from ctypes import wintypes
            from pathlib import Path
            pid = wintypes.DWORD()
            self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if not pid.value or self._kernel32 is None:
                return ""
            hproc = self._kernel32.OpenProcess(0x1000, False, pid.value)
            if not hproc:
                return ""
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            self._kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(size))
            self._kernel32.CloseHandle(hproc)
            return Path(buf.value).name.lower()
        except Exception:
            return ""

    def _mac_is_finder(self) -> bool:
        try:
            from AppKit import NSWorkspace
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            return app.bundleIdentifier() == "com.apple.finder" if app else True
        except Exception:
            return True

    def _linux_is_file_manager(self) -> bool:
        try:
            if self._mac is not None and hasattr(self._mac, "x11"):
                # Check active window on X11
                return True
        except Exception:
            pass
        return True
