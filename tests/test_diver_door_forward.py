import unittest
from unittest import mock

from asu.workflows import diver as diver_module
from asu.workflows.diver import DivergentUniverse


class TestDiverDoorForward(unittest.TestCase):
    def test_blocked_interaction_is_ignored_until_door_text(self):
        diver = DivergentUniverse.__new__(DivergentUniverse)
        calls = []
        check_results = iter([0, 1])

        diver._stop = False
        diver.get_screen = lambda: None
        diver.match_overworld_ui = lambda threshold=0.88: True

        def check_f(*_args, **_kwargs):
            result = next(check_results)
            diver._last_check_f_cleaned_text = "复活装置" if result == 0 else "随意门"
            calls.append(("check_f", result))
            return result

        diver.check_f = check_f
        diver.press = lambda key, t=0.0: calls.append(("press", key, t))
        diver.align_to_door = lambda timeout=120: calls.append(
            ("align_to_door", timeout)
        ) or 1

        with (
            mock.patch.object(
                diver_module.keyops,
                "keyDown",
                side_effect=lambda key: calls.append(("keyDown", key)),
            ),
            mock.patch.object(
                diver_module.keyops,
                "keyUp",
                side_effect=lambda key: calls.append(("keyUp", key)),
            ),
            mock.patch.object(diver_module.time, "sleep", return_value=None),
        ):
            self.assertEqual(diver.move_forward_to_door_f(timeout=1), 1)

        self.assertEqual(
            calls,
            [
                ("keyDown", "w"),
                ("check_f", 0),
                ("check_f", 1),
                ("keyUp", "w"),
                ("press", "f", 0.0),
            ],
        )

    def test_repeated_blocked_interaction_times_out_without_realigning(self):
        diver = DivergentUniverse.__new__(DivergentUniverse)
        calls = []
        clock = {"value": 0.0}

        def fake_time():
            clock["value"] += 0.3
            return clock["value"]

        diver._stop = False
        diver.get_screen = lambda: None
        diver.match_overworld_ui = lambda threshold=0.88: True

        def check_f(*_args, **_kwargs):
            diver._last_check_f_cleaned_text = "复活装置"
            calls.append(("check_f", 0))
            return 0

        diver.check_f = check_f
        diver.press = lambda key, t=0.0: calls.append(("press", key, t))
        diver.align_to_door = lambda timeout=120: calls.append(
            ("align_to_door", timeout)
        ) or 1

        with (
            mock.patch.object(
                diver_module.keyops,
                "keyDown",
                side_effect=lambda key: calls.append(("keyDown", key)),
            ),
            mock.patch.object(
                diver_module.keyops,
                "keyUp",
                side_effect=lambda key: calls.append(("keyUp", key)),
            ),
            mock.patch.object(
                diver_module.time, "time", side_effect=fake_time
            ),
            mock.patch.object(diver_module.time, "sleep", return_value=None),
        ):
            self.assertEqual(diver.move_forward_to_door_f(timeout=1), 0)

        self.assertEqual(
            calls,
            [
                ("keyDown", "w"),
                ("check_f", 0),
                ("check_f", 0),
                ("check_f", 0),
                ("keyUp", "w"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
