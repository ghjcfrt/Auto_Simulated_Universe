import os
import sys
import time
from typing import Optional, Tuple

import pythoncom
import win32com.client
import win32gui

from asu.core.common.paths import logs_path
from asu.core.platform.log import log


def _read_notif_state(file_path: str) -> Tuple[Optional[str], Optional[str]]:
    """读取通知计数与时间戳，读取失败时返回空值。"""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
    except OSError:
        return None, None

    cnt = lines[0].strip("\n") if len(lines) > 0 else None
    tm = lines[3].strip("\n") if len(lines) > 3 else None
    return cnt, tm


def notif(title: str, msg: str, cnt=None):
    """统一写入通知文件，并返回可解析的计数值。"""
    log.info("通知：" + msg + "  " + title)
    tm = str(time.time()) if cnt is not None else None
    file_path = logs_path("notif.txt", use_cwd=True)

    if os.path.exists(file_path):
        file_cnt, file_tm = _read_notif_state(file_path)
        if cnt is None and file_cnt is not None:
            cnt = file_cnt
        if tm is None and file_tm is not None:
            tm = file_tm

    os.makedirs(logs_path(use_cwd=True), exist_ok=True)
    if cnt is None:
        cnt = "0"
    if tm is None:
        tm = str(time.time())

    try:
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write(cnt + "\n" + title + "\n" + msg + "\n" + tm)
    except OSError as exc:
        log.error(f"写入通知文件失败: {exc}")

    try:
        return int(cnt)
    except (TypeError, ValueError):
        return 0


def set_forground(config):
    """将游戏窗口置于前台，失败时静默跳过。"""
    config.read()
    try:
        pythoncom.CoInitialize()
        shell = win32com.client.Dispatch("WScript.Shell")
        if getattr(sys, "frozen", False):
            shell.SendKeys(" ")
        else:
            shell.SendKeys("")
        game_nd = win32gui.FindWindow("UnityWndClass", "崩坏：星穹铁道")
        if game_nd == 0:
            game_nd = win32gui.FindWindow(None, "云·星穹铁道")
        if game_nd != 0:
            win32gui.SetForegroundWindow(game_nd)
    except Exception:
        return
