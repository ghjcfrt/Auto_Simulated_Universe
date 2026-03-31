import importlib
import types
import unittest
from unittest import mock

from tests._platform_stubs import install_platform_stubs

install_platform_stubs()
window = importlib.import_module("utils.common.window")


class WindowTests(unittest.TestCase):
    def _patch_success_dependencies(self):
        fake_windll = types.SimpleNamespace(
            user32=types.SimpleNamespace(GetDpiForWindow=lambda _hwnd: 96)
        )
        return (
            mock.patch.object(window.win32gui, "GetForegroundWindow", return_value=1),
            mock.patch.object(window.win32gui, "GetWindowText", return_value="崩坏：星穹铁道"),
            mock.patch.object(window.win32gui, "GetClientRect", return_value=(0, 0, 1920, 1080)),
            mock.patch.object(window.win32gui, "GetWindowRect", return_value=(0, 0, 1920, 1080)),
            mock.patch.object(window.win32gui, "GetWindowDC", return_value=10),
            mock.patch.object(window.win32gui, "ReleaseDC", return_value=None),
            mock.patch.object(window.win32print, "GetDeviceCaps", return_value=96),
            mock.patch.object(window.ctypes, "windll", fake_windll, create=True),
            mock.patch.object(window.time, "sleep", return_value=None),
        )

    def test_wait_game_window_state_returns_geometry(self):
        patches = self._patch_success_dependencies()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            state = window.wait_game_window_state(1920, 1080, 1.0, success_sleep=0.1)

        self.assertTrue(state["full"])
        self.assertEqual(state["xx"], 1920)
        self.assertEqual(state["yy"], 1080)
        self.assertEqual(state["x0"], 9)
        self.assertEqual(state["y0"], 9)
        self.assertEqual(state["real_width"], 1920)

    def test_wait_game_window_state_calls_exception_callback(self):
        call_count = {"count": 0}

        def get_foreground_window():
            if call_count["count"] == 0:
                call_count["count"] += 1
                raise RuntimeError("boom")
            return 1

        errors = []
        fake_windll = types.SimpleNamespace(
            user32=types.SimpleNamespace(GetDpiForWindow=lambda _hwnd: 96)
        )

        with mock.patch.object(window.win32gui, "GetForegroundWindow", side_effect=get_foreground_window), \
            mock.patch.object(window.win32gui, "GetWindowText", return_value="崩坏：星穹铁道"), \
            mock.patch.object(window.win32gui, "GetClientRect", return_value=(0, 0, 1920, 1080)), \
            mock.patch.object(window.win32gui, "GetWindowRect", return_value=(0, 0, 1920, 1080)), \
            mock.patch.object(window.win32gui, "GetWindowDC", return_value=10), \
            mock.patch.object(window.win32gui, "ReleaseDC", return_value=None), \
            mock.patch.object(window.win32print, "GetDeviceCaps", return_value=96), \
            mock.patch.object(window.ctypes, "windll", fake_windll, create=True), \
            mock.patch.object(window.time, "sleep", return_value=None):
            state = window.wait_game_window_state(
                1920,
                1080,
                1.0,
                on_exception=errors.append,
                exception_sleep=0.1,
            )

        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], RuntimeError)
        self.assertEqual(state["xx"], 1920)


if __name__ == "__main__":
    unittest.main()
