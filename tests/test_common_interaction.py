import importlib
import types
import unittest
from unittest import mock

from tests._platform_stubs import install_platform_stubs

try:
    import numpy as np

    HAS_NUMPY = True
except ModuleNotFoundError:
    np = None
    HAS_NUMPY = False

install_platform_stubs()
interaction = (
    importlib.import_module("asu.core.common.interaction") if HAS_NUMPY else None
)


@unittest.skipUnless(HAS_NUMPY, "缺少 numpy，跳过 interaction 回归测试")
class InteractionTests(unittest.TestCase):
    @staticmethod
    def _make_ctx():
        ctx = types.SimpleNamespace(
            debug=0,
            x1=2000,
            y1=1100,
            xx=1920,
            yy=1080,
            full=False,
            _stop=0,
            screen=np.zeros((1080, 1920, 3), dtype=np.uint8),
        )
        ctx.print_stack = lambda: None
        return ctx

    def test_calc_point_converts_pixel_offset(self):
        ctx = self._make_ctx()
        result = interaction.calc_point(ctx, (0.5, 0.5), (192, 108))
        self.assertAlmostEqual(result[0], 0.6)
        self.assertAlmostEqual(result[1], 0.6)

    def test_calculated_returns_template_center(self):
        center = interaction.calculated({"max_loc": (10, 20)}, (40, 60, 3))
        self.assertEqual(center, (40, 40))

    def test_click_transforms_normalized_coordinates(self):
        ctx = self._make_ctx()
        with (
            mock.patch.object(interaction.win32api, "SetCursorPos") as set_cursor,
            mock.patch.object(interaction.pyautogui, "click") as click_mouse,
            mock.patch.object(interaction.time, "sleep", return_value=None),
        ):
            interaction.click(ctx, (0.5, 0.5), click_button=1)

        set_cursor.assert_called_once_with((1040, 560))
        click_mouse.assert_called_once_with()

    def test_click_raises_when_stopping(self):
        ctx = self._make_ctx()
        ctx._stop = 1
        with self.assertRaisesRegex(ValueError, "正在退出"):
            interaction.click(ctx, (0.2, 0.2), click_button=1)

    def test_get_local_crops_expected_size(self):
        ctx = types.SimpleNamespace(
            xx=100,
            yy=100,
            screen=np.zeros((100, 100, 3), dtype=np.uint8),
        )
        area = interaction.get_local(ctx, 0.5, 0.5, (20, 20), large=False)
        self.assertEqual(area.shape, (20, 20, 3))


if __name__ == "__main__":
    unittest.main()
