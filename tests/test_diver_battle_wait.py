import unittest
from unittest import mock

from asu.workflows import diver as diver_module
from asu.workflows.diver import DivergentUniverse


class TestDiverBattleWait(unittest.TestCase):
    def test_confirmed_battle_wait_has_no_default_timeout(self):
        diver = DivergentUniverse.__new__(DivergentUniverse)
        calls = []
        battle_end_results = iter(["", "", "确认界面"])

        diver._stop = False
        diver._overworld_ui_detection_enabled = True
        diver.get_screen = lambda: None
        diver.ts = type("Ts", (), {"forward": lambda self, _screen: None})()
        diver.auto_battle = lambda: calls.append("auto_battle")
        diver.run_static = lambda action_list=None: calls.append(tuple(action_list or [])) or ""
        diver.battle_end = lambda: next(battle_end_results)

        with (
            mock.patch.object(
                diver_module.time,
                "time",
                side_effect=[0, 1000, 1001, 1002],
            ),
            mock.patch.object(diver_module.time, "sleep", return_value=None),
        ):
            self.assertEqual(diver.wait_battle_end(confirmed_in_battle=True), 1)

        self.assertEqual(calls.count("auto_battle"), 3)
        self.assertFalse(diver._overworld_ui_detection_enabled)


if __name__ == "__main__":
    unittest.main()
