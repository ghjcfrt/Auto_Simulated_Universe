import importlib
import os
import shutil
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from tests._platform_stubs import install_platform_stubs

install_platform_stubs()
runtime = importlib.import_module("utils.common.runtime")


@contextmanager
def _case_dir(name: str):
    base = Path(__file__).resolve().parent
    case_path = base / f"_runtime_{name}"
    if case_path.exists():
        shutil.rmtree(case_path, ignore_errors=True)
    case_path.mkdir(parents=True, exist_ok=True)

    cwd = os.getcwd()
    os.chdir(case_path)
    try:
        yield case_path
    finally:
        os.chdir(cwd)
        shutil.rmtree(case_path, ignore_errors=True)


class _DummyConfig:
    def __init__(self):
        self.read_count = 0

    def read(self):
        self.read_count += 1


class RuntimeTests(unittest.TestCase):
    def test_read_notif_state_missing_file_returns_none(self):
        with _case_dir("missing") as case_dir:
            missing = case_dir / "missing.txt"
            self.assertEqual(runtime._read_notif_state(str(missing)), (None, None))

    def test_notif_writes_and_reuses_previous_state(self):
        with _case_dir("reuse"):
            first = runtime.notif("标题1", "内容1", cnt="7")
            self.assertEqual(first, 7)

            notif_file = Path("logs/notif.txt")
            lines = notif_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[0], "7")
            old_time = lines[3]

            second = runtime.notif("标题2", "内容2", cnt=None)
            self.assertEqual(second, 7)

            lines2 = notif_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines2[0], "7")
            self.assertEqual(lines2[3], old_time)

    def test_notif_invalid_count_returns_zero(self):
        with _case_dir("invalid"):
            count = runtime.notif("标题", "内容", cnt="invalid")
            self.assertEqual(count, 0)

    def test_set_forground_reads_config_and_focuses_window(self):
        cfg = _DummyConfig()
        shell = mock.Mock()

        with mock.patch.object(runtime.pythoncom, "CoInitialize", return_value=None), \
            mock.patch.object(runtime.win32com.client, "Dispatch", return_value=shell), \
            mock.patch.object(runtime.win32gui, "FindWindow", side_effect=[123, 0]), \
            mock.patch.object(runtime.win32gui, "SetForegroundWindow") as set_foreground:
            runtime.set_forground(cfg)

        self.assertEqual(cfg.read_count, 1)
        shell.SendKeys.assert_called_once_with("")
        set_foreground.assert_called_once_with(123)


if __name__ == "__main__":
    unittest.main()
