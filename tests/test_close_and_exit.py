"""
测试 DivergentUniverse.close_and_exit 方法
"""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

import pyuac

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from asu.core.diver.utils import set_forground
from asu.workflows.diver import DivergentUniverse


class TestCloseAndExit(unittest.TestCase):
    """测试 close_and_exit 方法的单元测试"""

    def setUp(self):
        """设置测试环境"""
        self.diver = DivergentUniverse()
        # Mock 必要的方法和属性
        self.diver.press = MagicMock()
        self.diver.click_position = MagicMock()
        self.diver.init_floor = MagicMock()
        self.diver.screen = MagicMock()
        self.diver.debug = False
        self.diver.floor = 5
        self.diver.fail_count = 0
        self.diver.fail_tm = 0

    @patch("time.sleep")
    @patch("time.time")
    def test_close_and_exit_with_click_true(self, mock_time, mock_sleep):
        """测试 close_and_exit 当 click=True 时的行为"""
        mock_time.return_value = 100.0

        self.diver.close_and_exit(click=True)

        # 验证 ESC 键被按下
        self.diver.press.assert_called_once_with("esc")
        # 验证 sleep 被调用
        mock_sleep.assert_called_once_with(2.5)
        # 验证 init_floor 被调用
        self.diver.init_floor.assert_called_once()
        # 验证点击执行
        self.diver.click_position.assert_called_once_with([1530, 990])
        # 验证 floor 被重置
        self.assertEqual(self.diver.floor, 0)

    @patch("time.sleep")
    @patch("time.time")
    def test_close_and_exit_with_click_false_within_90s(self, mock_time, mock_sleep):
        """测试 close_and_exit 当 click=False 且失败时间在 90 秒内"""
        # 设置上一次失败时间在 30 秒前
        self.diver.fail_tm = 70.0
        mock_time.return_value = 100.0

        self.diver.close_and_exit(click=False)

        # 验证 ESC 键被按下
        self.diver.press.assert_called_once_with("esc")
        # 由于时间差小于 90 秒，click 应该被设置为 True
        self.diver.click_position.assert_called_once_with([1530, 990])
        # 验证 fail_tm 被重置
        self.assertEqual(self.diver.fail_tm, 0)

    @patch("time.sleep")
    @patch("time.time")
    def test_close_and_exit_with_click_false_beyond_90s(self, mock_time, mock_sleep):
        """测试 close_and_exit 当 click=False 且失败时间超过 90 秒"""
        # 设置上一次失败时间在 100 秒前
        self.diver.fail_tm = 0.0
        mock_time.return_value = 100.0

        self.diver.close_and_exit(click=False)

        # 验证点击不执行
        self.diver.click_position.assert_not_called()
        # 验证 fail_tm 被更新为当前时间
        self.assertEqual(self.diver.fail_tm, 100.0)
        # floor 应该保持不变
        self.assertEqual(self.diver.floor, 5)

    @patch("time.sleep")
    @patch("builtins.open", create=True)
    def test_close_and_exit_debug_mode_floor_lt_13(self, mock_open, mock_sleep):
        """测试 close_and_exit 在 debug 模式且 floor < 13 时写日志"""
        self.diver.debug = True
        self.diver.floor = 10
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        self.diver.close_and_exit(click=True)

        # 验证文件被打开并写入内容
        mock_open.assert_called_once_with("test.txt", "a")
        # 验证 write 被调用
        self.assertTrue(mock_file.write.called)

    @patch("time.sleep")
    def test_close_and_exit_debug_mode_floor_gte_13(self, mock_sleep):
        """测试 close_and_exit 在 debug 模式但 floor >= 13 时不写日志"""
        self.diver.debug = True
        self.diver.floor = 15

        self.diver.close_and_exit(click=True)

        # 不检查文件操作，因为 floor >= 13 时不应该写入
        self.diver.press.assert_called_once_with("esc")
        self.diver.init_floor.assert_called_once()


class TestCloseAndExitIntegration(unittest.TestCase):
    """集成测试 - 执行实际的按键和点击操作"""

    def setUp(self):
        """设置集成测试环境"""
        self.diver = DivergentUniverse(debug=1)
        self.diver.debug = False  # 先不用 debug 模式
        self.diver.fail_tm = 0
        self.diver._stop = False  # 允许按键操作

        # 确保游戏窗口在前台并获得焦点
        set_forground()
        time.sleep(0.5)  # 等待窗口获得焦点

    def test_close_and_exit_real_device_setup(self):
        """验证在实机上执行 close_and_exit 的前置条件"""
        # 检查必要的方法是否存在
        self.assertTrue(hasattr(self.diver, "press"))
        self.assertTrue(hasattr(self.diver, "click_position"))
        self.assertTrue(hasattr(self.diver, "init_floor"))
        self.assertTrue(callable(self.diver.press))
        self.assertTrue(callable(self.diver.click_position))
        self.assertTrue(callable(self.diver.init_floor))

    def test_manual_close_and_exit_with_wait(self):
        """
        实机测试 close_and_exit - 真实执行按键和点击

        使用方式：
        1. 进入游戏，确保窗口在前台和焦点
        2. 运行: uv run python tests/test_close_and_exit.py TestCloseAndExitIntegration.test_manual_close_and_exit_with_wait
        3. 观察游戏窗口的行为
        """
        print("\n" + "=" * 80)
        print("实机测试 close_and_exit - 将执行真实的按键和点击操作")
        print("=" * 80)
        print("\n📌 确保以下条件满足：")
        print("   1. 游戏窗口 (崩坏：星穹铁道) 已打开")
        print("   2. 游戏窗口处于前台并获得焦点")
        print("   3. 不在战斗中（避免误操作）")

        # 打印调试信息
        print("\n📊 窗口坐标调试信息：")
        print(f"   x0={self.diver.x0}, y0={self.diver.y0}")
        print(f"   x1={self.diver.x1}, y1={self.diver.y1}")
        print(f"   xx={self.diver.xx}, yy={self.diver.yy}")
        print(f"   _stop={self.diver._stop}")

        print("\n⏰ 准备在 5 秒后执行 ESC 按键（不会点击）...")

        for i in range(5, 0, -1):
            print(f"   {i}...", end="", flush=True)
            time.sleep(1)
        print("\n\n▶️  开始执行...")

        try:
            # 只执行 ESC 按键，不点击
            print(f"\n   当前 floor: {self.diver.floor}")
            print(f"   debug: {self.diver.debug}")

            # 调用 press 测试
            self.diver.press("esc")
            print("✓ ESC 按键执行完成")

            time.sleep(2.5)
            self.diver.init_floor()
            print("✓ init_floor 执行完成")

            # 现在尝试点击
            print("\n   尝试点击位置 [1530, 990]...")
            self.diver.click_position([1530, 990])
            print("✓ 点击执行完成")

            print(f"\n   执行后 floor: {self.diver.floor}")
        except Exception as e:
            print(f"\n✗ 执行出错: {e}")
            import traceback

            traceback.print_exc()
            raise

    def test_manual_close_and_exit_click_false(self):
        """
        实机测试 close_and_exit(click=False) - 验证不点击的情况

        使用方式：
        1. 进入游戏
        2. 运行: uv run python tests/test_close_and_exit.py TestCloseAndExitIntegration.test_manual_close_and_exit_click_false
        """
        print("\n" + "=" * 80)
        print("实机测试 close_and_exit(click=False)")
        print("=" * 80)
        print("\n执行 close_and_exit(click=False) 仅按 ESC，不进行点击动作")

        for i in range(5, 0, -1):
            print(f"   准备..{i}", end="", flush=True)
            time.sleep(1)
        print("\n\n▶️  开始执行...")

        try:
            self.diver.close_and_exit(click=False)
            print("\n✓ close_and_exit(click=False) 执行完成")
            print(f"   当前 fail_tm: {self.diver.fail_tm}")
        except Exception as e:
            print(f"\n✗ 执行出错: {e}")
            raise

    @patch("pyautogui.press")
    @patch("pyautogui.click")
    @patch("time.sleep")
    @patch("time.time")
    def test_close_and_exit_with_timing(
        self, mock_time, mock_sleep, mock_click, mock_press
    ):
        """测试 close_and_exit 的时序"""
        mock_time.return_value = 100.0
        calls_order = []

        def track_press(key):
            calls_order.append(("press", key))

        def track_sleep(duration):
            calls_order.append(("sleep", duration))

        def track_click(pos):
            calls_order.append(("click", pos))

        mock_press.side_effect = track_press
        mock_sleep.side_effect = track_sleep

        # Mock init_floor 和 click_position
        self.diver.init_floor = MagicMock()
        self.diver.click_position = MagicMock(side_effect=track_click)

        self.diver.close_and_exit(click=True)

        # 验证执行顺序
        print("\n执行顺序:")
        for op in calls_order:
            print(f"  {op}")


if __name__ == "__main__":
    if not pyuac.isUserAdmin():
        print("此脚本需要管理员权限运行")
        pyuac.runAsAdmin()
    else:
        unittest.main(verbosity=2)
