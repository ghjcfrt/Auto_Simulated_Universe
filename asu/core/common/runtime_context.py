import os
import threading


def _is_admin():
    try:
        import pyuac

        return bool(pyuac.isUserAdmin())
    except Exception:
        return None


def _foreground_title():
    try:
        import win32gui

        hwnd = win32gui.GetForegroundWindow()
        return win32gui.GetWindowText(hwnd)
    except Exception:
        return None


def describe_runtime_context(label: str) -> str:
    thread = threading.current_thread()
    return (
        f"{label}: "
        f"pid={os.getpid()}, "
        f"thread_name={thread.name}, "
        f"thread_ident={threading.get_ident()}, "
        f"main_thread={thread is threading.main_thread()}, "
        f"admin={_is_admin()}, "
        f"foreground={_foreground_title()!r}"
    )
