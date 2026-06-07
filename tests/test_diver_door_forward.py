import unittest
from unittest import mock

from asu.workflows import diver as diver_module
from asu.workflows.diver import DivergentUniverse


class TestDiverDoorForward(unittest.TestCase):
    def test_blocked_interaction_releases_w_and_realigns(self):
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
        diver.align_to_door = lambda timeout=120: calls.append(("align_to_door", timeout)) or 1

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
                ("keyUp", "w"),
                ("press", "s", 0.25),
                ("align_to_door", 3),
                ("keyDown", "w"),
                ("check_f", 1),
                ("keyUp", "w"),
                ("press", "f", 0.0),
            ],
        )


if __name__ == "__main__":
    unittest.main()
