"""Perekam aksi pengguna pada jendela emulator MuMu (Safe Polling Mode).

Menggunakan metode polling status mouse dan keyboard (GetAsyncKeyState & GetCursorPos)
yang 100% AMAN, tidak mencegat driver Windows, dan tidak akan membekukan kursor.
"""

from __future__ import annotations

import ctypes
import math
import sys
import threading
import time
from ctypes import wintypes
from typing import Callable

from app.services.automation import ScriptStep

# Virtual Keys
VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_PAUSE = 0x13
VK_CAPITAL = 0x14
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_PRIOR = 0x21  # Page Up
VK_NEXT = 0x22  # Page Down
VK_END = 0x23
VK_HOME = 0x24
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_DELETE = 0x2E
VK_F10 = 0x79

# Ctypes structures
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def _get_exe_name(hwnd: int) -> str:
    """Ambil nama file executable dari proses pemilik jendela."""
    if sys.platform != "win32":
        return ""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""

    try:
        buf = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(512)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value.rsplit("\\", 1)[-1]
    finally:
        kernel32.CloseHandle(handle)
    return ""


def _get_window_title(hwnd: int) -> str:
    """Ambil judul jendela."""
    if sys.platform != "win32":
        return ""
    user32 = ctypes.windll.user32
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


_MUMU_EXE_KEYWORDS = (
    "mumu", "nemu", "nemushell", "vkms",
)

_MUMU_TITLE_KEYWORDS = (
    "mumu", "nemu",
)

_SELF_EXE_KEYWORDS = (
    "python", "code.exe", "explorer.exe", "terminal",
    "opencode", "cmd.exe", "powershell",
)


def _is_mumu_exe(exe_name: str) -> bool:
    lower = exe_name.lower()
    return any(kw in lower for kw in _MUMU_EXE_KEYWORDS)


def _is_mumu_title(title: str) -> bool:
    lower = title.lower()
    return any(kw in lower for kw in _MUMU_TITLE_KEYWORDS)


def _is_self_window(exe_name: str, title: str) -> bool:
    lower_exe = exe_name.lower()
    lower_title = title.lower()
    if any(kw in lower_exe for kw in _SELF_EXE_KEYWORDS):
        return True
    if "quick tuner" in lower_title:
        return True
    return False


def find_mumu_windows() -> list[tuple[int, str]]:
    """Cari jendela MuMu yang sedang berjalan di sistem."""
    if sys.platform != "win32":
        return []

    user32 = ctypes.windll.user32
    results: list[tuple[int, str]] = []
    seen_hwnds: set[int] = set()

    def enum_cb(hwnd, _lparam):
        if hwnd in seen_hwnds:
            return True

        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w < 100 or h < 100:
            return True

        title = _get_window_title(hwnd)
        exe_name = _get_exe_name(hwnd)

        if _is_self_window(exe_name, title):
            return True

        is_mumu = _is_mumu_exe(exe_name) or _is_mumu_title(title)
        if is_mumu:
            label = title if title else f"MuMu Window ({exe_name})"
            results.append((hwnd, label))
            seen_hwnds.add(hwnd)

        return True

    ENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(ENUMPROC(enum_cb), 0)
    return results


def get_window_at_point(screen_x: int, screen_y: int) -> tuple[int, str] | None:
    """Ambil jendela top-level di posisi layar tertentu."""
    if sys.platform != "win32":
        return None

    user32 = ctypes.windll.user32
    pt = POINT(screen_x, screen_y)
    hwnd = user32.WindowFromPoint(pt)
    if not hwnd:
        return None

    GA_ROOT = 2
    root = user32.GetAncestor(hwnd, GA_ROOT)
    if root:
        hwnd = root

    title = _get_window_title(hwnd)
    exe_name = _get_exe_name(hwnd)

    if _is_self_window(exe_name, title):
        return None

    label = title if title else f"Window ({exe_name or 'unknown'})"
    return (hwnd, label)


def pick_window_under_cursor() -> tuple[int, str] | None:
    """Ambil jendela top-level di posisi kursor mouse saat ini."""
    if sys.platform != "win32":
        return None

    user32 = ctypes.windll.user32
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return get_window_at_point(pt.x, pt.y)


def get_window_client_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Dapatkan koordinat layar area client (isi dalam) dari sebuah jendela."""
    if sys.platform != "win32" or not hwnd:
        return None

    user32 = ctypes.windll.user32
    rect = RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None

    top_left = POINT(rect.left, rect.top)
    bottom_right = POINT(rect.right, rect.bottom)
    user32.ClientToScreen(hwnd, ctypes.byref(top_left))
    user32.ClientToScreen(hwnd, ctypes.byref(bottom_right))

    width = max(1, bottom_right.x - top_left.x)
    height = max(1, bottom_right.y - top_left.y)
    return (top_left.x, top_left.y, width, height)


class ActionRecorder:
    """Merekam interaksi mouse dan keyboard menggunakan Safe Polling Loop.

    Keunggulan Polling Mode:
    1. 100% AMAN: Tidak mencegat driver mouse Windows, kursor tidak akan pernah freeze/macet.
    2. Kebal terhadap masalah privilese Administrator / UIPI.
    3. Thread loop berjalan independen dengan frekuensi ~100Hz.
    """

    def __init__(
        self,
        target_hwnd: int,
        ref_width: int = 1280,
        ref_height: int = 720,
        on_step_recorded: Callable[[ScriptStep], None] | None = None,
    ) -> None:
        self.target_hwnd = target_hwnd
        self.ref_width = ref_width
        self.ref_height = ref_height
        self.on_step_recorded = on_step_recorded

        self.target_pid = 0
        if sys.platform == "win32" and target_hwnd:
            pid = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(target_hwnd, ctypes.byref(pid))
            self.target_pid = pid.value

        self.steps: list[ScriptStep] = []
        self._running = False
        self._thread: threading.Thread | None = None

        self._last_action_time: float = 0.0
        self._mouse_down = False
        self._drag_start_point: tuple[int, int] | None = None
        self._drag_start_time: float = 0.0

        # State tracking tombol keyboard untuk mendeteksi keydown/keyup
        self._key_down_states: dict[int, bool] = {}

        # Penyangga pengetikan teks beruntun
        self._text_buffer = ""
        self._text_start_delay: int = 0
        self._buffer_lock = threading.Lock()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.steps.clear()
        self._last_action_time = time.monotonic()
        self._mouse_down = False
        self._drag_start_point = None
        self._text_buffer = ""
        self._key_down_states.clear()

        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> list[ScriptStep]:
        if not self._running:
            return list(self.steps)

        self._running = False
        self._flush_text_buffer()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)

        return list(self.steps)

    def _flush_text_buffer(self) -> None:
        with self._buffer_lock:
            if not self._text_buffer:
                return
            step = ScriptStep(
                action="text",
                text=self._text_buffer,
                delay_ms=self._text_start_delay,
            )
            self.steps.append(step)
            self._text_buffer = ""
            if self.on_step_recorded:
                self.on_step_recorded(step)

    def _is_target_active(self) -> bool:
        if sys.platform != "win32":
            return True
        user32 = ctypes.windll.user32
        fg = user32.GetForegroundWindow()
        if not fg:
            return False
        if fg == self.target_hwnd:
            return True

        if self.target_pid:
            fg_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(fg, ctypes.byref(fg_pid))
            if fg_pid.value == self.target_pid:
                return True

        parent = user32.GetParent(fg)
        if parent == self.target_hwnd:
            return True
        root = user32.GetAncestor(fg, 2)
        target_root = user32.GetAncestor(self.target_hwnd, 2)
        return root == target_root if (root and target_root) else False

    def _client_to_ref(self, screen_x: int, screen_y: int) -> tuple[int, int] | None:
        user32 = ctypes.windll.user32

        client_rect = get_window_client_rect(self.target_hwnd)
        if client_rect and client_rect[2] > 10 and client_rect[3] > 10:
            cx, cy, cw, ch = client_rect
        else:
            wrect = RECT()
            if not user32.GetWindowRect(self.target_hwnd, ctypes.byref(wrect)):
                return None
            cx, cy = wrect.left, wrect.top
            cw = max(1, wrect.right - wrect.left)
            ch = max(1, wrect.bottom - wrect.top)

        if not (cx <= screen_x <= cx + cw and cy <= screen_y <= cy + ch):
            pt = POINT(screen_x, screen_y)
            hwnd_under = user32.WindowFromPoint(pt)
            if hwnd_under and self.target_pid:
                under_pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd_under, ctypes.byref(under_pid))
                if under_pid.value != self.target_pid:
                    return None
            else:
                return None

        rel_x = max(0, min(cw, screen_x - cx))
        rel_y = max(0, min(ch, screen_y - cy))

        scaled_x = int(round(rel_x * self.ref_width / cw))
        scaled_y = int(round(rel_y * self.ref_height / ch))
        return (
            max(0, min(self.ref_width - 1, scaled_x)),
            max(0, min(self.ref_height - 1, scaled_y)),
        )

    def _poll_mouse(self, user32) -> None:
        # GetAsyncKeyState: Most Significant Bit (0x8000) menunjukkan tombol sedang ditekan
        is_lbutton_pressed = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)

        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))

        if is_lbutton_pressed and not self._mouse_down:
            # Transisi: Mouse Down (Klik Baru)
            ref_pt = self._client_to_ref(pt.x, pt.y)
            if ref_pt:
                self._flush_text_buffer()
                self._mouse_down = True
                self._drag_start_point = ref_pt
                self._drag_start_time = time.monotonic()

        elif not is_lbutton_pressed and self._mouse_down:
            # Transisi: Mouse Up (Klik Dilepas)
            self._mouse_down = False
            if self._drag_start_point is not None:
                self._flush_text_buffer()
                end_pt = self._client_to_ref(pt.x, pt.y)
                if end_pt is None:
                    end_pt = self._drag_start_point

                now = time.monotonic()
                duration_ms = max(50, int((now - self._drag_start_time) * 1000))
                delay_ms = max(50, int((self._drag_start_time - self._last_action_time) * 1000))
                self._last_action_time = now

                dx = end_pt[0] - self._drag_start_point[0]
                dy = end_pt[1] - self._drag_start_point[1]
                distance = math.hypot(dx, dy)

                if distance < 15 and duration_ms < 500:
                    step = ScriptStep(
                        action="tap",
                        x=self._drag_start_point[0],
                        y=self._drag_start_point[1],
                        duration_ms=duration_ms,
                        delay_ms=delay_ms,
                    )
                else:
                    step = ScriptStep(
                        action="swipe",
                        x=self._drag_start_point[0],
                        y=self._drag_start_point[1],
                        x2=end_pt[0],
                        y2=end_pt[1],
                        duration_ms=duration_ms,
                        delay_ms=delay_ms,
                    )

                self.steps.append(step)
                self._drag_start_point = None
                if self.on_step_recorded:
                    self.on_step_recorded(step)

    def _poll_keyboard(self, user32) -> None:
        # Cek F10 untuk shortcut stop
        if user32.GetAsyncKeyState(VK_F10) & 0x8000:
            self.stop()
            return

        if not self._is_target_active():
            return

        # Daftar tombol navigasi dan kontrol
        key_map = {
            VK_RETURN: "enter",
            VK_BACK: "delete",
            VK_ESCAPE: "back",
            VK_TAB: "tab",
        }

        # Periksa tombol navigasi
        for vk, key_name in key_map.items():
            is_down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
            was_down = self._key_down_states.get(vk, False)
            self._key_down_states[vk] = is_down

            if is_down and not was_down:
                self._flush_text_buffer()
                now = time.monotonic()
                delay_ms = max(50, int((now - self._last_action_time) * 1000))
                self._last_action_time = now
                step = ScriptStep(action="key", key=key_name, delay_ms=delay_ms)
                self.steps.append(step)
                if self.on_step_recorded:
                    self.on_step_recorded(step)
                return

        # Periksa karakter alfanumerik (A-Z, 0-9, Spasi)
        vks_to_check = [VK_SPACE] + list(range(0x30, 0x3A)) + list(range(0x41, 0x5B))
        for vk in vks_to_check:
            is_down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
            was_down = self._key_down_states.get(vk, False)
            self._key_down_states[vk] = is_down

            if is_down and not was_down:
                char = self._vk_to_char(vk, user32)
                if char:
                    now = time.monotonic()
                    delay_ms = max(50, int((now - self._last_action_time) * 1000))
                    with self._buffer_lock:
                        if not self._text_buffer:
                            self._text_start_delay = delay_ms
                        self._text_buffer += char
                        self._last_action_time = now

    def _vk_to_char(self, vk: int, user32) -> str | None:
        if sys.platform != "win32":
            return None
        keyboard_state = (ctypes.c_ubyte * 256)()
        user32.GetKeyboardState(ctypes.byref(keyboard_state))

        buff = ctypes.create_unicode_buffer(5)
        res = user32.ToUnicode(vk, 0, keyboard_state, buff, 5, 0)
        if res > 0:
            val = buff.value
            if val and val.isprintable():
                return val
        return None

    def _poll_loop(self) -> None:
        if sys.platform != "win32":
            return

        user32 = ctypes.windll.user32

        # Reset state awal agar tombol yang sedang ditekan sebelum rekam tidak memicu aksi palsu
        user32.GetAsyncKeyState(VK_LBUTTON)
        user32.GetAsyncKeyState(VK_F10)
        for vk in range(0x30, 0x5B):
            user32.GetAsyncKeyState(vk)

        while self._running:
            try:
                self._poll_mouse(user32)
                self._poll_keyboard(user32)
            except Exception:
                pass

            # Polling rate ~100 FPS (10 ms per siklus, sangat ringan untuk CPU dan sangat responsif)
            time.sleep(0.01)
