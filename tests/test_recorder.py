"""Tes unit untuk perekam aksi (ActionRecorder)."""

from __future__ import annotations

import unittest

from app.services.automation import ScriptStep
from app.services.recorder import (
    ActionRecorder,
    get_window_at_point,
    get_window_client_rect,
    find_mumu_windows,
    pick_window_under_cursor,
    _is_mumu_exe,
    _is_mumu_title,
    _is_self_window,
)


class ActionRecorderTests(unittest.TestCase):
    def test_recorder_initial_state(self) -> None:
        rec = ActionRecorder(target_hwnd=12345, ref_width=1280, ref_height=720)
        self.assertEqual(rec.target_hwnd, 12345)
        self.assertEqual(rec.ref_width, 1280)
        self.assertEqual(rec.ref_height, 720)
        self.assertEqual(rec.steps, [])

    def test_text_buffer_flush(self) -> None:
        recorded: list[ScriptStep] = []
        rec = ActionRecorder(
            target_hwnd=12345,
            on_step_recorded=recorded.append,
        )
        rec._text_buffer = "hello"
        rec._text_start_delay = 500
        rec._flush_text_buffer()

        self.assertEqual(len(rec.steps), 1)
        step = rec.steps[0]
        self.assertEqual(step.action, "text")
        self.assertEqual(step.text, "hello")
        self.assertEqual(step.delay_ms, 500)
        self.assertEqual(len(recorded), 1)

    def test_text_buffer_flush_empty_is_noop(self) -> None:
        rec = ActionRecorder(target_hwnd=12345)
        rec._text_buffer = ""
        rec._flush_text_buffer()
        self.assertEqual(rec.steps, [])

    def test_get_window_client_rect_invalid_hwnd(self) -> None:
        rect = get_window_client_rect(0)
        self.assertIsNone(rect)

    def test_get_window_at_point_zero(self) -> None:
        # Posisi (0, 0) mungkin mengembalikan taskbar atau None
        result = get_window_at_point(0, 0)
        # Tidak crash — cukup
        self.assertTrue(result is None or isinstance(result, tuple))

    def test_find_mumu_windows_returns_list(self) -> None:
        result = find_mumu_windows()
        self.assertIsInstance(result, list)

    def test_pick_window_under_cursor_returns_tuple_or_none(self) -> None:
        result = pick_window_under_cursor()
        self.assertTrue(result is None or isinstance(result, tuple))


class DetectionHelperTests(unittest.TestCase):
    def test_is_mumu_exe_positive(self) -> None:
        self.assertTrue(_is_mumu_exe("MuMuNxMain.exe"))
        self.assertTrue(_is_mumu_exe("NemuShell.exe"))
        self.assertTrue(_is_mumu_exe("vkms.exe"))
        self.assertTrue(_is_mumu_exe("MuMuPlayer.exe"))

    def test_is_mumu_exe_negative(self) -> None:
        self.assertFalse(_is_mumu_exe("python.exe"))
        self.assertFalse(_is_mumu_exe("explorer.exe"))
        self.assertFalse(_is_mumu_exe("Code.exe"))

    def test_is_mumu_title_positive(self) -> None:
        self.assertTrue(_is_mumu_title("MuMu Player 15"))
        self.assertTrue(_is_mumu_title("NemuPlayer - #0"))

    def test_is_mumu_title_negative(self) -> None:
        self.assertFalse(_is_mumu_title("Visual Studio Code"))
        self.assertFalse(_is_mumu_title("File Explorer"))

    def test_is_self_window(self) -> None:
        self.assertTrue(_is_self_window("python.exe", ""))
        self.assertTrue(_is_self_window("Code.exe", ""))
        self.assertTrue(_is_self_window("explorer.exe", ""))
        self.assertTrue(_is_self_window("anything.exe", "MuMu Quick Tuner"))
        self.assertFalse(_is_self_window("MuMuNxMain.exe", "Game"))


if __name__ == "__main__":
    unittest.main()
