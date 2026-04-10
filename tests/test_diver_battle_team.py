import unittest

from asu.workflows.diver import DivergentUniverse


class TestDiverBattleTeam(unittest.TestCase):
    def setUp(self):
        # 可根据实际情况初始化DivergentUniverse，或Mock相关依赖
        self.diver = DivergentUniverse()
        self.diver.team_member = {}
        self.diver.team_detect = []
        self.diver.long_range_from_team = False
        self.diver.long_range = None
        self.diver.allow_e = False
        self.diver.area_state = 0
        self.diver.speed = 0
        self.diver.floor = 1
        self.diver.area_text = ""
        self.diver.get_now_area = lambda: "战斗"
        self.diver.get_screen = lambda: None
        self.diver.check = lambda *a, **kw: False
        self.diver.press = lambda x: None
        self.diver.click_position = lambda x: None
        self.diver.check_dead = lambda: None
        self.diver.close_and_exit = lambda click: None
        self.diver.init_floor = lambda: None
        self.diver.merge_text = lambda x: ""
        self.diver.ts = type("ts", (), {"find_with_box": lambda self, x: []})()

    def test_no_team_member(self):
        """测试无队伍成员时的日志输出"""
        self.diver.team_member = {}
        self.diver.team_detect = []
        # 捕获日志
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            self.diver.area()
        output = f.getvalue()
        self.assertIn("战斗站场选择: 跳过切换", output)
        self.assertIn("OCR检测到的队伍成员: 无", output)

    def test_team_detect_output(self):
        """测试有OCR检测到队伍成员时的日志输出"""
        self.diver.team_member = {}
        self.diver.team_detect = [
            {"slot": 1, "raw": "测试A", "clean": "A", "matched": 1, "long_range": 0},
            {"slot": 2, "raw": "测试B", "clean": "B", "matched": 0, "long_range": 1},
        ]
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            self.diver.area()
        output = f.getvalue()
        self.assertIn("OCR检测到的队伍成员: 1号位", output)
        self.assertIn("2号位", output)


if __name__ == "__main__":
    unittest.main()
