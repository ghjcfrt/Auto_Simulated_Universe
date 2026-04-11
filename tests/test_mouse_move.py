import time

import win32api
import win32con


class TestMouse:
    def __init__(self):
        self.multi = 1
        self.scale = 1
        self._stop = 0
        self.stop_move = 0

    def mouse_move(self, x, axis="x", fine=1, depth=0):
        axis = str(axis).lower()
        if axis not in ("x", "y"):
            raise ValueError("axis 必须为 'x' 或 'y'")

        if x > 30 // fine:
            y = 30 // fine
        elif x < -30 // fine:
            y = -30 // fine
        else:
            y = x
        delta = int(16.5 * y * self.multi * self.scale)
        dx, dy = (delta, 0) if axis == "x" else (0, delta)
        if self._stop == 0 and self.stop_move == 0:
            win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, dx, dy)  # 进行视角移动
        time.sleep(0.05 * fine)
        if x != y:
            if self._stop == 0:
                self.mouse_move(x - y, axis=axis, fine=fine)
            else:
                raise ValueError("正在退出")


# ===== 测试入口 =====
if __name__ == "__main__":
    # 请求管理员权限
    import pyuac

    if not pyuac.isUserAdmin():
        print("此脚本需要管理员权限运行")
        pyuac.runAsAdmin()
    else:
        t = TestMouse()

    print("=== 开始测试鼠标移动 ===")

    time.sleep(5)  # 等待一秒钟，模拟准备时间

    # print("=== 测试1：x=100, fine=1 ===")
    # t.mouse_move(100, axis="y", fine=1)

    # print("\n=== 测试2：x=100, fine=2 ===")
    # t.mouse_move(100, axis="y", fine=2)

    print("\n=== 测试3：x=25, fine=1 ===")
    t.mouse_move(5, axis="y", fine=1)

    # print("\n=== 测试4：x=-80, fine=1 ===")
    # t.mouse_move(-80, axis="y", fine=1)
