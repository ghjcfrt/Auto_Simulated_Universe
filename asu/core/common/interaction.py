import time

import cv2 as cv
import numpy as np
import pyautogui
import win32api


def get_point(ctx, x, y, printer=print):
    """输出一个像素点在当前窗口中的归一化坐标。"""
    x = ctx.x1 - x
    y = ctx.y1 - y
    printer("获取到点：{:.4f},{:.4f}".format(x / ctx.xx, y / ctx.yy))


def calc_point(ctx, point, offset):
    """按窗口尺寸把偏移量从像素转换为归一化坐标。"""
    return (point[0] - offset[0] / ctx.xx, point[1] - offset[1] / ctx.yy)


def click_box(ctx, box):
    """点击文字识别框中心点。"""
    x = (box[0] + box[1]) / 2
    y = (box[2] + box[3]) / 2
    click(ctx, (1 - x / ctx.xx, 1 - y / ctx.yy))


def click_position(ctx, position):
    """点击像素坐标点。"""
    click_box(ctx, [position[0], position[0], position[1], position[1]])


def click(ctx, points, click_button=1):
    """统一点击逻辑，兼容归一化坐标与像素坐标。"""
    if ctx.debug == 2:
        print(points)
    ctx.print_stack()
    x, y = points
    if type(x) != int:
        x, y = ctx.x1 - int(x * ctx.xx), ctx.y1 - int(y * ctx.yy)
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
    x1, y1 = pt1
    x1, y1 = ctx.x1 - int(x1 * ctx.xx), ctx.y1 - int(y1 * ctx.yy)
    x2, y2 = pt2
    x2, y2 = ctx.x1 - int(x2 * ctx.xx), ctx.y1 - int(y2 * ctx.yy)
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
    bx, by = ctx.xx - int(x * ctx.xx), ctx.yy - int(y * ctx.yy)
    return ctx.screen[
        max(0, by - sx // 2) : min(ctx.yy, by + sx // 2),
        max(0, bx - sy // 2) : min(ctx.xx, bx + sy // 2),
        :,
    ]

