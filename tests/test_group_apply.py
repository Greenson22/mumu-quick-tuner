"""Tes eksekutor batch dengan client palsu (tanpa MuMu asli)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.services import group_apply
from app.services.group_apply import (
    diff_settings,
    prepare_preset,
    run_batch,
)


class FakeClient:
    def __init__(
        self,
        settings: dict[str, dict[str, str]],
        failing: set[str] | None = None,
        ignore_keys: set[str] | None = None,
    ) -> None:
        self.settings = {index: dict(values) for index, values in settings.items()}
        self.failing = failing or set()
        self.ignore_keys = ignore_keys or set()
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get_settings(self, index: str) -> dict[str, str]:
        return dict(self.settings[str(index)])

    def apply(self, index: str, changes: dict[str, str]) -> None:
        index = str(index)
        if index in self.failing:
            raise RuntimeError("device sibuk")
        self.calls.append((index, dict(changes)))
        for key, value in changes.items():
            if key not in self.ignore_keys:
                self.settings[index][key] = value


class PrepareTests(unittest.TestCase):
    def test_prepare_preset_filters_unmanaged_keys(self) -> None:
        preset = {
            "max_frame_rate": "60",
            "player_name": "jangan-diubah",
            "phone_model": "X",
        }
        self.assertEqual(prepare_preset(preset), {"max_frame_rate": "60"})
        self.assertEqual(prepare_preset(None), {})

    def test_diff_only_changed(self) -> None:
        current = {"max_frame_rate": "30", "vertical_sync": "false"}
        preset = {"max_frame_rate": "60", "vertical_sync": "false"}
        self.assertEqual(diff_settings(current, preset), {"max_frame_rate": "60"})


class RunBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.backup_dir = Path(self._tmp.name)
        patcher = mock.patch.object(
            group_apply, "create_backup", return_value=None
        )
        self.backup = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_applies_only_diff(self) -> None:
        client = FakeClient(
            {
                "2": {"max_frame_rate": "30", "vertical_sync": "false"},
                "5": {"max_frame_rate": "60", "vertical_sync": "false"},
            }
        )
        preset = {"max_frame_rate": "60", "vertical_sync": "false", "player_name": "X"}

        results = run_batch(
            client,
            [("a", "2"), ("b", "5")],
            preset,
            self.backup_dir,
        )

        self.assertEqual([result.status for result in results], ["success", "unchanged"])
        self.assertEqual(client.calls, [("2", {"max_frame_rate": "60"})])
        self.assertNotIn("player_name", client.settings["2"])

    def test_continues_after_failure(self) -> None:
        client = FakeClient(
            {
                "2": {"max_frame_rate": "30"},
                "5": {"max_frame_rate": "30"},
            },
            failing={"2"},
        )

        results = run_batch(
            client,
            [("a", "2"), ("b", "5")],
            {"max_frame_rate": "60"},
            self.backup_dir,
        )

        self.assertEqual(results[0].status, "failed")
        self.assertEqual(results[1].status, "success")
        self.assertEqual(client.settings["5"]["max_frame_rate"], "60")

    def test_verification_failure_is_reported(self) -> None:
        client = FakeClient(
            {"2": {"max_frame_rate": "30"}},
            ignore_keys={"max_frame_rate"},
        )
        results = run_batch(
            client, [("a", "2")], {"max_frame_rate": "60"}, self.backup_dir
        )
        self.assertEqual(results[0].status, "failed")
        self.assertIn("Verifikasi gagal", results[0].message)

    def test_progress_and_backup_called(self) -> None:
        client = FakeClient({"2": {"max_frame_rate": "30"}})
        events: list[dict] = []

        results = run_batch(
            client,
            [("a", "2")],
            {"max_frame_rate": "60"},
            self.backup_dir,
            progress=events.append,
        )

        self.assertEqual(results[0].status, "success")
        self.backup.assert_called_once()
        phases = {event["phase"] for event in events}
        self.assertIn("apply", phases)
        self.assertIn("verify", phases)
        self.assertIn("done", phases)

    def test_cancel_marks_remaining_skipped(self) -> None:
        client = FakeClient(
            {"2": {"max_frame_rate": "30"}, "5": {"max_frame_rate": "30"}}
        )
        results = run_batch(
            client,
            [("a", "2"), ("b", "5")],
            {"max_frame_rate": "60"},
            self.backup_dir,
            should_cancel=lambda: True,
        )
        self.assertEqual([result.status for result in results], ["skipped", "skipped"])
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
