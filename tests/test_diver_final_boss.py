import unittest
from unittest import mock

from asu.workflows import diver as diver_module
from asu.workflows.diver import DivergentUniverse


class TestDiverFinalBoss(unittest.TestCase):
    def make_diver(self, floor, total, area_state=0):
        diver = DivergentUniverse.__new__(DivergentUniverse)
        calls = []

        diver._stop = False
        diver.speed = 0
        diver.allow_e = False
        diver.team_member = {}
        diver.team_detect = []
        diver.long_range_from_team = False
        diver.long_range = None
        diver.area_state = area_state
        diver.floor = floor
        diver.area_floor = floor
        diver.floor_total = total
        diver.area_floor_source = "ratio"
        diver.area_raw_text = f"({floor}/{total})首领"
        diver.area_text = f"{floor}{total}首领"
        diver.portal_cnt = 0
        diver.fail_count = 0
        diver.area_now = ""
        diver.da_hei_ta_effecting = False

        diver.get_now_area = lambda: "首领"
        diver.get_screen = lambda: None
        diver.ts = type("Ts", (), {"forward": lambda self, _screen: None})()
        diver.check = lambda *_args, **_kwargs: False
        diver.check_dead = lambda: calls.append("check_dead")
        diver.skill = lambda *args, **kwargs: calls.append(("skill", args, kwargs))
        diver.press = lambda *args: calls.append(("press", args))
        diver.handle_battle_area = lambda *args, **kwargs: calls.append(
            ("handle_battle_area", args, kwargs)
        ) or 1
        diver.close_and_exit = lambda click=True: calls.append(("close_and_exit", click))
        diver.end_of_uni = lambda: calls.append("end_of_uni")
        diver.portal_opening_days = lambda *args, **kwargs: calls.append(
            ("portal_opening_days", args, kwargs)
        )

        return diver, calls

    def test_final_boss_floor_uses_total_not_hardcoded_13(self):
        diver, calls = self.make_diver(floor=9, total=9)

        with (
            mock.patch.object(diver_module.time, "sleep", return_value=None),
            mock.patch.object(diver_module.pyautogui, "click", return_value=None),
        ):
            self.assertEqual(diver.area(), 1)

        self.assertEqual(diver.area_state, 1)
        self.assertNotIn("handle_battle_area", [call[0] for call in calls if call])

    def test_non_final_boss_still_waits_for_battle_resolution(self):
        diver, calls = self.make_diver(floor=9, total=13)

        with (
            mock.patch.object(diver_module.time, "sleep", return_value=None),
            mock.patch.object(diver_module.pyautogui, "click", return_value=None),
        ):
            diver.area()

        self.assertEqual(diver.area_state, 1)
        self.assertIn(
            ("handle_battle_area", (), {"enter_timeout": 22}),
            calls,
        )

    def test_floor_greater_than_total_is_not_final_floor(self):
        diver, _calls = self.make_diver(floor=10, total=9)

        self.assertFalse(diver._is_final_floor())

    def test_completed_final_boss_closes_even_when_total_is_not_13(self):
        diver, calls = self.make_diver(floor=9, total=9, area_state=1)

        with mock.patch.object(diver_module.time, "sleep", return_value=None):
            self.assertEqual(diver.area(), 1)

        self.assertIn(("close_and_exit", True), calls)
        self.assertIn("end_of_uni", calls)


if __name__ == "__main__":
    unittest.main()
