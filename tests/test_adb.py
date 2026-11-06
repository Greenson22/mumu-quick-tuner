"""Tes konstruksi perintah ADB dan parsing resolusi."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest import mock

from app.mumu import MuMuClient, MuMuError


class PlainRecordingClient(MuMuClient):
    def __init__(self, output: str = "") -> None:
        super().__init__(Path("MuMuManager.exe"))
        self.calls: list[tuple] = []
        self.output = output

    def _run_plain(self, *args: str, timeout: int | None = None) -> str:
        self.calls.append((args, timeout))
        return self.output


class AdbCommandTests(unittest.TestCase):
    def test_adb_shell_command_shape(self) -> None:
        client = PlainRecordingClient()
        client.adb_shell("2", "input tap 60 400")
        self.assertEqual(
            client.calls,
            [(("adb", "-v", "2", "-c", "input tap 60 400"), 60)],
        )

    def test_adb_shell_rejects_empty_command(self) -> None:
        client = PlainRecordingClient()
        with self.assertRaises(MuMuError):
            client.adb_shell("2", "   ")
        self.assertEqual(client.calls, [])

    def test_get_screen_size_physical(self) -> None:
        client = PlainRecordingClient("Physical size: 1280x720")
        self.assertEqual(client.get_screen_size("1"), (1280, 720))

    def test_get_screen_size_prefers_override(self) -> None:
        client = PlainRecordingClient(
            "Physical size: 1920x1080\nOverride size: 1280x720"
        )
        self.assertEqual(client.get_screen_size("1"), (1280, 720))

    def test_get_screen_size_invalid(self) -> None:
        client = PlainRecordingClient("Unknown command")
        self.assertIsNone(client.get_screen_size("1"))


class RunPlainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = MuMuClient(Path("MuMuManager.exe"))
        self.client.manager = Path(__file__)

    def test_plain_stdout(self) -> None:
        proc = subprocess.CompletedProcess([], 0, "Physical size: 800x600", "")
        with mock.patch.object(self.client, "_invoke", return_value=proc):
            self.assertEqual(
                self.client._run_plain("adb", "-v", "1", "-c", "wm size"),
                "Physical size: 800x600",
            )

    def test_json_error_is_raised(self) -> None:
        proc = subprocess.CompletedProcess(
            [], 0, '{"errcode": 1, "errmsg": "device mati"}', ""
        )
        with mock.patch.object(self.client, "_invoke", return_value=proc):
            with self.assertRaises(MuMuError):
                self.client._run_plain("adb", "-v", "1", "-c", "wm size")

    def test_json_data_is_unwrapped(self) -> None:
        proc = subprocess.CompletedProcess(
            [], 0, '{"errcode": 0, "data": "Physical size: 900x700"}', ""
        )
        with mock.patch.object(self.client, "_invoke", return_value=proc):
            self.assertEqual(
                self.client._run_plain("adb", "-v", "1", "-c", "wm size"),
                "Physical size: 900x700",
            )


if __name__ == "__main__":
    unittest.main()
