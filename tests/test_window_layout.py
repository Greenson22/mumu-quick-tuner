"""Tes modul penataan posisi jendela emulator."""

from __future__ import annotations

import unittest

from app.services.window_layout import plan_window_rects


class WindowLayoutTests(unittest.TestCase):
    def test_empty_aspects_returns_empty(self) -> None:
        self.assertEqual(plan_window_rects([], (0, 0, 1920, 1080)), [])

    def test_single_window_fits_screen(self) -> None:
        rects = plan_window_rects([(16, 9)], (0, 0, 1920, 1080), margin=8)
        self.assertEqual(len(rects), 1)
        x, y, w, h = rects[0]
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + w, 1920)
        self.assertLessEqual(y + h, 1080)

    def test_multiple_windows_do_not_overlap(self) -> None:
        screen = (0, 0, 1920, 1080)
        aspects = [(540, 960), (540, 960), (540, 960)]  # 3 device batch
        rects = plan_window_rects(aspects, screen, margin=10, title_bar=30)
        self.assertEqual(len(rects), 3)

        for i, (x1, y1, w1, h1) in enumerate(rects):
            # Di dalam batas layar
            self.assertGreaterEqual(x1, screen[0])
            self.assertGreaterEqual(y1, screen[1])
            self.assertLessEqual(x1 + w1, screen[0] + screen[2])
            self.assertLessEqual(y1 + h1, screen[1] + screen[3])

            for j, (x2, y2, w2, h2) in enumerate(rects):
                if i >= j:
                    continue
                # Overlap check
                overlap_x = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
                overlap_y = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
                self.assertTrue(
                    overlap_x == 0 or overlap_y == 0,
                    f"Jendela {i} {rects[i]} bertumpuk dengan jendela {j} {rects[j]}",
                )

    def test_orders_left_to_right_top_to_bottom(self) -> None:
        screen = (0, 0, 1920, 1080)
        aspects = [(16, 9), (16, 9), (16, 9), (16, 9)]
        rects = plan_window_rects(aspects, screen)
        # Urutan: baris 0 col 0, baris 0 col 1, baris 1 col 0, baris 1 col 1
        self.assertLess(rects[0][0], rects[1][0])
        self.assertLess(rects[0][1], rects[2][1])
        self.assertLess(rects[2][0], rects[3][0])

    def test_invalid_aspect_falls_back_to_default(self) -> None:
        rects = plan_window_rects(["invalid", (0, 0)], (0, 0, 1280, 720))
        self.assertEqual(len(rects), 2)
        self.assertTrue(all(w > 0 and h > 0 for _x, _y, w, h in rects))


if __name__ == "__main__":
    unittest.main()
