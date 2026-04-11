import time

import cv2 as cv
import numpy as np
import pyautogui
import win32api

from asu.core.platform.log import log


def _window_origin(ctx) -> tuple[int, int]:
    x0 = getattr(ctx, "x0", None)
    y0 = getattr(ctx, "y0", None)
    if x0 is None:
        x0 = getattr(ctx, "x1", 0) - ctx.xx
    if y0 is None:
        y0 = getattr(ctx, "y1", 0) - ctx.yy
    return int(x0), int(y0)


def _norm_to_local_pixel(ctx, x: float, y: float) -> tuple[int, int]:
    return int(x * ctx.xx), int(y * ctx.yy)


def _local_pixel_to_norm(ctx, px: int, py: int) -> tuple[float, float]:
    return px / ctx.xx, py / ctx.yy


def get_point(ctx, x, y, printer=print):
    """输出一个像素点在当前窗口中的归一化坐标。"""
    # 输入像素是屏幕绝对坐标，先转换到窗口局部坐标再归一化。
    x0, y0 = _window_origin(ctx)
    px = int(x - x0)
    py = int(y - y0)
    nx, ny = _local_pixel_to_norm(ctx, px, py)
    printer("获取到点：{:.4f},{:.4f}".format(nx, ny))


def calc_point(ctx, point, offset):
    """按窗口尺寸把偏移量从像素转换为归一化坐标。"""
    return (point[0] + offset[0] / ctx.xx, point[1] + offset[1] / ctx.yy)


def click_box(ctx, box):
    """点击文字识别框中心点。"""
    x = (box[0] + box[1]) / 2
    y = (box[2] + box[3]) / 2
    click(ctx, (x / ctx.xx, y / ctx.yy))


def click_position(ctx, position):
    """点击像素坐标点。"""
    click_box(ctx, [position[0], position[0], position[1], position[1]])
    # 全局默认：点击像素点后刷新一帧，避免后续逻辑继续使用旧截图。
    # 可通过设置 ctx.auto_refresh_after_click_position = False 关闭。
    time.sleep(0.5)
    should_refresh = getattr(ctx, "auto_refresh_after_click_position", True)
    if should_refresh and hasattr(ctx, "get_screen"):
        try:
            ctx.get_screen()
        except Exception:
            # 刷新失败不影响点击主流程。
            pass


def click(ctx, points, click_button=1):
    """统一点击逻辑，兼容归一化坐标与像素坐标。"""
    if ctx.debug == 2:
        print(points)
    ctx.print_stack()
    x, y = points
    if not isinstance(x, (int, np.integer)):
        lx, ly = _norm_to_local_pixel(ctx, x, y)
        x0, y0 = _window_origin(ctx)
        x, y = x0 + lx, y0 + ly
    if ctx.full:
        x += 9
        y += 9
    if ctx._stop == 0:
        win32api.SetCursorPos((x, y))
        if click_button:
            pyautogui.click()
    else:
        raise ValueError("正在退出")
    time.sleep(0.3)


def scan_screenshot(prepared):
    """屏幕截图并执行模板匹配。"""
    temp = pyautogui.screenshot()
    screenshot = np.array(temp)
    screenshot = cv.cvtColor(screenshot, cv.COLOR_BGR2RGB)
    result = cv.matchTemplate(screenshot, prepared, cv.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv.minMaxLoc(result)
    return {
        "screenshot": screenshot,
        "min_val": min_val,
        "max_val": max_val,
        "min_loc": min_loc,
        "max_loc": max_loc,
    }


def calculated(result, shape):
    """根据模板匹配结果计算中心点。"""
    mat_top, mat_left = result["max_loc"]
    prepared_height, prepared_width, _prepared_channels = shape
    x = int((mat_top + mat_top + prepared_width) / 2)
    y = int((mat_left + mat_left + prepared_height) / 2)
    return x, y


def drag(ctx, pt1, pt2):
    """按归一化坐标拖动鼠标。"""
    x0, y0 = _window_origin(ctx)
    x1, y1 = pt1
    lx1, ly1 = _norm_to_local_pixel(ctx, x1, y1)
    x1, y1 = x0 + lx1, y0 + ly1
    x2, y2 = pt2
    lx2, ly2 = _norm_to_local_pixel(ctx, x2, y2)
    x2, y2 = x0 + lx2, y0 + ly2
    if ctx.full:
        x1 += 9
        y1 += 9
        x2 += 9
        y2 += 9
    win32api.SetCursorPos((x1, y1))
    time.sleep(0.2)
    pyautogui.drag(x2 - x1, y2 - y1, 0.4)
    time.sleep(0.3)


def get_local(ctx, x, y, size, large=True):
    """在当前截图中截取指定中心点附近区域。"""
    sx, sy = size[0] + 60 * large, size[1] + 60 * large
    bx, by = _norm_to_local_pixel(ctx, x, y)
    return ctx.screen[
        max(0, by - sx // 2) : min(ctx.yy, by + sx // 2),
        max(0, bx - sy // 2) : min(ctx.xx, bx + sy // 2),
        :,
    ]


def save_screenshot(path, region=None, screen=None):
    """
    保存屏幕截图到指定路径。

    :param path: 保存截图的文件路径。
    :param region: 截图区域，格式为 [x1, x2, y1, y2]。
    :param screen: 可选，提供的屏幕图像（如果为 None，则调用 pyautogui 截图）。
    """
    if screen is None:
        import pyautogui

        screen = pyautogui.screenshot()
        screen = np.array(screen)

    if region:
        x1, x2, y1, y2 = region
        screen = screen[y1:y2, x1:x2]

    if screen is not None and screen.size > 0:
        cv.imwrite(path, screen)
        log.debug(f"截图保存到: {path}")
