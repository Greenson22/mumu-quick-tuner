"""Tes unit untuk perekam aksi (ActionRecorder)."""

from __future__ import annotations

import unittest

from app.services.automation import ScriptStep
from app.services.recorder import ActionRecorder, get_window_client_rect


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

    def test_get_window_client_rect_invalid_hwnd(self) -> None:
        rect = get_window_client_rect(0)
        self.assertIsNone(rect)


if __name__ == "__main__":
    unittest.main()
