import ctypes
import time
from typing import Any, Callable, Dict, Optional

import win32con
import win32gui
import win32print

from utils.log import log

GAME_WINDOW_TITLES = ("崩坏：星穹铁道", "云·星穹铁道")


def wait_game_window_state(
    bx: int,
    by: int,
    multi: float,
    *,
    resolution_detail: bool = False,
    success_sleep: float = 0.0,
    exception_sleep: float = 0.0,
    on_exception: Optional[Callable[[Exception], None]] = None,
) -> Dict[str, Any]:
    """等待游戏窗口可用并返回窗口几何信息。"""
    log.warning("等待游戏窗口")
    while True:
        try:
            hwnd = win32gui.GetForegroundWindow()
            text = win32gui.GetWindowText(hwnd)

            c_x0, c_y0, c_x1, c_y1 = win32gui.GetClientRect(hwnd)
            xx = c_x1 - c_x0
            yy = c_y1 - c_y0

            w_x0, w_y0, w_x1, w_y1 = win32gui.GetWindowRect(hwnd)
            full = w_x0 == 0 and w_y0 == 0
            x0 = max(0, w_x1 - xx) + 9 * full
            y0 = max(0, w_y1 - yy) + 9 * full
            x1 = w_x1
            y1 = w_y1

            # 高分屏或放缩导致窗口比 1920×1080 更大时，裁到中心区域。
            if (xx == 1920 or yy == 1080) and xx >= 1920 and yy >= 1080:
                x0 += (xx - 1920) // 2
                y0 += (yy - 1080) // 2
                x1 -= (xx - 1920) // 2
                y1 -= (yy - 1080) // 2
                xx, yy = 1920, 1080

            scx = xx / bx
            scy = yy / by

            dc = win32gui.GetWindowDC(hwnd)
            dpi_x = win32print.GetDeviceCaps(dc, win32con.LOGPIXELSX)
            dpi_y = win32print.GetDeviceCaps(dc, win32con.LOGPIXELSY)
            win32gui.ReleaseDC(hwnd, dc)
            scale_x = dpi_x / 96

            try:
                scale = ctypes.windll.user32.GetDpiForWindow(hwnd) / 96.0
            except Exception:
                log.info("DPI获取失败")
                scale = 1.0

            log.info("DPI: " + str(scale) + " A:" + str(int(multi * 100) / 100))
            log.info("TEXT: " + str(text))

            real_width = int(xx * scale_x)
            if text in GAME_WINDOW_TITLES:
                if xx != 1920 or yy != 1080:
                    if resolution_detail:
                        log.error(f"分辨率错误 {xx} {yy} 请设为1920*1080")
                    else:
                        log.error("分辨率错误")
                if success_sleep > 0:
                    time.sleep(success_sleep)
                return {
                    "x0": x0,
                    "y0": y0,
                    "x1": x1,
                    "y1": y1,
                    "xx": xx,
                    "yy": yy,
                    "full": full,
                    "scx": scx,
                    "scy": scy,
                    "scale": scale,
                    "real_width": real_width,
                }

            time.sleep(0.3)
        except Exception as exc:
            if on_exception is not None:
                on_exception(exc)
            if exception_sleep > 0:
                time.sleep(exception_sleep)

