"""Perekam aksi pengguna pada jendela emulator MuMu.

Merekam klik mouse (tap), geser (swipe), pengetikan teks, dan tombol navigasi
secara otomatis berdasarkan interaksi nyata pengguna pada emulator.
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

# Windows Constants
WH_MOUSE_LL = 14
WH_KEYBOARD_LL = 13
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104

VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
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


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulong),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulong),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


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


def _get_window_class(hwnd: int) -> str:
    """Ambil nama class jendela."""
    if sys.platform != "win32":
        return ""
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


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
    """Cek apakah nama executable berasal dari MuMu."""
    lower = exe_name.lower()
    return any(kw in lower for kw in _MUMU_EXE_KEYWORDS)


def _is_mumu_title(title: str) -> bool:
    """Cek apakah judul jendela mengandung kata kunci MuMu."""
    lower = title.lower()
    return any(kw in lower for kw in _MUMU_TITLE_KEYWORDS)


def _is_self_window(exe_name: str, title: str) -> bool:
    """Cek apakah jendela milik aplikasi kita sendiri atau tool lain."""
    lower_exe = exe_name.lower()
    lower_title = title.lower()
    if any(kw in lower_exe for kw in _SELF_EXE_KEYWORDS):
        return True
    if "quick tuner" in lower_title:
        return True
    return False


def find_mumu_windows() -> list[tuple[int, str]]:
    """Cari jendela MuMu yang sedang berjalan di sistem.

    Menggunakan beberapa strategi:
    1. Deteksi berdasarkan nama proses executable (MuMu*, Nemu*, vkms)
    2. Deteksi berdasarkan judul jendela (mengandung 'mumu' / 'nemu')
    3. Mengecualikan jendela aplikasi sendiri (Python, VS Code, Explorer, dll.)
    """
    if sys.platform != "win32":
        return []

    user32 = ctypes.windll.user32
    results: list[tuple[int, str]] = []
    seen_hwnds: set[int] = set()

    def enum_cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        if hwnd in seen_hwnds:
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
    """Ambil jendela top-level di posisi layar tertentu.

    Menggunakan WindowFromPoint yang bisa mendeteksi jendela dari proses
    elevated (Administrator) sekalipun, tidak seperti EnumWindows.
    """
    if sys.platform != "win32":
        return None

    user32 = ctypes.windll.user32
    pt = POINT(screen_x, screen_y)
    hwnd = user32.WindowFromPoint(pt)
    if not hwnd:
        return None

    # Naik ke jendela top-level (root owner)
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
    """Merekam interaksi mouse dan keyboard pada jendela target."""

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

        self.steps: list[ScriptStep] = []
        self._running = False
        self._thread: threading.Thread | None = None
        self._mouse_hook = None
        self._keyboard_hook = None
        self._hook_thread_id = 0

        self._last_action_time: float = 0.0
        self._drag_start_point: tuple[int, int] | None = None
        self._drag_start_time: float = 0.0

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
        self._drag_start_point = None
        self._text_buffer = ""

        self._thread = threading.Thread(target=self._run_hooks, daemon=True)
        self._thread.start()

    def stop(self) -> list[ScriptStep]:
        if not self._running:
            return list(self.steps)

        self._flush_text_buffer()
        self._running = False

        if sys.platform == "win32" and self._hook_thread_id:
            user32 = ctypes.windll.user32
            WM_QUIT = 0x0012
            user32.PostThreadMessageW(self._hook_thread_id, WM_QUIT, 0, 0)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

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
        if fg == self.target_hwnd:
            return True
        # Cek apakah jendela aktif adalah child atau parent dari target
        parent = user32.GetParent(fg)
        if parent == self.target_hwnd:
            return True
        root = user32.GetAncestor(fg, 2)  # GA_ROOT
        target_root = user32.GetAncestor(self.target_hwnd, 2)
        return root == target_root if (root and target_root) else False

    def _client_to_ref(self, screen_x: int, screen_y: int) -> tuple[int, int] | None:
        client_rect = get_window_client_rect(self.target_hwnd)
        if not client_rect:
            return None
        cx, cy, cw, ch = client_rect
        if not (cx <= screen_x <= cx + cw and cy <= screen_y <= cy + ch):
            return None

        rel_x = screen_x - cx
        rel_y = screen_y - cy

        scaled_x = int(round(rel_x * self.ref_width / cw))
        scaled_y = int(round(rel_y * self.ref_height / ch))
        return (
            max(0, min(self.ref_width - 1, scaled_x)),
            max(0, min(self.ref_height - 1, scaled_y)),
        )

    def _handle_mouse(self, ncode: int, wparam: int, lparam: int) -> None:
        if ncode < 0 or not self._running:
            return

        ms = MSLLHOOKSTRUCT.from_address(lparam)
        pt_x, pt_y = ms.pt.x, ms.pt.y

        if wparam == WM_LBUTTONDOWN:
            ref_pt = self._client_to_ref(pt_x, pt_y)
            if ref_pt:
                self._flush_text_buffer()
                self._drag_start_point = ref_pt
                self._drag_start_time = time.monotonic()

        elif wparam == WM_LBUTTONUP:
            if self._drag_start_point is not None:
                self._flush_text_buffer()
                end_pt = self._client_to_ref(pt_x, pt_y)
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

    def _handle_keyboard(self, ncode: int, wparam: int, lparam: int) -> None:
        if ncode < 0 or not self._running:
            return

        if wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            if not self._is_target_active():
                return

            kb = KBDLLHOOKSTRUCT.from_address(lparam)
            vk = kb.vkCode

            # Tombol Stop darurat / cepat saat merekam: F10
            if vk == VK_F10:
                self.stop()
                return

            now = time.monotonic()
            delay_ms = max(50, int((now - self._last_action_time) * 1000))

            # Tombol navigasi / kontrol
            key_map = {
                VK_RETURN: "enter",
                VK_BACK: "delete",
                VK_ESCAPE: "back",
                VK_TAB: "tab",
            }

            if vk in key_map:
                self._flush_text_buffer()
                self._last_action_time = now
                step = ScriptStep(action="key", key=key_map[vk], delay_ms=delay_ms)
                self.steps.append(step)
                if self.on_step_recorded:
                    self.on_step_recorded(step)
                return

            # Konversi virtual key ke karakter jika alfanumerik / simbol
            char = self._vk_to_char(vk)
            if char:
                with self._buffer_lock:
                    if not self._text_buffer:
                        self._text_start_delay = delay_ms
                    self._text_buffer += char
                    self._last_action_time = now

    def _vk_to_char(self, vk: int) -> str | None:
        if sys.platform != "win32":
            return None
        user32 = ctypes.windll.user32
        keyboard_state = (ctypes.c_ubyte * 256)()
        user32.GetKeyboardState(ctypes.byref(keyboard_state))

        buff = ctypes.create_unicode_buffer(5)
        res = user32.ToUnicode(vk, 0, keyboard_state, buff, 5, 0)
        if res > 0:
            val = buff.value
            if val and val.isprintable():
                return val
        return None

    def _run_hooks(self) -> None:
        if sys.platform != "win32":
            return

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._hook_thread_id = kernel32.GetCurrentThreadId()

        def mouse_proc(ncode, wparam, lparam):
            try:
                self._handle_mouse(ncode, wparam, lparam)
            except Exception:
                pass
            return user32.CallNextHookEx(self._mouse_hook, ncode, wparam, lparam)

        def keyboard_proc(ncode, wparam, lparam):
            try:
                self._handle_keyboard(ncode, wparam, lparam)
            except Exception:
                pass
            return user32.CallNextHookEx(self._keyboard_hook, ncode, wparam, lparam)

        mouse_cb = HOOKPROC(mouse_proc)
        keyboard_cb = HOOKPROC(keyboard_proc)

        self._mouse_hook = user32.SetWindowsHookExW(
            WH_MOUSE_LL, mouse_cb, kernel32.GetModuleHandleW(None), 0
        )
        self._keyboard_hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, keyboard_cb, kernel32.GetModuleHandleW(None), 0
        )

        msg = wintypes.MSG()
        while self._running:
            b_ret = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if b_ret <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._mouse_hook:
            user32.UnhookWindowsHookEx(self._mouse_hook)
            self._mouse_hook = None
        if self._keyboard_hook:
            user32.UnhookWindowsHookEx(self._keyboard_hook)
            self._keyboard_hook = None
