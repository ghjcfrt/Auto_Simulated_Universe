import unittest

from asu.workflows.diver import DivergentUniverse


class TestDiverNextStation(unittest.TestCase):
    def test_rest_station_enters_directly_without_reroll(self):
        diver = DivergentUniverse.__new__(DivergentUniverse)
        calls = []

        diver.debug = False
        diver.get_screen = lambda: None
        diver._get_next_priority = lambda: ["战斗", "事件", "奖励"]
        diver._scan_next_candidates = lambda priority, rois=None: (
            {"休整": {"box": [10, 20, 30, 40], "raw_text": "休整"}},
            ["休整"],
            [],
        )
        diver.click_box = lambda box: calls.append(("click_box", box))
        diver.click_img = lambda path: calls.append(("click_img", path))
        diver._get_reroll_count = lambda: self.fail("休整站点不应进入重抽逻辑")

        self.assertEqual(diver.next(), 1)
        self.assertEqual(
            calls,
            [
                ("click_box", [10, 20, 30, 40]),
                ("click_img", "divergent/confirm.png"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
