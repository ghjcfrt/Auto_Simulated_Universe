import bisect
import csv
import datetime
import json
import os
import re
import threading
import time
import traceback
from collections import defaultdict

import cv2 as cv
import keyboard
import numpy as np
import pyautogui
import pytz
import pyuac
import win32api
import win32con
import win32gui
import yaml

import asu.core.diver.keyops as keyops
from asu.core.common.paths import actions_path, img_path, logs_path, project_path
from asu.core.common.runtime_context import describe_runtime_context
from asu.core.diver.args import get_args
from asu.core.diver.config import config
from asu.core.diver.constants import DEFAULT_PORTAL_PRIOR
from asu.core.diver.keyops import KeyController
from asu.core.diver.utils import UniverseUtils, notif, set_forground
from asu.core.platform.log import log, print_exc, set_debug
from asu.core.platform.log import my_print as print

# 版本号
version = "v8.042.1"
args = get_args()


class DivergentUniverse(UniverseUtils):
    def __init__(self, debug=0, nums=-1, speed=0):
        super().__init__()
        self.is_get_team = True  # 首次进入差分宇宙后,获取队伍成员
        self.team_detect = {}  # 队伍成员检测

        self._stop_lock = threading.Lock()
        self._stop = True
        self.end = 0
        self.floor = 0

        # 允许使用秘技,秘技消耗品不足的时候就用不了
        self.allow_e = 1

        self.count = self.my_cnt = 0
        self.debug = debug
        self.nums = nums
        self.speed = speed
        self.init_tm = time.time()
        self.area_now = None
        self.action_history = []
        self.event_prior = self.read_csv(actions_path("event.csv"), name="event")
        self.character_prior = self.read_csv(actions_path("character.csv"), name="char")
        self.all_bless = self.read_csv(actions_path("bless.csv"), name="bless")
        self.bless_prior = defaultdict(int)
        self.team_member = {}
        self.ocr_time_list = [0.5]
        self.fail_tm = 0
        self.last_action_time = 0
        self.total_empty_saves = 1

        # 对黄泉角色的优化,判断是否需要使用黄泉角色
        self.quan = 0

        # 对大黑塔角色的优化,判断是否需要使用大黑塔角色,同时存在大黑塔和黄泉时,优先使用大黑塔,或许后面可以考虑自定义优先级
        self.da_hei_ta = False
        self.da_hei_ta_effecting = False  # 秘技生效中,进战清除

        self.bai_e = 0  # 是否启用白厄

        self.event_text = ""

        self.long_range = "1"  # 默认角色 选用1号位
        self.long_range_from_team = False  # 仅在识别到队伍站位后才允许按远程位切人
        self._auto_battle_last_state = None
        self._auto_battle_last_toggle = 0.0
        self._auto_battle_c_miss_count = 0
        self._auto_battle_wait_post_v = False
        self._auto_battle_stop_recognize = False
        self._auto_battle_probe_start = 0.0
        self._auto_battle_probe_seen_any = False
        self._overworld_ui_detection_enabled = True
        self._entered_universe_scene = False
        self._next_debug_last_save = 0.0
        self._event_followup = ""
        self.area_raw_text = ""
        self.area_floor = None
        self.area_floor_source = ""
        self.floor_total = 13
        self._last_area_floor_log = None
        self._area_event_count = 0
        self._area_event_layout = ""
        self._area_event_front_x = None
        self._area_event_back_right_x = None

        self.init_floor()
        self.saved_num = 0
        self.default_json_path = actions_path("default.json")
        self.default_json = self.load_actions(self.default_json_path)
        if config.weekly_mode:
            self.default_json["模式选择"][0]["actions"][1]["text"] = "周期演算"
        if debug != 2:
            pyautogui.FAILSAFE = False
        self.update_count()
        notif("开始运行", f"初始计数：{self.count}")
        set_debug(debug > 0)

    def route(self):
        self.threshold = 0.91
        self.is_get_team = True  # 启动后重置状态
        while True:
            if self._stop:
                break
            hwnd = win32gui.GetForegroundWindow()  # 根据当前活动窗口获取句柄
            Text = win32gui.GetWindowText(hwnd)
            warn_game = False
            cnt = 0
            while Text != "崩坏：星穹铁道" and Text != "云·星穹铁道" and not self._stop:
                self.lst_changed = time.time()
                if self._stop:
                    raise KeyboardInterrupt
                if not warn_game:
                    warn_game = True
                    log.warning(f"等待游戏窗口，当前窗口：{Text}")
                time.sleep(0.5)
                cnt += 1
                if cnt == 1200:
                    set_forground()
                hwnd = win32gui.GetForegroundWindow()  # 根据当前活动窗口获取句柄
                Text = win32gui.GetWindowText(hwnd)
            if self._stop:
                break
            self.loop()
        log.info("停止运行")

    def route_door_test(self):
        self.threshold = 0.91
        self.is_get_team = True
        while True:
            if self._stop:
                break

            hwnd = win32gui.GetForegroundWindow()
            text = win32gui.GetWindowText(hwnd)
            warn_game = False
            while text != "崩坏：星穹铁道" and text != "云·星穹铁道" and not self._stop:
                if not warn_game:
                    warn_game = True
                    log.warning(f"等待游戏窗口，当前窗口：{text}")
                time.sleep(0.5)
                hwnd = win32gui.GetForegroundWindow()
                text = win32gui.GetWindowText(hwnd)

            if self._stop:
                break

            self.ts.forward(self.get_screen())
            _, area_text = self._read_area_header_text()
            if not ("位面" in area_text or "区域" in area_text or "第" in area_text):
                time.sleep(0.3)
                continue

            self._entered_universe_scene = True
            self._enable_view_movement("door_test_detect_universe_scene")
            aligned = self.align_to_door(timeout=6)
            if not aligned:
                aligned = self.recover_after_align_fail()
            if not aligned:
                log.info("对门测试: 常规对门失败，开始整圈扫描")
                aligned = self._full_turn_align_scan(total_turn=360, step=12)

            if not aligned:
                log.warning("对门测试: 对门失败")
                time.sleep(0.5)
                continue

            if self.move_forward_to_door_f(timeout=20):
                log.info("对门测试: 成功触发F交互")
            else:
                log.warning("对门测试: 未触发F交互")

            time.sleep(0.4)

        log.info("对门测试已停止")

    def loop(self):
        self.ts.forward(self.get_screen())
        res = self.run_static()
        if res == "":
            _, area_text = self._read_area_header_text()
            if "位面" in area_text or "区域" in area_text or "第" in area_text:
                self._entered_universe_scene = True
                self._enable_view_movement("loop_detect_universe_scene")
                self.area()
                self.last_action_time = time.time()

            elif self._entered_universe_scene and self._check_battle_c_btn():
                # 未检查到自动战斗,已经入站,清除秘技持续
                self.da_hei_ta_effecting = False
                self.press("v")
            else:
                text = self.merge_text(
                    self.ts.find_with_box([400, 1920, 100, 600], redundancy=0)
                )
                if (
                    self.speed
                    and "转化" in text
                    and "继续战斗" not in text
                    and ("数据" in text or "过量" in text)
                ):
                    print("ready to stop")
                    time.sleep(6)
                    tm = time.time()
                    while time.time() - tm < 15:
                        print("trying to stop")
                        self.press("esc", 0.2)
                        time.sleep(2)
                        self.ts.forward(self.get_screen())
                        static_res = self.run_static(action_list=["过量转化"])
                        if static_res != "":
                            print(static_res)
                            break
                else:
                    if time.time() - self.last_action_time > 60:
                        self.click((0.5, 0.1))
                        self.click((0.5, 0.25))
                        self.last_action_time = time.time()
        else:
            self.last_action_time = time.time()
        if self.end and res == "加载界面":
            self.press("esc", 0.2)
            time.sleep(2)
            self.press("esc", 0.2)
            self._stop = True

    def do_action(self, action) -> int:
        if type(action) == str:
            return getattr(self, action)()
        if "text" in action:
            if "box" in action:
                box = action["box"]
            else:
                box = [0, 1920, 0, 1080]
            text = self.ts.find_with_box(box, redundancy=action.get("redundancy", 30))
            for i in text:
                if action["text"] in i["raw_text"]:
                    log.info(f"点击 {action['text']}:{i['box']}")
                    self.click_box(i["box"])
                    return 1
        elif "position" in action:
            log.info(f"点击 {action['position']}")
            self.click_position(action["position"])
            return 1
        elif "sleep" in action:
            self.sleep(float(action["sleep"]))
            return 1
        elif "press" in action:
            self.press(action["press"], action["time"] if "time" in action else 0)
            return 1
        return 0

    def load_actions(self, json_path):
        res = defaultdict(list)
        with open(json_path, "r", encoding="utf-8") as f:
            for i in json.load(f):
                res[i["name"]].append(i)
        return res

    def run_static(
        self, json_path=None, json_file=None, action_list=[], skip_check=0
    ) -> str:
        if json_file is None:
            if json_path is None:
                json_file = self.default_json
            else:
                json_file = self.load_actions(json_path)
        for j in action_list if len(action_list) else json_file:
            for i in json_file[j]:
                trigger = i["trigger"]
                text = self.ts.find_with_box(
                    trigger["box"], redundancy=trigger.get("redundancy", 30)
                )
                if skip_check or (
                    len(text) and trigger["text"] in self.merge_text(text)
                ):
                    log.info(f"触发 {i['name']}:{trigger['text']}")
                    actions = i["actions"]
                    log.info(f"run_static: 执行动作数={len(actions)}")
                    for step_index, action in enumerate(actions, 1):
                        action_result = self.do_action(action)
                        log.info(
                            f"run_static: {i['name']} step {step_index}/{len(actions)} result={action_result}"
                        )
                    self.action_history.append(i["name"])
                    self.action_history = self.action_history[-10:]
                    log.info(
                        f"run_static: 完成 {i['name']}，最近状态={self.action_history[-3:]}"
                    )
                    return i["name"]
        if action_list:
            log.debug(f"run_static: 未命中 {action_list}")
        return ""

    def _run_event_post_static(self) -> str:
        # 事件页退出后不能直接触发“差分宇宙中”，否则会在外层更新 area_state 前重入 area()。
        action_list = [
            action_name
            for action_name in self.default_json.keys()
            if action_name != "差分宇宙中"
        ]
        post_action = self.run_static(action_list=action_list)
        if not post_action and self._match_default_trigger_name(["差分宇宙中"]):
            log.info(
                "事件处理退出后检测到位面文本，跳过差分宇宙中默认动作，等待区域流程接管。"
            )
        return post_action

    def _match_default_trigger_name(self, action_names=None) -> str:
        # 仅检测 default.json 的触发条件，不执行动作。
        if action_names is None:
            action_names = self.default_json.keys()
        for action_name in action_names:
            if action_name not in self.default_json:
                continue
            for item in self.default_json[action_name]:
                trigger = item["trigger"]
                text = self.ts.find_with_box(
                    trigger["box"], redundancy=trigger.get("redundancy", 30)
                )
                if len(text) and trigger["text"] in self.merge_text(text):
                    return item["name"]
        return ""

    def run_static_with_retry(self, action_list, timeout=5.0, interval=0.35) -> str:
        tm = time.time()
        while time.time() - tm < timeout:
            if self._stop:
                return ""
            self.ts.forward(self.get_screen())
            res = self.run_static(action_list=action_list)
            if res:
                return res
            time.sleep(interval)
        return ""

    def click_img_with_retry(
        self, path, timeout=5.0, interval=0.35, threshold=0.9
    ) -> bool:
        tm = time.time()
        while time.time() - tm < timeout:
            if self._stop:
                return False
            self.get_screen()
            if self.click_img(path, threshold=threshold):
                return True
            time.sleep(interval)
        return False

    def recover_door_fail_by_temp_leave(self):
        log.warning("[对门] 找门失败，执行暂离重进")
        self.press("esc", 0.2)
        time.sleep(0.8)

        leave_res = self.run_static_with_retry(action_list=["退出界面"], timeout=6.0)
        if leave_res != "退出界面":
            log.warning("[对门] 未识别到“暂离”按钮，继续执行重进流程")
        time.sleep(1.2)

        # 先交互进入入口，再尝试点击“开始游戏”。
        self.press("f")
        time.sleep(0.8)

        start_clicked = False
        for attempt in range(3):
            self.get_screen()
            if self.click_img("divergent/start.png", threshold=0.88):
                start_clicked = True
                log.info("[对门] 已点击“开始游戏”按钮")
                break
            log.warning(
                f"[对门] 第 {attempt + 1} 次未识别到“开始游戏”按钮，重新尝试 divergent/start.png"
            )
            time.sleep(0.5)

        if not start_clicked:
            log.warning("[对门] 3 次未识别到“开始游戏”按钮，停止直接进入继续进度")
            return

        continue_res = self.run_static_with_retry(action_list=["模式选择"], timeout=6.0)
        if continue_res != "模式选择":
            log.warning("[对门] 未识别到“继续进度”按钮")
        self._enable_view_movement("recover_door_fail_by_temp_leave")

    def select_difficulty(self):
        time.sleep(0.5)
        self.click_position([125, 175 + int((self.diffi - 1) * (605 - 175) / 4)])

    def read_csv(self, file_path, name):
        last_error = None
        for encoding in ("utf-8-sig", "utf-8", "cp936"):
            try:
                with open(file_path, mode="r", newline="", encoding=encoding) as file:
                    reader = csv.reader(file)
                    next(reader)
                    if name == "char":
                        data = defaultdict(dict)
                        for row in reader:
                            data[row[0]].update(
                                {
                                    white: int(row[3])
                                    for white in row[1].replace("，", ",").split(",")
                                }
                            )
                            data[row[0]].update(
                                {
                                    black: -int(row[3])
                                    for black in row[2].replace("，", ",").split(",")
                                }
                            )
                    else:
                        data = {
                            row[0]: [s.replace("，", ",") for s in row[1:]]
                            for row in reader
                        }
                return data
            except UnicodeDecodeError as exc:
                last_error = exc

        raise UnicodeDecodeError(
            last_error.encoding if last_error else "unknown",
            last_error.object if last_error else b"",
            last_error.start if last_error else 0,
            last_error.end if last_error else 0,
            f"Failed to decode {file_path} with tried encodings: utf-8-sig, utf-8, cp936",
        )

    def clean_text(self, text, char=1):
        symbols = r"[!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~—“”‘’«»„…·¿¡£¥€©®™°±÷×¶§‰]，。！？；：（）【】「」《》、￥ "
        if char:
            symbols += r"0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        translator = str.maketrans("", "", symbols)
        return text.translate(translator)

    def merge_text(self, text, char=1):
        return self.clean_text(
            "".join([i["raw_text"] for i in self.ts.sort_text(text)]), char
        )

    def _area_header_roi(self):
        return [50, 525, 3, 45]

    def _normalize_area_header_ocr(self, text):
        replacements = {
            "（": "(",
            "）": ")",
            "【": "(",
            "】": ")",
            "／": "/",
            "∕": "/",
            "｜": "/",
            "|": "/",
            "\\": "/",
            "I": "1",
            "l": "1",
            "O": "0",
            "o": "0",
            "S": "5",
            "s": "5",
            "B": "8",
        }
        return "".join(replacements.get(ch, ch) for ch in str(text or ""))

    def _parse_floor_from_area_text(self, raw_text, cleaned_text=None):
        normalized = self._normalize_area_header_ocr(raw_text)
        ratio_match = re.search(r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})(?!\d)", normalized)
        if ratio_match:
            floor = int(ratio_match.group(1))
            total = int(ratio_match.group(2))
            if 1 <= floor <= total <= 20:
                return floor, total, "ratio"

        candidates = [self.clean_text(normalized, char=0)]
        if cleaned_text and cleaned_text not in candidates:
            candidates.append(cleaned_text)

        known_totals = []
        for total in [getattr(self, "floor_total", None), 13]:
            if isinstance(total, int) and total not in known_totals:
                known_totals.append(total)

        for text in candidates:
            prefix_match = re.search(r"(\d{2,4})(?=第|位面|区域)", text)
            if not prefix_match:
                prefix_match = re.match(r"(\d{2,4})", text)
            if not prefix_match:
                continue

            digits = prefix_match.group(1)
            for total in known_totals:
                total_text = str(total)
                if not digits.endswith(total_text) or len(digits) <= len(total_text):
                    continue
                floor_text = digits[: -len(total_text)]
                floor = int(floor_text)
                if 1 <= floor <= total <= 20:
                    return floor, total, "compact"

            if len(digits) >= 3:
                floor = int(digits[:-2])
                total = int(digits[-2:])
                if 1 <= floor <= total <= 20:
                    return floor, total, "compact"

        return None, None, ""

    def _read_area_header_text(self):
        self.area_raw_text = (
            self.ts.ocr_one_row(self.screen, self._area_header_roi()) or ""
        )
        self.area_text = self.clean_text(self.area_raw_text, char=0)
        floor, total, source = self._parse_floor_from_area_text(
            self.area_raw_text, self.area_text
        )
        self.area_floor = floor
        self.area_floor_source = source
        if total is not None:
            self.floor_total = total
        return self.area_raw_text, self.area_text

    def init_floor(self):
        self.portal_cnt = 0
        self.area_state = 0
        self.event_solved = 0
        self.bless_solved = 0
        self.fail_cnt = 0
        self.now_event = ""
        self._event_followup = ""
        self._area_event_count = 0
        self._area_event_layout = ""
        self._area_event_front_x = None
        self._area_event_back_right_x = None
        if hasattr(self, "keys"):
            self.keys.fff = 0
        self._release_control_keys(["w", "a", "s", "d", "f"], "init_floor")

    def _release_control_keys(self, keys=None, label="release_control_keys"):
        for key in keys or ["shift", "alt", "w", "a", "s", "d", "f"]:
            try:
                keyops.keyUp(key, pause=False)
            except Exception as exc:
                log.debug(f"{label}: 释放按键 {key} 失败: {exc}")

    def save_or_exit(self):
        print("saved_num:", self.saved_num, "save_cnt:", config.save_cnt)
        if self.saved_num < self.total_empty_saves:
            time.sleep(1.5)
            self.saved_num += 1
            self.click_position([1204, 959])
            time.sleep(1)
        else:
            self.click_position([716, 959])
        self.click_position([716, 959])
        time.sleep(1.5)

    def select_save(self):
        time.sleep(0.5)
        self.ts.forward(self.get_screen())
        txt = self.merge_text(self.ts.find_with_box([0, 1920, 0, 1080], redundancy=0))
        empty_saves = len(txt.split("无存档")) - 1
        if self.total_empty_saves == 1:
            self.total_empty_saves = empty_saves

    def _prepare_close_and_exit_input(self):
        """停止后台输入并释放可能残留的按键，给 ESC 一个干净的输入环境。"""
        self.stop_move = 1
        if hasattr(self, "keys"):
            try:
                self.keys.fff = 0
                self.keys.events.clear()
            except Exception:
                pass
        self._release_control_keys(label="close_and_exit")

    def _enable_view_movement(self, label="enable_view_movement"):
        if getattr(self, "stop_move", 0):
            log.info(f"{label}: 恢复视角移动输入 stop_move=1 -> 0")
        self.stop_move = 0

    def close_and_exit(self, click=True):
        log.info(describe_runtime_context(f"close_and_exit(click={click})"))
        self._prepare_close_and_exit_input()
        self.press("esc", 1.0)
        if self.debug and self.floor < 13:
            with open("test.txt", "a") as f:
                format_string = "%H:%M:%S"
                formatted_time = time.strftime(format_string, time.localtime())
                f.write(formatted_time + "\n")
        time.sleep(2.5)
        self.init_floor()
        if not click:
            if time.time() - self.fail_tm < 90:
                click = True
                self.fail_tm = 0
                if self.debug:
                    log.info("debug模式下连续暂离失败，标记停止运行，跳过 exit()")
                    self._stop = True
                    return
            else:
                self.fail_tm = time.time()
        if click:
            self.floor = 0
            self.click_position([1530, 990])
            time.sleep(1)

    def get_text_type(self, text, types, prefix=1):
        for i in types:
            if i[:prefix] in text:
                return i
        return None

    def test(self):
        self.find_team_member()

    def _check_battle_c_btn(self):
        # 固定 ROI：左上(0,900) 右下(127,950)，按当前分辨率等比换算。
        if self.screen is None or self.screen.size == 0:
            return False

        x1 = int(self.xx * 0 / 1920)
        x2 = int(self.xx * 127 / 1920)
        y1 = int(self.yy * 900 / 1080)
        y2 = int(self.yy * 950 / 1080)
        roi = self.screen[y1:y2, x1:x2]
        if roi is None or roi.size == 0:
            return False

        path = self.format_path("c")
        target = cv.imread(path)
        if target is None:
            log.error(f"模板读取失败: {path}")
            return False

        target_w = max(1, int(round(self.scx * target.shape[1])))
        target_h = max(1, int(round(self.scx * target.shape[0])))
        target = cv.resize(target, dsize=(target_w, target_h))
        if roi.shape[0] < target.shape[0] or roi.shape[1] < target.shape[1]:
            log.info(
                f"c按钮ROI检测: skipped(roi too small) roi={roi.shape[1]}x{roi.shape[0]} tpl={target.shape[1]}x{target.shape[0]}"
            )
            return False

        threshold = 0.80
        result = cv.matchTemplate(roi, target, cv.TM_CCORR_NORMED)
        _, max_val, _, max_loc = cv.minMaxLoc(result)

        self.tm = max_val
        self.tx = (x1 + max_loc[0] + 0.5 * target.shape[1]) / self.xx
        self.ty = (y1 + max_loc[1] + 0.5 * target.shape[0]) / self.yy
        matched = max_val >= threshold
        log.info(
            f"c按钮ROI检测: score={max_val:.4f}, threshold={threshold:.2f}, matched={int(matched)}"
        )
        return matched

    def find_team_member(self, return_details=False):
        boxes = [
            [1620, 1777, 289, 335],
            [1620, 1777, 384, 427],
            [1620, 1777, 478, 521],
            [1620, 1777, 570, 618],
        ]  # x1, x2, y1, y2
        team_member = {}
        detect_details = []

        # 调试模式：保存ROI截图
        save_roi = self.debug > 0
        if save_roi:
            roi_save_dir = logs_path("team_detection_roi")
            import os

            os.makedirs(roi_save_dir, exist_ok=True)
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 真实角色集合：内置全角色列表 + character.json 的映射值。
        # 这样即使新角色暂未写入 character.csv，也能完成队伍识别。
        all_real_characters = set()
        if hasattr(config, "all_list"):
            all_real_characters.update(config.all_list)
        if hasattr(config, "match"):
            all_real_characters.update(config.match.values())

        for i, b in enumerate(boxes):
            screen = self.get_screen()

            # 保存ROI截图
            if save_roi and screen is not None:
                x1, x2, y1, y2 = b
                roi = screen[y1:y2, x1:x2]
                if roi is not None and roi.size > 0:
                    roi_file = os.path.join(
                        roi_save_dir, f"{timestamp}_slot{i + 1}.png"
                    )
                    cv.imwrite(roi_file, roi)
                    log.debug(f"ROI截图已保存: {roi_file}")

            # 队伍配队识别：按需求不做文本预处理，直接使用原始 OCR 结果。
            raw_name = str(self.ts.ocr_one_row(screen, b) or "")
            # 仅保留 character.json 的“精确键”映射，不进行 clean/normalize。
            # name = str(config.match.get(raw_name, raw_name))
            name = config.normalize_character_name(raw_name)
            matched_csv = name in self.character_prior
            is_real_char = name in all_real_characters
            recognized = is_real_char

            # 调试日志：详细输出识别过程
            if save_roi or not recognized:
                log.info(
                    f"[队伍检测 槽位{i + 1}] 原始文本='{raw_name}' -> 规范化='{name}' -> 匹配CSV={matched_csv} | 真实角色={is_real_char}"
                )
                if name and not is_real_char:
                    log.warning(
                        f"  【未找到角色】'{name}' 不在真实角色列表中"
                        f"\n  建议：如果这是真实角色，请在 actions/character.json 中添加别名"
                        f"\n  部分真实角色: {sorted(list(all_real_characters))[:15]}"
                    )

            if recognized:
                team_member[name] = i
            if return_details:
                detect_details.append(
                    {
                        "slot": i + 1,
                        "raw": raw_name,
                        "clean": name,
                        "matched": matched_csv,
                        "is_real": is_real_char,
                        "long_range": name in config.long_range_list,
                    }
                )
        if return_details:
            return team_member, detect_details
        return team_member

    def get_now_area(self, deep=0):
        team_member, team_detect_detail = self.find_team_member(return_details=True)
        self._read_area_header_text()
        print("area_text:", self.area_text, "deep:", deep)
        if self.area_floor is not None:
            floor_log_key = (
                self.area_floor,
                self.floor_total,
                self.area_floor_source,
                self.area_text,
            )
            if floor_log_key != getattr(self, "_last_area_floor_log", None):
                log.info(
                    f"层数OCR解析: floor={self.area_floor}/{self.floor_total}, source={self.area_floor_source}, raw='{self.area_raw_text}', clean='{self.area_text}'"
                )
                self._last_area_floor_log = floor_log_key
        if (
            "位面" in self.area_text
            or "区域" in self.area_text
            or "第" in self.area_text
        ):
            if not self._overworld_ui_detection_enabled:
                self._overworld_ui_detection_enabled = True
                log.info("大世界界面检测: 已识别到位面/区域文本，恢复检测")

            check_ok = 1
            for i in team_member:
                if i not in self.team_member or team_member[i] != self.team_member[i]:
                    check_ok = 0
                    break

            if not check_ok:
                self.team_member = team_member
                print("team_member:", team_member)
                self.team_detect = team_detect_detail
                log.info(
                    "队伍识别明细: "
                    + " | ".join(
                        [
                            f"{i['slot']}号位 raw='{i['raw']}' clean='{i['clean']}' matched={int(i['matched'])} long_range={int(i['long_range'])}"
                            for i in team_detect_detail
                        ]
                    )
                )
                self.long_range_from_team = False
                for i in self.team_member:
                    # 从当前队伍中,选取处于内置远程角色列表中的第一个远程角色
                    if i in config.long_range_list:
                        self.long_range = str(
                            self.team_member[i] + 1
                        )  # 更新默认远程角色
                        self.long_range_from_team = True
                        log.info(f"队伍识别远程角色: 命中{i}, 站位={self.long_range}")
                        break
                if not self.long_range_from_team:
                    log.info(
                        f"队伍识别远程角色: 未命中, long_range_list={config.long_range_list}, 当前队伍={list(self.team_member.keys())}"
                    )

            res = self.get_text_type(
                self.area_text,
                [
                    "战斗",
                    "商店",
                    "铸造",
                    "异常",
                    "事件",
                    "财富",
                    "奖励",
                    "冒险",
                    "首领",
                    "遭遇",
                    "休整",
                    "位面",
                ],
            )
            if res == "遭遇":
                res = "战斗"
            if (res == "位面" or res is None) and deep == 0:
                self.mouse_move(20, axis="x")
                scr = self.screen
                time.sleep(0.3)
                self.get_screen()
                self.mouse_move(-20, axis="x")
                res = self.get_now_area(deep=1)
                self.screen = scr
            return res
        else:
            return None

    def find_portal(self, type=None):
        prefer_portal = {
            "战斗": 1,
            "商店": 3,
            "铸造": 3,
            "异常": 2,
            "事件": 2,
            "财富": 3,
            "奖励": 2,
            "冒险": 3,
        }
        if self.speed:
            prefer_portal = {
                "战斗": 1,
                "商店": 3,
                "铸造": 3,
                "异常": 2,
                "事件": 2,
                "财富": 3,
                "奖励": 2,
                "冒险": 3,
            }
            if (self.quan or self.bai_e) and self.allow_e:
                prefer_portal["战斗"] = 2
        if config.enable_portal_prior:
            prefer_portal.update(config.portal_prior)
        prefer_portal.update({"首领": 4, "休整": 4})
        tm = time.time()
        text = self.ts.find_with_box([0, 1920, 0, 540], forward=1, mode=2)
        portal = {"score": 0, "nums": 0, "type": ""}
        for i in text:
            if ("区" in i["raw_text"] or "域" in i["raw_text"]) and (
                i["box"][0] > 400 or i["box"][2] > 60
            ):
                portal_type = self.get_text_type(i["raw_text"], prefer_portal)
                if "冒" in i["raw_text"] or "险" in i["raw_text"]:
                    portal["nums"] += 1
                elif portal_type is not None:
                    i.update(
                        {
                            "score": prefer_portal[portal_type]
                            + 10 * (portal_type == type),
                            "type": portal_type,
                            "nums": portal["nums"] + 1,
                        }
                    )
                    if i["score"] > portal["score"]:
                        portal = i
                    else:
                        portal["nums"] = i["nums"]
        ocr_time = time.time() - tm
        self.ocr_time_list = self.ocr_time_list[-5:] + [ocr_time]
        print(f"识别时间:{int(ocr_time * 1000)}ms", text, portal)
        return portal

    def sleep(self, tm=2):
        time.sleep(tm)
        self.ts.forward(self.get_screen())

    def portal_bias(self, portal):
        return (portal["box"][0] + portal["box"][1]) // 2 - 950

    def _reset_auto_battle_runtime_state(self):
        self._auto_battle_last_state = None
        self._auto_battle_last_toggle = 0.0
        self._auto_battle_c_miss_count = 0
        self._auto_battle_wait_post_v = False
        self._auto_battle_stop_recognize = False
        self._auto_battle_probe_start = 0.0
        self._auto_battle_probe_seen_any = False

    def _read_battle_indicators(self):
        # 大世界界面只表示“未入战的常驻界面”是否可见；c/auto/auto_2 只会在已入战后出现。
        overworld_ui_visible = self.match_overworld_ui(threshold=0.9)
        c_btn = self._check_battle_c_btn()
        auto_btn, auto_score = self.check(
            "auto",
            1763 / 1920,
            47 / 1080,
            debug_save=False,
            debug_tag="auto_btn",
            threshold=0.9,
            return_score=True,
        )
        auto_2_threshold = getattr(self, "threshold", 0.8)
        auto_2_btn, auto_2_score = self.check(
            "auto_2",
            0.0583,
            0.0769,
            debug_save=False,
            debug_tag="auto_2_btn",
            threshold=auto_2_threshold,
            return_score=True,
        )
        log.info(
            f"auto检测: score={auto_score if auto_score is not None else 'n/a'}, threshold={0.80:.2f}, matched={int(auto_btn)}"
        )
        log.info(
            f"auto_2检测: score={auto_2_score if auto_2_score is not None else 'n/a'}, threshold={auto_2_threshold:.2f}, matched={int(auto_2_btn)}"
        )
        return overworld_ui_visible, c_btn, auto_btn, auto_2_btn

    def auto_battle(self):
        if self._auto_battle_stop_recognize:
            return False

        now = time.time()
        if self._auto_battle_probe_start <= 0:
            self._auto_battle_probe_start = now

        _, c_btn, auto_btn, auto_2_btn = self._read_battle_indicators()

        # c / auto / auto_2 不是入战条件，但一旦识别到，就说明已经处于战斗中。
        if auto_btn or auto_2_btn or c_btn:
            self._auto_battle_probe_seen_any = True
        elif (
            not self._auto_battle_probe_seen_any
        ) and now - self._auto_battle_probe_start >= 2.0:
            self._auto_battle_stop_recognize = True
            log.info(
                "自动战斗检测: 入战后2s内未命中auto/auto_2/c，停止后续识别并视为已开启"
            )
            return False

        if auto_btn and not c_btn and not auto_2_btn:
            self._auto_battle_c_miss_count += 1
            if (
                self._auto_battle_c_miss_count in (1, 5)
                or self._auto_battle_c_miss_count % 20 == 0
            ):
                log.info(
                    f"自动战斗检测: auto=1 但 c 未命中，连续丢失{self._auto_battle_c_miss_count}帧"
                )
        else:
            self._auto_battle_c_miss_count = 0

        state = (int(auto_btn), int(auto_2_btn), int(c_btn))
        if state != self._auto_battle_last_state:
            log.info(
                f"自动战斗检测: 已入战状态 auto={state[0]}, auto_2={state[1]}, c={state[2]}"
            )
            self._auto_battle_last_state = state

        if (
            self._auto_battle_wait_post_v
            and (not auto_btn)
            and (not auto_2_btn)
            and (not c_btn)
        ):
            self._auto_battle_wait_post_v = False
            self._auto_battle_stop_recognize = True
            log.info("自动战斗检测: v后 auto/auto_2/c 同时未命中，停止后续识别")
            return False

        # c 与 auto 同时命中时，等待后发送一次 v。
        if (
            c_btn
            and auto_btn
            and not auto_2_btn
            and time.time() - self._auto_battle_last_toggle > 1.2
        ):
            self._auto_battle_last_toggle = time.time()
            time.sleep(0.5)
            self.press("v")
            self._auto_battle_wait_post_v = True
            log.info("自动战斗检测: c+auto命中，等待0.5s后发送v")

        return auto_btn or auto_2_btn or c_btn

    def match_overworld_ui(self, threshold=0.9):
        # 大世界界面改为全屏模板匹配，不再裁固定 ROI。
        # 语义约定：matched=True 表示“未入战常驻大世界界面可见”。
        # 语义翻转：大世界界面可见=未入战，大世界界面不可见=已入战/战中。
        if self.screen is None:
            log.info("大世界界面检测: skipped(no screen)")
            return False
        roi = self.screen
        if roi is None or roi.size == 0:
            log.info("大世界界面检测: skipped(empty roi)")
            return False

        target = cv.imread(img_path("divergent", "overworld_ui.png"))
        if target is None:
            log.error("模板读取失败: divergent/overworld_ui.png")
            return False

        roi_gray = cv.cvtColor(roi, cv.COLOR_BGR2GRAY)
        target_gray = cv.cvtColor(target, cv.COLOR_BGR2GRAY)
        if (
            roi_gray.shape[0] < target_gray.shape[0]
            or roi_gray.shape[1] < target_gray.shape[1]
        ):
            log.info(
                f"大世界界面检测: skipped(roi too small) roi={roi_gray.shape[1]}x{roi_gray.shape[0]} tpl={target_gray.shape[1]}x{target_gray.shape[0]}"
            )
            return False

        result = cv.matchTemplate(roi_gray, target_gray, cv.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv.minMaxLoc(result)

        # 轻度兜底：主阈值未过时使用一个更宽松阈值，避免动画帧导致漏判。
        relaxed_threshold = max(0.0, threshold - 0.08)
        matched = max_val >= threshold or max_val >= relaxed_threshold
        log.info(
            f"大世界界面检测: score={max_val:.4f}, threshold={threshold:.2f}, relaxed={relaxed_threshold:.2f}, matched={int(matched)}"
        )
        return matched

    def battle_end(self):
        # 战斗结束后，除了祝福/失败页，还可能先进入方程/奇物等结算页。
        battle_exit_actions = [
            "方程选择",
            "祝福选择",
            "确认界面",
            "愿力满盈",
            "点击空白处关闭",
            "继续战斗",
            "过量转化",
            "战斗结束-失败",
            "选择站点卡",
            "欢愉假面",
            "金血选择",
            "加权奇物选择",
            "奇物大转盘",
            "混沌药箱",
            "丢弃",
        ]
        # 结束判定直接执行 default.json 对应动作，避免“只识别不执行”。
        exit_action = self.run_static(action_list=battle_exit_actions)
        if exit_action:
            log.info(f"战斗结束检测: 命中并执行退出动作 {exit_action}")
            return exit_action

        return ""

    def _resolve_post_battle_settlement(self, timeout=None):
        tm = time.time()
        settle_actions = [
            "方程选择",
            "祝福选择",
            "确认界面",
            "愿力满盈",
            "点击空白处关闭",
            "继续战斗",
            "过量转化",
            "战斗结束-失败",
            "选择站点卡",
            "欢愉假面",
            "金血选择",
            "加权奇物选择",
            "奇物大转盘",
            "混沌药箱",
            "丢弃",
        ]
        while timeout is None or time.time() - tm < timeout:
            if self._stop:
                return 0
            self.ts.forward(self.get_screen())

            area_text = self.clean_text(
                self.ts.ocr_one_row(self.screen, [50, 350, 3, 35]), char=0
            )
            if "位面" in area_text or "区域" in area_text or "第" in area_text:
                self._entered_universe_scene = True
                return 1

            settled = self.run_static(action_list=settle_actions)
            if settled == "战斗结束-失败":
                log.warning("战斗结算检测: 命中失败流程，返回上层处理")
                return 0
            time.sleep(0.2)

        log.warning("战斗结算检测: 超时未回到位面界面")
        return 0

    def wait_battle_end(self, timeout=None, confirmed_in_battle=False):
        if not confirmed_in_battle:
            log.warning("wait_battle_end 跳过：未确认已入战")
            return 0
        if self._overworld_ui_detection_enabled:
            self._overworld_ui_detection_enabled = False
            log.info("大世界界面检测: 已确认入战，暂停检测")
        tm = time.time()
        last_wait_log = tm
        battle_wait_actions = ["继续战斗", "确认界面", "点击空白处关闭", "过量转化"]
        while timeout is None or time.time() - tm < timeout:
            if self._stop:
                log.info("wait_battle_end: 收到停止信号，退出战斗等待")
                return 0
            self.ts.forward(self.get_screen())
            if self._stop:
                log.info("wait_battle_end: 截图后收到停止信号，退出战斗等待")
                return 0
            # auto_battle 仅负责确保自动战斗开启。
            self.auto_battle()
            # 战斗等待期间仅执行白名单动作，避免把退出目标页面提前消费掉。
            self.run_static(action_list=battle_wait_actions)
            ended_action = self.battle_end()
            if ended_action == "战斗结束-失败":
                return 0
            if ended_action:
                return 1
            now = time.time()
            if timeout is None and now - last_wait_log >= 30:
                log.info("wait_battle_end: 仍在等待战斗结束")
                last_wait_log = now
            time.sleep(0.2)
        return 0

    def _save_event_exit_probe_snapshot(
        self, reason, attempt, retries, indicators=None, followup_name=""
    ):
        screen = self.screen
        if screen is None or getattr(screen, "size", 0) == 0:
            log.warning("事件页退出探测调试截图跳过: 当前截图为空")
            return ""

        save_dir = logs_path("event_exit_probe_debug")
        os.makedirs(save_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        prefix = f"{ts}_attempt_{attempt:02d}_of_{retries:02d}_{reason}"
        raw_path = os.path.join(save_dir, f"{prefix}_raw.png")
        json_path = os.path.join(save_dir, f"{prefix}.json")

        cv.imwrite(raw_path, screen)
        debug_data = {
            "reason": reason,
            "attempt": int(attempt),
            "retries": int(retries),
            "indicators": indicators or {},
            "followup_name": followup_name,
            "raw_path": raw_path,
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(debug_data, f, ensure_ascii=False, indent=2)
        log.warning(f"事件页退出探测调试截图已保存: raw={raw_path}, meta={json_path}")
        return raw_path

    # 战斗结束后，可能直接回到位面，也可能先进入结算界面（祝福/方程/奇物等）。这个函数负责探测结算界面并做出区分。
    def _probe_event_followup(self, retries=30, interval=0.2):
        bless_like_names = [
            "祝福选择",
            "方程选择",
            "金血选择",
            "欢愉假面",
            "愿力满盈",
        ]
        item_like_names = [
            "选择站点卡",
            "加权奇物选择",
            "奇物大转盘",
            "混沌药箱",
            "丢弃",
        ]
        self.click((0.5, 0.5))
        for attempt in range(retries):
            if self._stop:
                return ""
            self.ts.forward(self.get_screen())
            overworld_ui_visible, c_btn, auto_btn, auto_2_btn = (
                self._read_battle_indicators()
            )
            indicators = {
                "overworld_ui": int(overworld_ui_visible),
                "c": int(c_btn),
                "auto": int(auto_btn),
                "auto_2": int(auto_2_btn),
            }
            log.info(
                f"事件页退出探测[{attempt + 1}/{retries}]: 大世界界面={int(overworld_ui_visible)}, c={int(c_btn)}, auto={int(auto_btn)}, auto_2={int(auto_2_btn)}"
            )
            if overworld_ui_visible:
                log.info("事件页退出探测: 检测到大世界界面")
                self._save_event_exit_probe_snapshot(
                    reason="overworld",
                    attempt=attempt + 1,
                    retries=retries,
                    indicators=indicators,
                )
                return "overworld"
            if c_btn or auto_btn or auto_2_btn:
                log.info("事件页退出探测: 检测到已入战 UI（c/auto/auto_2）")
                self._save_event_exit_probe_snapshot(
                    reason="battle_active",
                    attempt=attempt + 1,
                    retries=retries,
                    indicators=indicators,
                )
                return "battle_active"
            followup_name = self._match_default_trigger_name(
                bless_like_names + item_like_names
            )
            if followup_name:
                if followup_name in bless_like_names:
                    log.info(f"事件页退出探测: 检测到祝福界面 {followup_name}")
                    self._save_event_exit_probe_snapshot(
                        reason="bless_ui",
                        attempt=attempt + 1,
                        retries=retries,
                        indicators=indicators,
                        followup_name=followup_name,
                    )
                    return "bless_ui"
                log.info(f"事件页退出探测: 检测到奇物/站点卡界面 {followup_name}")
                self._save_event_exit_probe_snapshot(
                    reason="item_ui",
                    attempt=attempt + 1,
                    retries=retries,
                    indicators=indicators,
                    followup_name=followup_name,
                )
                return "item_ui"
            reason = "probing" if attempt < retries - 1 else "timeout"
            self._save_event_exit_probe_snapshot(
                reason=reason,
                attempt=attempt + 1,
                retries=retries,
                indicators=indicators,
                followup_name=followup_name,
            )
            if attempt == retries - 1:
                return ""
            time.sleep(interval)
        return ""

    # 进场前检测 f 键是否可按（互动点检测）
    def _check_enter_interact_f(self):
        # 使用模板匹配检测 F 按钮是否可见（不限制文案）
        return self.check_f(check_text=0)

    # 战斗、精英位面处理：触发战斗并等待结束
    def handle_battle_area(self, enter_timeout=18):
        tm = time.time()
        entered_battle = False
        overworld_ui_missing_since = None
        overworld_ui_missing_confirm_seconds = 3.0
        while time.time() - tm < enter_timeout:
            if self._stop:
                return 0
            self.get_screen()
            overworld_ui_visible = self.match_overworld_ui(threshold=0.9)
            # 语义翻转：大世界界面可见=未入战，大世界界面不可见=已入战/战中。
            if not overworld_ui_visible:
                if overworld_ui_missing_since is None:
                    overworld_ui_missing_since = time.time()
                missing_seconds = time.time() - overworld_ui_missing_since
                if missing_seconds >= overworld_ui_missing_confirm_seconds:
                    log.info(
                        f"战斗进入检测: 大世界界面连续丢失{missing_seconds:.2f}s，判定已进入战斗"
                    )
                    entered_battle = True
                    break
            else:
                overworld_ui_missing_since = None
            # 未确认入战前持续 w+左键触发。
            self.press("w", 0.45)
            pyautogui.click()

            # 未确认入战前，先检测是否可以按 f（互动点）
            if self._check_enter_interact_f():
                log.info("进场互动检测: 发现 f 可按")
                self.press("f", 0.2)
                time.sleep(0.4)
                # 按 f 后检测 default.json 中的动作
                action_triggered = self.run_static()
                if action_triggered:
                    log.info(f"进场互动检测: 执行了动作 {action_triggered}")
                time.sleep(0.3)
                # 继续回到 w 攻击逻辑的下一次迭代
                continue

            time.sleep(0.15)

        if not entered_battle:
            for _ in range(6):
                self.get_screen()
                overworld_ui_visible = self.match_overworld_ui(threshold=0.88)
                if not overworld_ui_visible:
                    if overworld_ui_missing_since is None:
                        overworld_ui_missing_since = time.time()
                    missing_seconds = time.time() - overworld_ui_missing_since
                    if missing_seconds >= overworld_ui_missing_confirm_seconds:
                        log.info(
                            f"战斗进入检测: 二次确认大世界界面连续丢失{missing_seconds:.2f}s"
                        )
                        entered_battle = True
                        break
                else:
                    overworld_ui_missing_since = None
                self.press("w", 0.2)
                pyautogui.click()
                time.sleep(0.12)
        if not entered_battle:
            log.warning("战斗位面：超时未进入战斗")
            return 0

        # 入战已确认后，再执行自动战斗确认/开启动作。
        self._reset_auto_battle_runtime_state()
        self.auto_battle()
        if not self.wait_battle_end(confirmed_in_battle=True):
            return 0
        return self._resolve_post_battle_settlement()

    # 新差分找门
    def _ensure_all_door_template(self):
        if hasattr(self, "all_door_tpl"):
            return

        self._door_sift = cv.SIFT_create() if hasattr(cv, "SIFT_create") else None
        self._door_sift_matcher = (
            cv.FlannBasedMatcher(dict(algorithm=1, trees=5), dict(checks=50))
            if self._door_sift is not None
            else None
        )
        if self._door_sift is None:
            log.error("当前 OpenCV 不支持 SIFT，无法使用 SIFT 找门")

        templates = []
        for template_name in ["all_door.png", "all_door_up.png", "all_door_down.png"]:
            tpl = cv.imread(img_path("divergent", template_name))
            if tpl is None:
                log.warning(f"模板读取失败: divergent/{template_name}")
                continue
            tpl_hsv = cv.cvtColor(tpl, cv.COLOR_BGR2HSV)
            tpl_pink, tpl_yellow, _, _ = self._make_door_color_masks(tpl_hsv)
            tpl_gray = cv.cvtColor(tpl, cv.COLOR_BGR2GRAY)
            sift_kp, sift_des = ([], None)
            if self._door_sift is not None:
                sift_kp, sift_des = self._door_sift.detectAndCompute(tpl_gray, None)
            templates.append(
                {
                    "name": template_name,
                    "image": tpl,
                    "gray": tpl_gray,
                    "edge": cv.Canny(tpl, 50, 150),
                    "pink": tpl_pink,
                    "yellow": tpl_yellow,
                    "sift_kp": sift_kp,
                    "sift_des": sift_des,
                    "sift_threshold": {
                        "all_door.png": 20,
                        "all_door_up.png": 18,
                        "all_door_down.png": 15,
                    }[template_name],
                }
            )

        if not templates:
            self.all_door_tpl = None
            log.error("模板读取失败: divergent/all_door/all_door_up/all_door_down")
            return
        self.all_door_tpl = templates

    def _enhance_mask_connectivity(self, mask_bin):
        # 与 door_template_debug 保持一致：闭开运算并过滤小连通域。
        mask_u8 = (mask_bin > 0).astype(np.uint8)
        kernel = np.ones((3, 3), dtype=np.uint8)
        mask_u8 = cv.morphologyEx(mask_u8, cv.MORPH_CLOSE, kernel, iterations=1)
        mask_u8 = cv.morphologyEx(mask_u8, cv.MORPH_OPEN, kernel, iterations=1)

        num_labels, labels, stats, _ = cv.connectedComponentsWithStats(
            mask_u8, connectivity=8
        )
        if num_labels <= 1:
            return mask_u8.astype(np.float32)

        fg_area = int(mask_u8.sum())
        min_area = max(6, int(fg_area * 0.005))
        kept = np.zeros_like(mask_u8, dtype=np.uint8)
        for comp_id in range(1, num_labels):
            area = int(stats[comp_id, cv.CC_STAT_AREA])
            if area >= min_area:
                kept[labels == comp_id] = 1

        if int(kept.sum()) == 0:
            largest_idx = 1 + int(np.argmax(stats[1:, cv.CC_STAT_AREA]))
            kept[labels == largest_idx] = 1

        return kept.astype(np.float32)

    def _normalized_mask_overlap_map(self, roi_mask, tpl_mask):
        # 与 door_template_debug 保持一致：面积归一化重叠评分。
        roi_bin = self._enhance_mask_connectivity(roi_mask)
        tpl_bin = self._enhance_mask_connectivity(tpl_mask)
        tpl_area = float(tpl_bin.sum())
        if tpl_area <= 1e-6:
            out_h = roi_bin.shape[0] - tpl_bin.shape[0] + 1
            out_w = roi_bin.shape[1] - tpl_bin.shape[1] + 1
            return np.zeros((max(1, out_h), max(1, out_w)), dtype=np.float32)
        overlap_map = cv.matchTemplate(roi_bin, tpl_bin, cv.TM_CCORR)
        return overlap_map / tpl_area

    def _make_door_color_masks(self, hsv_img):
        pink = cv.inRange(hsv_img, np.array([140, 55, 70]), np.array([175, 255, 255]))
        yellow = cv.inRange(hsv_img, np.array([18, 65, 85]), np.array([42, 255, 255]))
        # 玻璃主体：深蓝灰 #57597e -> HSV(118, 79, 126) H~113-123, S~49-109, V~96-156
        glass_cyan_green = cv.inRange(
            hsv_img, np.array([113, 49, 96]), np.array([123, 109, 156])
        )
        # 玻璃高光：高亮区域 V>180, S<60
        glass_highlight = cv.inRange(
            hsv_img, np.array([0, 0, 180]), np.array([180, 60, 255])
        )
        return pink, yellow, glass_cyan_green, glass_highlight

    def _match_all_door_fullscreen(
        self, screen_bgr, origin_x=0, origin_y=0, distance_scales=None
    ):
        self._ensure_all_door_template()
        if self.all_door_tpl is None:
            return None

        roi_h, roi_w = screen_bgr.shape[:2]
        roi_edge = cv.Canny(screen_bgr, 50, 150)
        roi_hsv = cv.cvtColor(screen_bgr, cv.COLOR_BGR2HSV)
        roi_pink, roi_yellow, _, _ = self._make_door_color_masks(roi_hsv)

        best = None
        # 门在画面里的尺寸主要取决于角色和门的距离，而不是屏幕分辨率。
        # 全窗口找门使用更宽的距离尺度；对齐 ROI 可传入较窄尺度以保持稳定。
        if distance_scales is None:
            distance_scales = [0.45, 0.55, 0.65, 0.75, 0.85, 1.0, 1.15, 1.3, 1.5, 1.7]
        for tpl in self.all_door_tpl:
            tpl_edge = tpl["edge"]
            tpl_pink = tpl["pink"]
            tpl_yellow = tpl["yellow"]
            th, tw = tpl_edge.shape[:2]
            for scale in distance_scales:
                rw, rh = max(1, int(tw * scale)), max(1, int(th * scale))
                if rw >= roi_w or rh >= roi_h:
                    continue

                scaled_edge = cv.resize(
                    tpl_edge, (rw, rh), interpolation=cv.INTER_LINEAR
                )
                scaled_pink = cv.resize(
                    tpl_pink, (rw, rh), interpolation=cv.INTER_NEAREST
                )
                scaled_yellow = cv.resize(
                    tpl_yellow, (rw, rh), interpolation=cv.INTER_NEAREST
                )

                edge_map = cv.matchTemplate(roi_edge, scaled_edge, cv.TM_CCORR_NORMED)
                pink_map = self._normalized_mask_overlap_map(roi_pink, scaled_pink)
                yellow_map = self._normalized_mask_overlap_map(
                    roi_yellow, scaled_yellow
                )

                frame_color_map = 0.70 * pink_map + 0.30 * yellow_map
                # door_template_debug 专用打分比例：frame_color 70% + edge 30%
                score_map = 0.70 * frame_color_map + 0.30 * edge_map

                _, conf, _, max_loc = cv.minMaxLoc(score_map)
                cx = origin_x + max_loc[0] + rw / 2
                cy = origin_y + max_loc[1] + rh / 2
                item = {
                    "conf": float(conf),
                    "template": tpl["name"],
                    "scale": float(scale),
                    "center_x": float(cx),
                    "center_y": float(cy),
                    "width": int(rw),
                    "height": int(rh),
                    "x": int(origin_x + max_loc[0]),
                    "y": int(origin_y + max_loc[1]),
                }
                if best is None or item["conf"] > best["conf"]:
                    best = item

        return best

    def _match_all_door_sift_fullscreen(self, screen_bgr):
        self._ensure_all_door_template()
        if (
            self.all_door_tpl is None
            or self._door_sift is None
            or self._door_sift_matcher is None
        ):
            return None

        screen_gray = cv.cvtColor(screen_bgr, cv.COLOR_BGR2GRAY)
        kp_scr, des_scr = self._door_sift.detectAndCompute(screen_gray, None)
        if des_scr is None or len(kp_scr) < 4:
            return None
        if des_scr.dtype != np.float32:
            des_scr = des_scr.astype(np.float32)

        best = None
        for tpl in self.all_door_tpl:
            kp_tpl = tpl.get("sift_kp") or []
            des_tpl = tpl.get("sift_des")
            if des_tpl is None or len(kp_tpl) < 4:
                continue
            if des_tpl.dtype != np.float32:
                des_tpl = des_tpl.astype(np.float32)

            raw_matches = self._door_sift_matcher.knnMatch(des_tpl, des_scr, k=2)
            good_matches = [
                pair[0]
                for pair in raw_matches
                if len(pair) == 2 and pair[0].distance < 0.7 * pair[1].distance
            ]
            if len(good_matches) < 4:
                item = {
                    "template": tpl["name"],
                    "matched": False,
                    "inliers": 0,
                    "inlier_ratio": 0.0,
                    "good_matches": len(good_matches),
                    "raw_matches": len(raw_matches),
                    "threshold": tpl["sift_threshold"],
                    "center_x": None,
                    "center_y": None,
                    "width": 0,
                    "height": 0,
                    "x": 0,
                    "y": 0,
                }
                if best is None or item["good_matches"] > best["good_matches"]:
                    best = item
                continue

            src_pts = np.float32([kp_tpl[m.queryIdx].pt for m in good_matches]).reshape(
                -1, 1, 2
            )
            dst_pts = np.float32([kp_scr[m.trainIdx].pt for m in good_matches]).reshape(
                -1, 1, 2
            )
            matrix, mask = cv.findHomography(src_pts, dst_pts, cv.RANSAC, 5.0)
            if matrix is None or mask is None:
                inliers = 0
                inlier_ratio = 0.0
                projected = None
            else:
                inliers = int(mask.ravel().sum())
                inlier_ratio = float(inliers / max(1, len(good_matches)))
                h, w = tpl["image"].shape[:2]
                corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(
                    -1, 1, 2
                )
                projected = cv.perspectiveTransform(corners, matrix).reshape(-1, 2)

            threshold = tpl["sift_threshold"]
            matched = inliers >= threshold and inlier_ratio >= 0.55
            if projected is None:
                center_x = center_y = None
                x = y = width = height = 0
                projected_corners = None
            else:
                center_x = float(projected[:, 0].mean())
                center_y = float(projected[:, 1].mean())
                min_xy = projected.min(axis=0)
                max_xy = projected.max(axis=0)
                x, y = int(min_xy[0]), int(min_xy[1])
                width = int(max(0, max_xy[0] - min_xy[0]))
                height = int(max(0, max_xy[1] - min_xy[1]))
                projected_corners = [
                    [float(px), float(py)] for px, py in projected.tolist()
                ]

            item = {
                "template": tpl["name"],
                "matched": matched,
                "inliers": inliers,
                "inlier_ratio": inlier_ratio,
                "good_matches": len(good_matches),
                "raw_matches": len(raw_matches),
                "threshold": threshold,
                "center_x": center_x,
                "center_y": center_y,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "projected_corners": projected_corners,
            }
            if best is None:
                best = item
                continue
            best_key = (int(best["matched"]), best["inliers"], best["inlier_ratio"])
            item_key = (int(item["matched"]), item["inliers"], item["inlier_ratio"])
            if item_key > best_key:
                best = item

        return best

    def _door_align_roi_x_range(self):
        w = self.screen.shape[1]
        x1 = int(w * 900 / 1920)
        x2 = int(w * 1030 / 1920)
        return [max(0, x1), min(w, x2)]

    def _door_match_in_align_roi(self, match, roi_x_range):
        if match is None:
            return False
        if match.get("center_x") is None:
            return False
        x1, x2 = roi_x_range
        return x1 <= match["center_x"] <= x2

    def _full_turn_align_scan(self, total_turn=360, step=12):
        turned = 0
        while turned < total_turn:
            if self._stop:
                return 0
            self.mouse_move(step, axis="x")
            time.sleep(0.5)
            turned += step
            if self.align_to_door(timeout=1):
                log.info(f"对门测试: 整圈扫描命中，累计转动{turned}")
                return 1
        return 0

    # 新差分找门
    def align_to_door(self, timeout=120):
        self._enable_view_movement("align_to_door")
        tm = time.time()
        round_count = 0  # 轮数计数器
        moves_this_round = 0  # 本轮左右移动计数

        while time.time() - tm < timeout:
            if self._stop:
                return 0
            self.get_screen()
            full_match = self._match_all_door_sift_fullscreen(self.screen)
            if full_match is None or not full_match["matched"]:
                self.mouse_move(25, axis="x")
                moves_this_round += 1
                best_tpl = full_match["template"] if full_match else "n/a"
                inliers = full_match["inliers"] if full_match else 0
                threshold = full_match["threshold"] if full_match else 0
                good_matches = full_match["good_matches"] if full_match else 0
                inlier_ratio = full_match["inlier_ratio"] if full_match else 0.0
                log.info(
                    f"[对门] SIFT门匹配不足，右移视角继续搜索 "
                    f"(best={best_tpl} inliers={inliers}/{threshold} "
                    f"good={good_matches} ratio={inlier_ratio:.3f}, "
                    f"本轮移动数: {moves_this_round})"
                )
                time.sleep(0.5)

                # 左右移动超过10次后，执行垂直移动，完成一轮
                if moves_this_round > 10:
                    self.mouse_move(5, axis="y", fine=1)
                    round_count += 1
                    moves_this_round = 0
                    log.info(f"[对门] 完成第 {round_count} 轮 (左右移动+垂直调整)")

                    # 6轮后认定为找门失败，暂离重进
                    if round_count >= 6:
                        self.recover_door_fail_by_temp_leave()
                        return 0

                continue

            align_roi_x_range = self._door_align_roi_x_range()
            if self._door_match_in_align_roi(full_match, align_roi_x_range):
                log.info(
                    f"门对准完成({full_match['template']} SIFT) "
                    f"inliers={full_match['inliers']}/{full_match['threshold']} "
                    f"good={full_match['good_matches']} "
                    f"ratio={full_match['inlier_ratio']:.3f} "
                    f"center=({full_match['center_x']:.1f},{full_match['center_y']:.1f}) "
                    f"roi_x={align_roi_x_range}, roi_y=all"
                )
                return 1

            door_center_x = full_match["center_x"]
            # 一次计算并水平转向到位；不做垂直移动。
            target_center_x = (align_roi_x_range[0] + align_roi_x_range[1]) / 2
            bias = door_center_x - target_center_x
            move_angle = int(round(bias / 16.0))
            if move_angle == 0:
                move_angle = 1 if bias > 0 else -1
            self.mouse_move(move_angle, axis="x")
            moves_this_round += 1
            log.info(
                f"[对门] 一次转向({full_match['template']} SIFT): "
                f"inliers={full_match['inliers']}/{full_match['threshold']}, "
                f"good={full_match['good_matches']}, "
                f"ratio={full_match['inlier_ratio']:.3f}, "
                f"center=({full_match['center_x']:.1f},{full_match['center_y']:.1f}), "
                f"roi_x={align_roi_x_range}, roi_y=all, "
                f"bias={bias:+.1f}, move={move_angle:+d} "
                f"(本轮移动数: {moves_this_round})"
            )
            # 每次转向后等待0.5s，再进行下一次检测。
            time.sleep(0.5)

            # 左右移动超过10次后，执行垂直移动，完成一轮
            if moves_this_round > 10:
                self.mouse_move(5, axis="y", fine=1)
                round_count += 1
                moves_this_round = 0
                log.info(f"[对门] 完成第 {round_count} 轮 (左右移动+垂直调整)")

                # 6轮后认定为找门失败，暂离重进
                if round_count >= 6:
                    self.recover_door_fail_by_temp_leave()
                    return 0

        return 0

    def move_forward_to_door_f(self, timeout=20):
        keyops.keyDown("w")
        tm = time.time()
        overworld_ui_missing_since = None
        overworld_ui_missing_confirm_seconds = 3.0
        while time.time() - tm < timeout:
            if self._stop:
                keyops.keyUp("w")
                return 0
            self.get_screen()
            # 入战判定仅依赖大世界界面；入战后才调用 auto_battle。
            overworld_ui_visible = self.match_overworld_ui(threshold=0.88)
            if not overworld_ui_visible:
                if overworld_ui_missing_since is None:
                    overworld_ui_missing_since = time.time()
                missing_seconds = time.time() - overworld_ui_missing_since
                if missing_seconds >= overworld_ui_missing_confirm_seconds:
                    log.info(f"门前入战检测: 大世界界面连续丢失{missing_seconds:.2f}s")
                    keyops.keyUp("w")
                    self._reset_auto_battle_runtime_state()
                    self.auto_battle()
                    if not self.wait_battle_end(confirmed_in_battle=True):
                        return 0
                    if not self._resolve_post_battle_settlement():
                        return 0
                    keyops.keyDown("w")
                    overworld_ui_missing_since = None
                    continue
            else:
                overworld_ui_missing_since = None
            f_result = self.check_f(
                is_in=["随意门"],
                ocr_box=[1207, 1530, 585, 640],
                debug_save=True,
                debug_tag="door_move_forward",
            )
            if f_result:
                log.info("识别到门交互F文案：随意门")
                keyops.keyUp("w")
                self.press("f")
                time.sleep(0.3)
                return 1
            if f_result == 0:
                f_text = str(getattr(self, "_last_check_f_cleaned_text", "") or "")
                if any(keyword in f_text for keyword in ["沉浸", "紧锁", "复活", "下载"]):
                    log.info(
                        f"门前前进检测: 识别到禁用交互“{f_text}”，松开W并重新对门"
                    )
                    keyops.keyUp("w")
                    self.press("s", 0.25)
                    self.align_to_door(timeout=3)
                    keyops.keyDown("w")
                    overworld_ui_missing_since = None
                    continue
            time.sleep(0.08)
        keyops.keyUp("w")
        return 0

    def aim_portal(self, portal):
        zero = bisect.bisect_left(config.angles, 0)
        while abs(self.portal_bias(portal)) > 50:
            angle = bisect.bisect_left(config.angles, self.portal_bias(portal)) - zero
            self.mouse_move(angle, axis="x")
            if abs(self.portal_bias(portal)) < 200:
                return portal
            time.sleep(0.2)
            portal_after = self.find_portal(portal["type"])
            if portal_after["score"] == 0:
                self.press("w", 1)
                portal_after = self.find_portal(portal["type"])
                if portal_after["score"] == 0:
                    return portal
            portal = portal_after
        return portal

    def forward_until(self, text_list=[], timeout=5, moving=0, chaos=0):
        log.info(
            f"[forward_until] text_list: {text_list}, timeout: {timeout}, moving: {moving}, chaos: {chaos}"
        )
        tm = time.time()
        if not moving:
            keyops.keyDown("w")
        while time.time() - tm < timeout:
            self.get_screen()
            check_result = self.check_f(check_text=0)
            log.info(f"[forward_until] check_f result: {check_result}")
            if check_result:
                keyops.keyUp("w")
                print(text_list)
                if chaos:
                    if self.check_f(is_in=["混沌", "战利品"]):
                        self.press("f")
                        for _ in range(1):
                            self.press("s", 0.2)
                            self.press("f")
                        time.sleep(0.8)
                        tmm = time.time()
                        while time.time() - tmm < 8:
                            self.ts.forward(self.get_screen())
                            area_text = self.clean_text(
                                self.ts.ocr_one_row(self.screen, [50, 350, 3, 35]),
                                char=0,
                            )
                            if (
                                "位面" in area_text
                                or "区域" in area_text
                                or "第" in area_text
                            ):
                                break
                            self.run_static()
                        time.sleep(0.6)
                        tm = time.time()
                        keyops.keyDown("w")
                if self.check_f(is_in=text_list):
                    self.press("f")
                    for _ in range(1):
                        self.press("s", 0.2)
                        self.press("f")
                    return 1
                else:
                    tm += 0.7
                    keyops.keyDown("w")
                    time.sleep(0.5)
        keyops.keyUp("w")
        return 0

    def handle_forge_area(self, timeout=12, event_timeout=12, mirror_events=False):
        tm = time.time()
        while time.time() - tm < timeout:
            if self._stop:
                return 0
            self.get_screen()
            if self.check_f(is_in=["造物调试台"]):
                self.press("a", 1)
                break
            keyops.keyDown("w")
            time.sleep(0.4)
            keyops.keyUp("w")
            time.sleep(0.1)
        else:
            return 0

        def solve_one_forge_event(timeout_sec):
            # 持续前进，直到识别到 F 事件交互。
            keyops.keyDown("w")
            try:
                event_tm = time.time()
                while time.time() - event_tm < timeout_sec:
                    if self._stop:
                        return 0
                    self.get_screen()
                    if self.check_f(is_in=["事件"]):
                        keyops.keyUp("w")
                        self.press("f")
                        time.sleep(0.4)
                        self.event()
                        return 1
                    time.sleep(0.08)
            finally:
                keyops.keyUp("w")
            return 0

        if not solve_one_forge_event(event_timeout):
            return 0

        # 奇遇中的铸造是左右对称双事件：左侧完成后切到右侧再处理一次。
        if mirror_events:
            self.press("d", 1)
            time.sleep(0.25)
            if not solve_one_forge_event(max(4, int(event_timeout * 0.8))):
                # 兜底：若直行未触发，尝试按事件文本对齐再触发。
                self.align_event("d", click=1)
                time.sleep(0.4)
                self.get_screen()
                if "事件" in self.merge_text(self.ts.find_with_box([92, 195, 54, 88])):
                    self.event()

        return 1

    def recover_after_align_fail(self):
        # 对门失败时，仅使用前进+水平转向恢复，不使用 a/s/d 位移。
        keyops.keyDown("w")
        time.sleep(0.25)
        keyops.keyUp("w")

        self.mouse_move(10, axis="x")
        time.sleep(0.5)
        if self.align_to_door(timeout=3):
            return 1

        self.mouse_move(-20, axis="x")
        time.sleep(0.5)

        keyops.keyDown("w")
        time.sleep(0.25)
        keyops.keyUp("w")

        return self.align_to_door(timeout=3)

    # 这个方法是通过本层么?
    def portal_opening_days(self, aimed=0, static=0, deep=0, retry_count=1):
        if deep > 1:
            self.close_and_exit(click=self.fail_count > 1)
            self.fail_count += 1
            return
        if deep == 0:
            self.portal_cnt += 1

        retry_count = max(1, int(retry_count))
        if retry_count > 1:
            log.info(f"[对门] 门前找门流程最多重试 {retry_count} 次")

        for attempt in range(retry_count):
            self.get_screen()
            if self.check_f(
                is_in=["随意门"],
                ocr_box=[1207, 1530, 585, 640],
                debug_save=True,
                debug_tag="portal_opening_days",
            ):
                log.info("[对门] 检测到“随意门”，直接进入门交互")
                if self.move_forward_to_door_f():
                    self.init_floor()
                    return
                log.info("[对门] 随意门快捷进入失败，回退常规对门流程")
                continue

            # 新版差分宇宙：不再依赖地图，采用“处理结束后 -> 门模板对准 -> 直行到F交互”。
            # 注意：战斗处理仅在战斗位面中通过 handle_battle_area 执行。

            aligned = self.align_to_door()
            if not aligned:
                aligned = self.recover_after_align_fail()
                if not aligned:
                    log.warning("门对准失败，进入盲走交互兜底")

            if self.move_forward_to_door_f():
                self.init_floor()
                return

            if attempt + 1 < retry_count:
                log.warning(
                    f"[对门] 第 {attempt + 1}/{retry_count} 次找门失败，继续重试"
                )

        self.close_and_exit(click=self.fail_cnt > 1)
        self.fail_cnt += 1

    def _scan_event_positions(self, timeout=15, door_retry_count=10):
        tm = time.time()
        total_events = None
        empty_candidate_retry = 0
        door_retry_count = max(1, int(door_retry_count))
        if door_retry_count > 1:
            log.info(f"[当前区域] 事件候选为空后的门复核最多重试 {door_retry_count} 次")
        keyops.keyDown("w")
        try:
            while time.time() - tm < timeout:
                if self._stop:
                    return []
                self.get_screen()
                has_text = self.get_text_position()
                if has_text:
                    keyops.keyUp("w")
                    time.sleep(0.5)
                    self.get_screen()
                    event_positions = self.get_text_position(1)
                    total_events = self._filter_event_positions(event_positions)
                    if total_events:
                        return total_events
                    raw_texts = self.ts.find_with_box(
                        [300, 1920, 0, 350], forward=1, mode=2
                    )
                    merged_text = self.merge_text(raw_texts, char=0)
                    raw_screen = self.screen.copy() if self.screen is not None else None
                    roi_box = [300, 1920, 0, 350]
                    roi_screen = (
                        raw_screen[roi_box[2] : roi_box[3], roi_box[0] : roi_box[1]]
                        if raw_screen is not None
                        else None
                    )
                    if raw_screen is not None and roi_screen is not None:
                        self._save_check_f_text_debug_images(
                            raw_screen=raw_screen,
                            roi_box=roi_box,
                            roi_screen=roi_screen,
                            ocr_text=merged_text,
                            keywords=["事件候选为空"],
                            matched=False,
                            debug_tag="anomaly_scan_positions_empty",
                        )
                        self._update_last_check_debug_json(
                            {
                                "area_now": self.area_now,
                                "area_text": getattr(self, "area_text", ""),
                                "text_positions": event_positions,
                                "raw_ocr_items": [
                                    {
                                        "raw_text": str(item.get("raw_text", "")),
                                        "box": list(item.get("box", [])),
                                        "score": item.get("score"),
                                    }
                                    for item in raw_texts
                                ],
                                "merged_text": merged_text,
                            }
                        )
                    log.info("[当前区域] 已识别到文本但未形成事件候选，开始门复核。")
                    empty_candidate_retry += 1

                if self.check_f(
                    is_in=["随意门", "事件"],
                    ocr_box=[1207, 1530, 585, 640],
                    debug_save=True,
                    debug_tag="anomaly_scan_positions",
                ):
                    f_text = self.clean_text(
                        self.ts.ocr_one_row(self.screen, [1207, 1530, 585, 640]),
                        char=0,
                    )
                    if "随意门" in f_text:
                        log.info(f"[当前区域] 扫描到随意门，直接进入门交互: {f_text}")
                        keyops.keyUp("w")
                        if self.move_forward_to_door_f():
                            return "door"
                        log.info("[当前区域] 随意门快捷进入失败，继续异常/事件扫描")
                        keyops.keyDown("w")
                        continue

                    if "事件" in f_text:
                        log.info(
                            f"[当前区域] F 模板命中事件类文案，返回事件处理流程: {f_text}"
                        )
                        return "event"

                    log.info(
                        f"[当前区域] F 模板命中但文案不是随意门: {f_text}，继续异常/事件扫描"
                    )
                    if has_text:
                        keyops.keyDown("w")
                    continue

                if empty_candidate_retry >= door_retry_count:
                    log.warning(
                        f"[当前区域] 事件候选为空后的门复核已达 {door_retry_count} 次，返回外层找门流程。"
                    )
                    return []

                if has_text:
                    keyops.keyDown("w")
                    time.sleep(1)
                    tm += 1.5
                else:
                    time.sleep(0.1)
            return []
        finally:
            keyops.keyUp("w")

    def _filter_event_positions(self, positions):
        # 过滤掉大世界界面左上角元素、右侧角色名和其他明显不属于事件标题的坐标。
        filtered = []
        for x, y in positions:
            # 左上ui
            if x < 460 and y < 180:
                continue
            # 右上ui
            if x > 1470 and y < 115:
                continue
            # 配队
            if x > 1660 and 220 < y < 635:
                continue
            # 技能
            if x > 1560 and y > 800:
                continue
            # UID
            if x < 250 and y > 1030:
                continue
            filtered.append((x, y))
        return filtered

    def _set_area_event_count(self, total_events):
        count = max(1, len(total_events))
        if count > 3:
            log.warning(
                f"[当前区域] 检测到 {count} 个事件目标，仅按前三个处理: {total_events}"
            )
            count = 3
        self._area_event_count = count
        self._area_event_layout = ""
        self._area_event_front_x = None
        self._area_event_back_right_x = None
        if count >= 3:
            candidates = sorted(total_events, key=lambda pos: pos[0])[:3]
            by_y = sorted(candidates, key=lambda pos: pos[1], reverse=True)
            if len(by_y) >= 2 and by_y[0][1] - by_y[1][1] >= 15:
                front_event = by_y[0]
            else:
                front_event = min(candidates, key=lambda pos: abs(pos[0] - 950))
            back_events = [pos for pos in candidates if pos != front_event]
            if len(back_events) < 2:
                back_events = [pos for pos in candidates if pos is not front_event]
            back_right = max(back_events, key=lambda pos: pos[0])
            self._area_event_layout = "pin_three"
            self._area_event_front_x = front_event[0]
            self._area_event_back_right_x = back_right[0]
            log.info(
                f"[当前区域] 三事件品字形: 前中={front_event}, 后右={back_right}, 全部={candidates}"
            )
        log.info(f"[当前区域] 本区域事件目标数: {self._area_event_count}")
        return count

    def _first_area_event_x(self, total_events):
        if getattr(self, "_area_event_layout", "") == "pin_three":
            return self._area_event_front_x
        return total_events[-1][0]

    def _advance_to_next_area_event(self):
        target_count = max(2, getattr(self, "_area_event_count", 2))
        log.info(f"[当前区域] 继续处理事件目标 {self.area_state + 1}/{target_count}")
        if (
            getattr(self, "_area_event_layout", "") == "pin_three"
            and self.area_state == 1
            and self._area_event_back_right_x is not None
        ):
            log.info(
                f"[当前区域] 三事件前中已处理，转向后右事件: {self._area_event_back_right_x}"
            )
            self.align_event("d", event_text=self._area_event_back_right_x, click=1)
            self.area_state += 1
            return
        if hasattr(self, "keys"):
            self.keys.fff = 1
        self.press("a", 1.3)
        time.sleep(0.4)
        if hasattr(self, "keys"):
            self.keys.fff = 0
        self.get_screen()
        if self.get_now_area() is not None:
            self.press("w", 0.3)
            time.sleep(0.6)
            self.get_screen()
            if self.check_f(check_text=0):
                self.press("f")
            else:
                self.press("s", 0.5)
                self.align_event("d")
        self.area_state += 1

    def event_score(self, text, event):
        score = 0
        event_weight = [2 * self.speed, 1, -10]
        for i in range(3):
            for e in event[i].split("-"):
                if e in text and len(e):
                    score += event_weight[i]
        return score

    def event(self):
        event_id = (-1, "")
        self.event_solved = 1
        self._event_followup = ""
        tm = time.time()
        while time.time() - tm < 20:
            title_text = self.clean_text(
                self.ts.ocr_one_row(self.screen, [185, 820, 945, 1005]), char=0
            )
            print(title_text)
            if event_id[0] == -1:
                for i, e in enumerate(self.event_prior):
                    if e in title_text and len(e) > len(event_id[1]):
                        event_id = (i, e)
                start = self.now_event == event_id[1]
                self.now_event = event_id[1]
                log.info(f"event:{event_id},start:{start}")
            if "事件" not in self.merge_text(self.ts.find_with_box([92, 195, 54, 88])):
                time.sleep(0.4)
                post_action = self._run_event_post_static()
                if post_action:
                    log.info(f"事件处理退出前的默认检测命中: {post_action}")
                self._event_followup = self._probe_event_followup()
                if self._event_followup:
                    log.info(f"事件处理退出后续状态: {self._event_followup}")
                else:
                    log.error(
                        f"事件处理异常：已离开事件页但未识别到后续界面, event_id={event_id}, now_event={self.now_event}, title={title_text}"
                    )
                return

            self.ts.forward(self.get_screen())
            if self.check(
                "arrow",
                0.8172,
                0.5000,
                mask="mask_event",
                debug_save=self.debug > 0,
                debug_tag="event_arrow",
            ):
                self.click((self.tx, self.ty))
            # 事件界面：退出
            elif self.check(
                "arrow_1",
                0.8172,
                0.5000,
                mask="mask_event",
                debug_save=self.debug > 0,
                debug_tag="event_exit",
            ):
                self.click((self.tx, self.ty))
            # 事件选择界面
            elif self.check(
                "star",
                0.8172,
                0.5000,
                mask="mask_event",
                threshold=0.9,
                debug_save=self.debug > 0,
                debug_tag="event_star",
            ):
                star_tx, star_ty = self.tx, self.ty
                if self.debug and event_id[0] == -1:
                    print(self.ts.res)
                    with open("test.txt", "a") as f:
                        format_string = "%H:%M:%S"
                        formatted_time = time.strftime(format_string, time.localtime())
                        f.write(formatted_time + " new event" + "\n")
                self.ts.forward(self.get_screen())
                clicked = 0
                selected_event = None
                text = self.ts.find_with_box([1300, 1920, 100, 1080], redundancy=30)
                raw_texts = []
                for item in text:
                    raw_item = dict(item)
                    raw_item["box"] = list(raw_item["box"])
                    raw_texts.append(raw_item)

                events = []
                event_now = None
                last_star = 0
                for i in raw_texts:
                    current_star = self.check_box(
                        "star", [1250, 1460, i["box"][2] - 30, i["box"][3] + 30]
                    )
                    current_star_y = self.ty
                    if current_star and last_star < current_star_y - 20:
                        last_star = current_star_y
                        if event_now is not None:
                            events.append(event_now)
                        event_now = {
                            "raw_text": str(i["raw_text"]).lstrip("米"),
                            "box": list(i["box"]),
                            "parts": [i],
                        }
                    else:
                        if event_now is not None:
                            event_now["raw_text"] += str(i["raw_text"])
                            event_now["parts"].append(i)
                        else:
                            event_now = {
                                "raw_text": str(i["raw_text"]),
                                "box": list(i["box"]),
                                "parts": [i],
                            }
                if event_now is not None:
                    events.append(event_now)

                event_rules = self.event_prior.get(event_id[1], ["", "", ""])
                if event_id[0] != -1:
                    selection_mode = "score"
                    for e in events:
                        e["raw_text"] = self.clean_text(e["raw_text"], 0)
                        e["score"] = self.event_score(e["raw_text"], event_rules)
                    events = sorted(events, key=lambda x: x["score"], reverse=True)
                else:
                    selection_mode = "fallback_bottom"
                    for e in events:
                        e["raw_text"] = self.clean_text(e["raw_text"], 0)
                        e["score"] = 0
                    events = sorted(events, key=lambda x: x["box"][2], reverse=True)
                    if len(events):
                        log.info(f"事件标题未命中，使用最下方选项兜底: {title_text}")

                print(
                    [{k: v for k, v in event.items() if k != "box"} for event in events]
                )

                click_targets = events if len(events) else [None]
                for i in click_targets:
                    if i is None:
                        log.warning("事件标题未命中且未分组到选项，点击 star 兜底")
                        self.click((star_tx, star_ty))
                        selected_event = {
                            "raw_text": "",
                            "box": [star_tx, star_ty, star_tx, star_ty],
                            "parts": [],
                            "score": 0,
                            "fallback": "star_center",
                        }
                    else:
                        self.click_box(i["box"])
                        selected_event = dict(i)
                        selected_event["box"] = list(selected_event["box"])
                    time.sleep(0.4)
                    self.get_screen()
                    if self.check(
                        "confirm",
                        0.8172,
                        0.5000,
                        mask="mask_event",
                        threshold=0.9,
                    ):
                        self.click((self.tx, self.ty))
                        clicked = 1
                        break
                self._update_last_check_debug_json(
                    {
                        "star_ocr": {
                            "ocr_box": [1300, 1920, 100, 1080],
                            "redundancy": 30,
                            "star_match": {
                                "x": star_tx,
                                "y": star_ty,
                                "threshold_y": star_ty - 20,
                            },
                            "raw_ocr": raw_texts,
                            "grouped_events": events,
                            "selected_event": selected_event,
                            "clicked": bool(clicked),
                            "selection_mode": selection_mode,
                            "event_id": event_id[1],
                            "title_text": title_text,
                        }
                    }
                )
                if not clicked:
                    if event_id[0] == -1:
                        log.error(
                            f"事件标题未命中，底部兜底后仍未识别到可确认选项, now_event={self.now_event}, title={title_text}"
                        )
                    else:
                        log.error(
                            f"事件选择失败：未识别到可确认选项, event_id={event_id}, now_event={self.now_event}, title={title_text}"
                        )
                    post_action = self._run_event_post_static()
                    if post_action:
                        log.info(f"事件选择失败后的默认检测命中: {post_action}")
                    self._event_followup = self._probe_event_followup()
                    if self._event_followup:
                        log.info(f"事件选择失败后的后续状态: {self._event_followup}")
                    else:
                        if event_id[0] == -1:
                            log.error(
                                f"事件标题未命中且未识别到后续界面, now_event={self.now_event}"
                            )
                        else:
                            log.error(
                                f"事件选择失败且未识别到后续界面, event_id={event_id}, now_event={self.now_event}"
                            )
                    return
                time.sleep(0.8)
                start = 0
            else:
                if not start:
                    time.sleep(0.6)
                    self.ts.forward(self.get_screen())
                    if "事件" not in self.merge_text(
                        self.ts.find_with_box([92, 195, 54, 88])
                    ):
                        post_action = self._run_event_post_static()
                        if post_action:
                            log.info(f"事件处理被中断前的默认检测命中: {post_action}")
                        self._event_followup = self._probe_event_followup()
                        if self._event_followup:
                            log.info(f"事件处理退出后续状态: {self._event_followup}")
                        else:
                            log.error(
                                f"事件处理被中断：事件页标题消失, event_id={event_id}, now_event={self.now_event}"
                            )
                        return
                self.click((0.9479, 0.9565))
                self.click((0.9479, 0.9565))
                if start:
                    self.click((0.9479, 0.9565))
                    self.click((0.9479, 0.9565))
                self.ts.forward(self.get_screen())
        log.error(
            f"事件处理超时：20秒内未完成, event_id={event_id}, now_event={self.now_event}"
        )
        post_action = self._run_event_post_static()
        if post_action:
            log.info(f"事件处理超时后的默认检测命中: {post_action}")
        self._event_followup = self._probe_event_followup()
        if self._event_followup:
            log.info(f"事件超时后的后续状态: {self._event_followup}")

    def _get_next_priority(self):
        # 用户优先级来源：程序根目录 info.yml。
        prior = None
        try:
            with open(
                project_path("info.yml"), "r", encoding="utf-8", errors="ignore"
            ) as f:
                yaml_data = yaml.safe_load(f)
            if isinstance(yaml_data, dict):
                cfg = yaml_data.get("config")
                if isinstance(cfg, dict):
                    portal_prior = cfg.get("portal_prior")
                    if isinstance(portal_prior, dict) and portal_prior:
                        prior = portal_prior
        except Exception:
            pass

        if not isinstance(prior, dict) or len(prior) == 0:
            prior = dict(DEFAULT_PORTAL_PRIOR)
        else:
            merged = dict(DEFAULT_PORTAL_PRIOR)
            merged.update(prior)
            prior = merged
        return sorted(prior.keys(), key=lambda x: prior.get(x, -999))

    def _scan_next_candidates(self, priority, rois=None):
        if rois is None:
            # 保持原有 ROI，不改识别区域，只做定位排查。
            rois = [[220, 1706, 730, 773]]
        candidates = {}
        visible_texts = []
        scan_debug = []
        for roi in rois:
            x1, x2, y1, y2 = [int(v) for v in roi]
            if self.screen is None or self.screen.size == 0:
                self.get_screen()
            crop = self.screen[y1:y2, x1:x2]
            texts = []
            used_mode = 2
            if crop is not None and crop.size > 0:
                # 使用当前帧进行 OCR，避免 find_with_box(forward=1) 内部再次截屏造成帧不一致。
                filtered = self.ts.filter_non_white(crop, mode=2)
                self.ts.forward(filtered)
                for res in self.ts.res:
                    r = dict(res)
                    r["box"] = [
                        x1 + int(res["box"][0]),
                        x1 + int(res["box"][1]),
                        y1 + int(res["box"][2]),
                        y1 + int(res["box"][3]),
                    ]
                    texts.append(r)
                # mode=2 在某些亮度/UI 状态会过严，空结果时回退到 mode=0 再试一次。
                if len(texts) == 0:
                    used_mode = 0
                    self.ts.forward(crop)
                    for res in self.ts.res:
                        r = dict(res)
                        r["box"] = [
                            x1 + int(res["box"][0]),
                            x1 + int(res["box"][1]),
                            y1 + int(res["box"][2]),
                            y1 + int(res["box"][3]),
                        ]
                        texts.append(r)
            scan_debug.append(
                {"roi": list(roi), "used_mode": used_mode, "texts": texts}
            )
            for item in texts:
                raw_text = str(item.get("raw_text", ""))
                cleaned_text = self.clean_text(raw_text, char=0)
                if len(raw_text):
                    visible_texts.append(raw_text)
                if "首领" in raw_text or "首领" in cleaned_text:
                    candidates["首领"] = item
                    continue
                if "休整" in raw_text or "休整" in cleaned_text:
                    candidates["休整"] = item
                    continue
                for area_type in priority:
                    if area_type in raw_text or area_type in cleaned_text:
                        if area_type not in candidates:
                            candidates[area_type] = item
                        break
        return candidates, visible_texts, scan_debug

    def _save_next_debug_snapshot(
        self, tag, rois, scan_debug, candidates, priority, visible_texts
    ):
        if self.screen is None or self.screen.size == 0:
            return

        now = time.time()
        if now - self._next_debug_last_save < 0.8:
            return
        self._next_debug_last_save = now

        save_dir = logs_path("next_station_debug")
        os.makedirs(save_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        raw_path = os.path.join(save_dir, f"{ts}_{tag}_raw.png")
        marked_path = os.path.join(save_dir, f"{ts}_{tag}_marked.png")
        json_path = os.path.join(save_dir, f"{ts}_{tag}.json")

        cv.imwrite(raw_path, self.screen)
        marked = self.screen.copy()

        for roi in rois:
            x1, x2, y1, y2 = [int(v) for v in roi]
            cv.rectangle(marked, (x1, y1), (x2, y2), (255, 140, 0), 2)

        for group in scan_debug:
            for item in group.get("texts", []):
                box = item.get("box")
                if not box or len(box) != 4:
                    continue
                x1, x2, y1, y2 = [int(v) for v in box]
                cv.rectangle(marked, (x1, y1), (x2, y2), (180, 180, 180), 1)

        for area_type, item in candidates.items():
            box = item.get("box")
            if not box or len(box) != 4:
                continue
            x1, x2, y1, y2 = [int(v) for v in box]
            cv.rectangle(marked, (x1, y1), (x2, y2), (0, 220, 0), 2)
            rank = priority.index(area_type) + 1 if area_type in priority else 99
            cv.putText(
                marked,
                f"#{rank}",
                (x1, max(20, y1 - 6)),
                cv.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 220, 0),
                2,
            )

        cv.imwrite(marked_path, marked)
        debug_data = {
            "tag": tag,
            "priority": priority,
            "visible_texts": visible_texts[:30],
            "rois": rois,
            "candidates": {
                k: {"raw_text": str(v.get("raw_text", "")), "box": v.get("box")}
                for k, v in candidates.items()
            },
            "scan_debug": [
                {
                    "roi": g.get("roi"),
                    "texts": [
                        {"raw_text": str(t.get("raw_text", "")), "box": t.get("box")}
                        for t in g.get("texts", [])
                    ],
                }
                for g in scan_debug
            ],
            "raw_path": raw_path,
            "marked_path": marked_path,
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(debug_data, f, ensure_ascii=False, indent=2)
        log.warning(f"下一站调试截图已保存: {marked_path}")

    def _pick_best_visible_next(self, candidates, priority):
        for area_type in priority:
            if area_type in candidates:
                return area_type
        return None

    def _list_visible_next_by_priority(self, candidates, priority, max_options=3):
        visible = [area_type for area_type in priority if area_type in candidates]
        return visible[:max_options]

    def _get_reroll_count(self):
        # (678, 945) 参考点，这里使用其附近 ROI 识别“重抽 N”。
        reroll_roi = [560, 900, 920, 980]
        texts = self.ts.find_with_box(reroll_roi, forward=1, mode=2)
        merged = self.merge_text(texts, char=0)
        if "重抽" not in merged:
            return None
        match = re.search(r"重抽\D*(\d+)", merged)
        if match is None:
            return None
        return int(match.group(1))

    def next(self):
        priority = self._get_next_priority()
        candidates = {}
        visible_texts = []
        scan_debug = []
        rois = [[220, 1706, 730, 800]]
        # “选择下一站”文本会有短暂淡入，最多重试 3 次降低空识别概率。
        for _ in range(3):
            self.get_screen()
            candidates, visible_texts, scan_debug = self._scan_next_candidates(
                priority, rois=rois
            )
            if len(candidates):
                break
            time.sleep(0.12)

        # 首领层不会出现其他可选项：直接点击并使用首领专用确认坐标
        if "首领" in candidates:
            if self.debug:
                self._save_next_debug_snapshot(
                    "next_boss", rois, scan_debug, candidates, priority, visible_texts
                )
            self.click_box(candidates["首领"]["box"])
            time.sleep(0.2)
            self.click_position([958, 965])
            return 1

        # 休整站点是必进项，通常不会和其他站点同时出现；识别到后不参与重抽。
        if "休整" in candidates:
            log.info("选择下一站：识别到休整，直接进入")
            if self.debug:
                self._save_next_debug_snapshot(
                    "next_rest", rois, scan_debug, candidates, priority, visible_texts
                )
            self.click_box(candidates["休整"]["box"])
            time.sleep(0.2)
            self.click_img("divergent/confirm.png")
            return 1

        visible = self._list_visible_next_by_priority(candidates, priority)
        if visible:
            log.info(f"下一站识别候选数量: {len(visible)}，候选: {visible}")
            if self.debug:
                self._save_next_debug_snapshot(
                    "next_ok", rois, scan_debug, candidates, priority, visible_texts
                )
        else:
            self._save_next_debug_snapshot(
                "next_fail", rois, scan_debug, candidates, priority, visible_texts
            )
            if len(visible_texts):
                log.warning(
                    f"选择下一站：未识别到可用词汇坐标，OCR原文: {visible_texts[:8]}"
                )
            else:
                log.warning("选择下一站：未识别到可用词汇坐标")
            return 0

        top_two = priority[:2]
        for area_type in top_two:
            if area_type in candidates:
                self.click_box(candidates[area_type]["box"])
                time.sleep(0.2)
                self.click_img("divergent/confirm.png")
                return 1

        if len(top_two) == 2:
            log.info(f"前两优先级均未出现: {top_two}")

        reroll_count = self._get_reroll_count()
        if reroll_count is not None and reroll_count > 0:
            # 若 OCR 未给出“重抽”框坐标，回退为当前候选最高优先级并确认。
            reroll_box = None
            reroll_texts = self.ts.find_with_box(
                [560, 900, 920, 980], forward=1, mode=2
            )
            for item in reroll_texts:
                if "重抽" in str(item.get("raw_text", "")):
                    reroll_box = item["box"]
                    break
            if reroll_box is not None:
                self.click_box(reroll_box)
            else:
                best_type = self._pick_best_visible_next(candidates, priority)
                if best_type is None:
                    log.warning("未识别到“重抽”坐标，且当前无可用候选")
                    return 0
                log.warning(f"未识别到“重抽”坐标，回退选择当前最高优先级：{best_type}")
                self.click_box(candidates[best_type]["box"])
                time.sleep(0.2)
                self.click_position([1156, 970])
                return 1

            time.sleep(0.5)
            self.get_screen()
            candidates, visible_texts, scan_debug = self._scan_next_candidates(
                priority, rois=rois
            )
            visible = self._list_visible_next_by_priority(candidates, priority)
            if visible:
                log.info(f"重抽后识别候选数量: {len(visible)}，候选: {visible}")
            for area_type in priority[:2]:
                if area_type in candidates:
                    self.click_box(candidates[area_type]["box"])
                    time.sleep(0.2)
                    self.click_img("divergent/confirm.png")
                    return 1

        # 无可重抽次数（或重抽后仍无前二）时，按优先级选可见项并点击“确定”。
        final_type = self._pick_best_visible_next(candidates, priority)
        if final_type is None:
            return 0

        self.click_box(candidates[final_type]["box"])
        time.sleep(0.2)
        self.click_img("divergent/confirm.png")
        return 1

    # 事件文本对齐：通过扫描事件标题坐标，辅助调整角色位置到达最佳交互点。
    def find_event_text(self, save=0):
        self.get_screen()
        raw_screen = self.screen.copy() if self.screen is not None else None
        roi_box = [300, 1600, 0, 350]
        roi_screen = (
            raw_screen[roi_box[2] : roi_box[3], roi_box[0] : roi_box[1]]
            if raw_screen is not None
            else None
        )
        event_positions = self._filter_event_positions(self.get_text_position(clean=1))
        event_positions = sorted(event_positions, key=lambda x: x[0])
        if len(event_positions):
            res = event_positions[-1][0]
            if save and raw_screen is not None and roi_screen is not None:
                self._save_check_f_text_debug_images(
                    raw_screen=raw_screen,
                    roi_box=roi_box,
                    roi_screen=roi_screen,
                    ocr_text="",
                    keywords=["event_positions"],
                    matched=True,
                    debug_tag="find_event_text_pos",
                    save_dir_name="event_text_debug",
                    extra_data={
                        "event_positions": [list(pos) for pos in event_positions],
                        "selected_x": res,
                        "selected_text": "",
                        "source": "get_text_position",
                    },
                )
            return res
        time.sleep(0.3)
        text = self.ts.find_with_box(roi_box, forward=1, mode=2)
        merged_text = self.merge_text(text, char=0)
        res = 0
        event_text = ""
        debug_res = []
        print("event_text:", text)
        preferred_text = self.event_text or ""
        for i in text:
            box = i["box"]
            if (
                "ms" in i["raw_text"]
                or "状态效" in i["raw_text"]
                or len(i["raw_text"]) < 2
                or (box[0] > 1470 and box[2] < 75)
                or (box[0] > 1800 and box[2] < 120)
                or (box[0] > 1600 and box[2] > 290)
                or (box[1] < 400 and box[3] < 160)
            ):
                continue
            if (
                "?" not in i["raw_text"]
                and "？" not in i["raw_text"]
                and len(self.clean_text(i["raw_text"], 1)) == 0
            ):
                continue
            w, h = box[1] - box[0], box[3] - box[2]
            if w < 40 or h > 45:
                continue
            if (
                (box[0] + box[1]) // 2 > res
                or (preferred_text and preferred_text in i["raw_text"])
                or (preferred_text and i["raw_text"] in preferred_text)
            ):
                res = (box[0] + box[1]) // 2
                event_text = i["raw_text"]
            debug_res.append(i)
        if self.debug:
            print(debug_res, res, event_text)
        if res == 0:
            scr = np.copy(self.screen)
            mask = np.zeros(scr.shape[:2], dtype=np.uint8)
            mask[np.sum((scr - np.array([255, 255, 255])) ** 2, axis=-1) <= 400] = 255
            kernel = np.ones((20, 6), np.uint8)
            mask = cv.dilate(mask, kernel, iterations=2)
            contours, _ = cv.findContours(
                mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE
            )
            for contour in contours:
                x, y, rect_w, rect_h = cv.boundingRect(contour)
                box = [x, x + rect_w, y, y + rect_h]
                if rect_w < 90 or rect_h > 70 or box[0] < 400 or box[1] > 1470:
                    continue
                if abs(res - 950) > abs((box[0] + box[1]) // 2 - 950):
                    res = (box[0] + box[1]) // 2
        if save:
            if raw_screen is not None and roi_screen is not None:
                self._save_check_f_text_debug_images(
                    raw_screen=raw_screen,
                    roi_box=roi_box,
                    roi_screen=roi_screen,
                    ocr_text=merged_text,
                    keywords=["event_text"],
                    matched=bool(res),
                    debug_tag="find_event_text_ocr",
                    save_dir_name="event_text_debug",
                    extra_data={
                        "event_positions": [list(pos) for pos in event_positions],
                        "raw_ocr_items": [
                            {
                                "raw_text": str(item.get("raw_text", "")),
                                "box": list(item.get("box", [])),
                                "score": item.get("score"),
                            }
                            for item in text
                        ],
                        "debug_res": [
                            {
                                "raw_text": str(item.get("raw_text", "")),
                                "box": list(item.get("box", [])),
                                "score": item.get("score"),
                            }
                            for item in debug_res
                        ],
                        "preferred_text": preferred_text,
                        "selected_x": res,
                        "selected_text": event_text,
                    },
                )
            self.event_text = event_text
        return res

    def check_pop(self):
        in_time = time.time()
        while True:
            time.sleep(0.5)
            self.ts.forward(self.get_screen())
            if self.get_now_area() is not None:
                break
            if self.run_static(action_list=["点击空白处关闭"]):
                time.sleep(0.3)
            elif time.time() - in_time > 3:
                break

    def align_event(self, key, deep=0, event_text=None, click=0):
        find = 0
        found_by_find_event_text = False
        if deep == 0 and key == "d" and event_text is None:
            event_text = self.find_event_text(1)
            if not event_text:
                self.press("s", 1)
            else:
                find = 1
                found_by_find_event_text = True
        if not find and not event_text:
            event_text = self.find_event_text(1)
            if event_text:
                found_by_find_event_text = True
        self.get_screen()
        if self.check_f(is_in=["事件", "奖励", "遭遇", "交易"]):
            self.press("f")
            return found_by_find_event_text

        if not event_text:
            event_text = 950
        if event_text and event_text < 910 and key == "d":
            key = "a"

        log.info(f"align_event: {event_text}, key: {key}")

        if event_text:
            if abs(950 - event_text) >= 50:
                self.press(key, 0.2)
                time.sleep(0.5)
            event_text_after = self.find_event_text(1)
            if not event_text_after:
                for retry in range(3):
                    keyops.keyDown("w")
                    time.sleep(0.25)
                    keyops.keyUp("w")
                    time.sleep(0.25)
                    event_text_after = self.find_event_text(1)
                    if event_text_after:
                        log.info(
                            f"align_event: event_text_after 重扫命中, retry={retry + 1}, value={event_text_after}"
                        )
                        break
            if event_text_after:
                found_by_find_event_text = True
                sub = event_text - event_text_after
                if key == "a":
                    sub = -sub
                print("sub:", sub)
                log.info(f"event_text_after: {event_text_after}, sub: {sub}")
            else:
                sub = 100000

            if sub < 60:
                sub = 100

            if sub < 400:
                sub = int((event_text_after - 950) / sub)
                sub = min(3, max(-3, int(sub)))
            else:
                sub = 2

            if abs(950 - event_text) < 50:
                sub = 0

            for _ in range(sub):
                self.press("d", 0.2)
                time.sleep(0.5)

            for _ in range(-sub):
                self.press("a", 0.2)
                time.sleep(0.5)

            if click:
                pyautogui.click()
                self.check_pop()

            self.forward_until(
                ["事件", "奖励", "遭遇", "交易"], timeout=2.5, moving=0, chaos=1
            )

        else:
            if deep < 3:
                self.press("w", [0, 0.3, 0.5][deep])
                return self.align_event(key, deep + 1)
            return found_by_find_event_text

        return found_by_find_event_text

    def skill(self, quan=0):
        if not self.allow_e:
            return
        self.press("e")
        time.sleep(0.4)
        self.get_screen()
        if self.check("e", 0.4995, 0.7500):
            self.solve_snack()
            if quan and self.allow_e:
                time.sleep(0.4)
            else:
                time.sleep(1.5 * self.allow_e)

    def check_dead(self):
        self.get_screen()
        if self.check("divergent/sile", 0.5010, 0.7519, threshold=0.96):
            self.click_position([1188, 813])
            time.sleep(2.5)

    def area(self):
        area_now = self.get_now_area()
        just_switched_role = False
        time.sleep(0.5)
        if self.get_now_area() != area_now or area_now is None:
            return 0
        if self.area_state == -1:
            self.close_and_exit(click=False)
            return 1
        now_floor = self.area_floor if self.area_floor is not None else self.floor
        if self.area_floor is None:
            total = getattr(self, "floor_total", 13)
            for i in range(1, total + 1):
                if f"{i}{total}" in self.area_text:
                    now_floor = i
        if now_floor != self.floor:
            if now_floor < self.floor:
                log.warning(
                    f"层数OCR回退: current={self.floor}, parsed={now_floor}, source={self.area_floor_source}, raw='{self.area_raw_text}', clean='{self.area_text}'"
                )
                self.init_floor()
            self.floor = now_floor
            if self.floor in [5, 10]:
                time.sleep(3)
        time.sleep(0.8)

        if self.area_state == 0:
            speed_mode_enabled = bool(self.speed or getattr(config, "speed_mode", 0))

            # 判断队伍成员状态
            da_hei_ta_in_team = "大黑塔" in self.team_member
            bai_e_in_team = "白厄" in self.team_member
            huang_quan_in_team = "黄泉" in self.team_member

            # 判断秘技状态
            da_hei_ta_has_skill = "大黑塔" in config.skill_char
            bai_e_has_skill = "白厄" in config.skill_char
            huang_quan_has_skill = "黄泉" in config.skill_char

            # 非速通模式：不启用白厄/黄泉/大黑塔优先逻辑，默认远程站场。
            self.da_hei_ta = False
            self.bai_e = 0
            self.quan = 0
            if speed_mode_enabled and self.allow_e:
                # 速通模式优先级: 白厄 -> 大黑塔 -> 黄泉
                if bai_e_in_team and bai_e_has_skill:
                    self.bai_e = 1
                elif da_hei_ta_in_team and da_hei_ta_has_skill:
                    self.da_hei_ta = True
                elif huang_quan_in_team and huang_quan_has_skill:
                    self.quan = 1

            # 决策站场角色
            # 默认优先远程角色；仅速通模式时优先秘技角色。
            selected_slot = None
            if speed_mode_enabled and self.allow_e:
                if self.da_hei_ta:
                    selected_slot = str(self.team_member["大黑塔"] + 1)
                elif self.bai_e and area_now == "战斗":
                    selected_slot = str(self.team_member["白厄"] + 1)
                elif self.quan and area_now == "战斗":
                    selected_slot = str(self.team_member["黄泉"] + 1)

            if (
                selected_slot is None
                and self.long_range_from_team
                and self.long_range
                and str(self.long_range).isdigit()
            ):
                selected_slot = str(self.long_range)

            if selected_slot is not None:
                self.press(selected_slot)
                just_switched_role = True
                log.info(
                    f"战斗站场选择: slot={selected_slot}, speed_mode={int(speed_mode_enabled)}"
                )
            else:
                log.info("战斗站场选择: 跳过切换(未识别到远程角色站位)")
                # 输出OCR检测到的队伍成员信息
                if self.team_detect:
                    log.info(
                        "OCR检测到的队伍成员: "
                        + " | ".join(
                            [
                                f"{i.get('slot', '?')}号位 raw='{i.get('raw', '')}' clean='{i.get('clean', '')}' matched={int(i.get('matched', 0))} long_range={int(i.get('long_range', 0))}"
                                for i in self.team_detect
                            ]
                        )
                    )
                else:
                    log.info("OCR检测到的队伍成员: 无")

        self.ts.forward(self.get_screen())
        if self.check("divergent/arrow", 0.7833, 0.9231, threshold=0.95):
            keyops.keyDown("alt")
            time.sleep(0.2)
            self.click_position([413, 79])
            keyops.keyUp("alt")
        time.sleep(0.7)

        self.check_dead()

        if area_now is not None:
            self.area_now = area_now
        else:
            area_now = self.area_now

        if self.portal_cnt > 1:
            # 这里考虑的是全局异常暂离次数达到2次,就结束本次探索,或许可以考虑改为单个区域
            self.close_and_exit(click=False)
            return 1

        log.info(
            f"floor:{self.floor}, state:{self.area_state}, area:{area_now}, text:{self.area_text}"
        )

        if area_now in ["异常"]:
            log.info(
                f"[area_now] Detected area: {area_now}, area_state: {self.area_state}"
            )
            # 异常层：先找事件；找不到事件时，再用 F + 文案复核是否为随意门。
            if self.area_state == 0:
                pyautogui.click()
                self.check_pop()
                time.sleep(0.4)

                handled_anomaly_event = False
                while not self._stop:
                    total_events = self._scan_event_positions()
                    if total_events == "door":
                        log.info(
                            "[当前区域] 已识别随意门并进入门交互流程，结束本轮事件扫描。"
                        )
                        return 1
                    if total_events == "event":
                        log.info("[当前区域] 扫描到事件类F文案，继续事件对齐流程。")
                        handled_anomaly_event = True
                        self.align_event("d", click=1)
                    elif not total_events:
                        if handled_anomaly_event:
                            log.info("[当前区域] 异常事件已处理完，开始找门流程。")
                            self.area_state = 1
                            break
                        log.info("[当前区域] 异常未识别到事件，按战斗异常处理。")
                        if self.handle_battle_area():
                            self.area_state = 1
                            return 1
                        else:
                            self.close_and_exit(click=self.fail_count > 1)
                            self.fail_count += 1
                            return 1
                    else:
                        self._set_area_event_count(total_events)
                        log.info(
                            f"[当前区域] 异常识别到 {len(total_events)} 个事件: {total_events}"
                        )
                        handled_anomaly_event = True
                        self.align_event(
                            "d",
                            event_text=self._first_area_event_x(total_events),
                            click=1,
                        )
                    time.sleep(1)

                    self.get_screen()
                    self.ts.forward(self.screen)
                    raw_text = self.ts.find_with_box([90, 190, 60, 101])
                    log.info(f"[当前区域] OCR 原始结果: {raw_text}")

                    detected_text = self.merge_text(raw_text)
                    log.info(f"[当前区域] 合并后的识别文本: {detected_text}")

                    if not detected_text:
                        log.info("[当前区域] F 已按下但事件文本尚未稳定，继续扫描。")
                        continue

                    event_res = ""
                    if "事件" in detected_text:
                        log.info("[当前区域] 识别到事件，开始处理事件逻辑。")
                        event_res = self.run_static(action_list=["事件选择"])
                        if event_res:
                            log.info(f"[当前区域] 已执行事件动作: {event_res}")
                        else:
                            log.warning("[当前区域] 未触发事件动作，直接执行事件处理。")
                            self.event()

                        followup = self._event_followup
                        self.area_state = 1
                        if followup == "battle_active":
                            log.info(
                                "[当前区域] 事件页退出后已进入战斗，交给外层轮询处理；战斗后进入找门流程"
                            )
                            return 1
                        if followup in ["bless_ui", "item_ui"]:
                            log.info(
                                f"[当前区域] 事件页退出后进入后续界面: {followup}；处理后进入找门流程"
                            )
                            return 1
                        if followup == "overworld":
                            log.info(
                                "[当前区域] 事件页退出后回到大世界，进入找门流程。"
                            )
                        elif followup:
                            log.info(
                                f"[当前区域] 事件页退出后续状态: {followup}，进入找门流程。"
                            )
                        else:
                            log.info("[当前区域] 事件已处理，进入找门流程。")
                        break
                    else:
                        log.info(
                            f"[当前区域] 当前文本不是事件页，继续扫描: {detected_text}"
                        )
                        continue

            self.portal_opening_days(static=1)

        elif area_now in ["铸造"]:
            if self.area_state == 0:
                pyautogui.click()
                self.check_pop()
                time.sleep(0.4)
                if not self.handle_forge_area():
                    return 0
                self.area_state = 1

            self.portal_opening_days(static=1)

        elif area_now in ["商店"]:
            self.press("w", 3)
            self.portal_opening_days(static=1)

        elif area_now in ["事件", "奖励", "遭遇"]:
            # 如果存在大黑塔,还是切过来,毕竟这些事件都可能入战
            if self.da_hei_ta and self.allow_e and not self.da_hei_ta_effecting:
                self.skill()
                self.da_hei_ta_effecting = True

            # 这些层都可能存在单、双或三事件，同时还可能存在宝箱、抽奖机。
            # 单事件在中间；双事件位置不变，按旧逻辑右后->左后；三事件是品字形，先前中再后右后左。
            # 基本思想是前进,监视中间区域出现汉字,确定事件数量,再按事件数推进状态。

            if self.area_state == 0:
                keyops.keyDown("w")
                tm = time.time()
                self.get_screen()
                self.get_text_position()
                total_events = None

                while time.time() - tm < 15:
                    self.get_screen()
                    if self.get_text_position():
                        keyops.keyUp("w")
                        time.sleep(0.5)
                        self.get_screen()
                        total_events = self._filter_event_positions(
                            self.get_text_position(1)
                        )
                        if len(total_events):
                            break
                        else:
                            keyops.keyDown("w")
                            time.sleep(1)
                            tm += 1.5

                keyops.keyUp("w")
                if total_events is None:
                    self.close_and_exit()
                    return 1
                log.info(f"total_events step: {total_events}")

                if not total_events or not (933 <= total_events[0][0] <= 972):
                    win32api.mouse_event(
                        win32con.MOUSEEVENTF_MOVE,
                        0,
                        int(-100 * self.multi * self.scale),
                    )
                    time.sleep(0.3)
                    self.get_screen()
                    total_events_after = self._filter_event_positions(
                        self.get_text_position(1)
                    )
                    if len(total_events_after) <= 3 and len(total_events_after) >= len(
                        total_events
                    ):
                        total_events = total_events_after
                    else:
                        win32api.mouse_event(
                            win32con.MOUSEEVENTF_MOVE,
                            0,
                            int(100 * self.multi * self.scale),
                        )

                if total_events is None:
                    self.press("d", 0.5)
                    return 1

                if not total_events:
                    total_events = [(950, 0)]
                event_count = self._set_area_event_count(total_events)

                portal = self.find_portal()
                log.info(f"portal_detail: {portal['nums']}")
                log.info(f"area_state_update: {self.area_state}")

                if portal["nums"] > 0:
                    self.area_state = max(2, event_count)
                else:
                    log.info("对齐中...")
                    self.align_event(
                        "d", event_text=self._first_area_event_x(total_events), click=1
                    )
                    self.area_state += 1 + (event_count == 1)
                    log.info(f"对齐完成, area_state: {self.area_state}")

            elif self.area_state < max(2, getattr(self, "_area_event_count", 2)):
                self._advance_to_next_area_event()

            else:
                self.portal_opening_days(static=1)

        elif area_now in ["奇遇"]:  # 奇遇-铸造
            if self.area_state == 0:
                pyautogui.click()
                self.check_pop()  #
                time.sleep(0.4)
                if not self.handle_forge_area(mirror_events=True):
                    return 0
                self.area_state = 1

            self.portal_opening_days(static=1)

        elif area_now == "休整":
            pyautogui.click()
            self.check_pop()
            time.sleep(0.3)
            keyops.keyDown("w")
            try:
                self.press("a", 0.45)
                time.sleep(1.5)
            finally:
                keyops.keyUp("w")
            time.sleep(0.25)
            self.portal_opening_days(static=1)

        # 旧版
        # elif area_now == "商店":
        #     pyautogui.click()
        #     self.check_pop()
        #     time.sleep(0.3)
        #     keyops.keyDown("w")
        #     time.sleep(1.8)
        #     keyops.keyUp("w")
        #     time.sleep(0.6)
        #     self.portal_opening_days(static=1)

        elif area_now in ["首领"]:
            if self.floor == 13 and self.area_state > 0:
                # 已经结束战斗了
                self.close_and_exit()
                self.end_of_uni()
                return 1

            if self.area_state == 0:
                self.press("w", 3)
                for c in config.skill_char:
                    if (c in self.team_member or c.isdigit()) and self.allow_e:
                        if c == "大黑塔" and self.da_hei_ta_effecting:
                            # 大黑塔秘技生效中,跳过
                            continue
                        self.press(
                            int(c) if c.isdigit() else str(self.team_member[c] + 1)
                        )
                        time.sleep(0.8)
                        self.check_dead()
                        self.skill()
                        time.sleep(1.5)

                pyautogui.click()
                time.sleep(0.2)
                pyautogui.click()
                if not self.handle_battle_area(enter_timeout=22):
                    self.close_and_exit(click=self.fail_count > 1)
                    self.fail_count += 1
                    return 1
                self.area_state += 1
            else:
                time.sleep(1)
                self.portal_opening_days(static=1)

        elif area_now in ["战斗", "精英"]:
            # 如果大黑塔秘技使能,先使用秘技,前面应该已经切换到了大黑塔
            if self.da_hei_ta and self.allow_e and not self.da_hei_ta_effecting:
                self.skill()
                self.da_hei_ta_effecting = True

            if self.area_state == 0:
                if just_switched_role:
                    # 给角色切换一个极短稳定窗口，避免紧接着冲刺导致切人丢失。
                    time.sleep(0.22)
                    self.get_screen()

                on_quan = "黄泉" in self.team_member and self.long_range == str(
                    self.team_member["黄泉"] + 1
                )
                on_bai_e = "白厄" in self.team_member and self.long_range == str(
                    self.team_member["白厄"] + 1
                )

                if self.quan and self.allow_e and on_quan:
                    for _ in range(4):
                        self.skill(1)
                    time.sleep(1.5)
                elif self.bai_e and self.allow_e and on_bai_e:
                    for _ in range(4):
                        self.skill(1)
                    time.sleep(1.5)

                if not self.handle_battle_area():
                    self.close_and_exit(click=self.fail_count > 1)
                    self.fail_count += 1
                    return 1

                self.area_state = 1

            use_battle_skill_role = self.allow_e and (
                (
                    self.quan
                    and "黄泉" in self.team_member
                    and self.long_range == str(self.team_member["黄泉"] + 1)
                )
                or (
                    self.bai_e
                    and "白厄" in self.team_member
                    and self.long_range == str(self.team_member["白厄"] + 1)
                )
            )
            if not use_battle_skill_role:
                self.press("w", 0.25)
            self.portal_opening_days(static=1)

        elif area_now in ["财富"]:
            self.forward_until(text_list=["战利品", "药箱"], timeout=8, moving=0)
            keyops.keyDown("a")
            time.sleep(0.5)
            keyops.keyUp("a")
            keyops.keyDown("w")
            time.sleep(1.3)
            keyops.keyUp("w")
            self.portal_opening_days(static=1)

        elif area_now == "位面":
            pyautogui.click()
            time.sleep(2)
            self.close_and_exit()
        else:
            self.press("F4")
        return 1

    def update_bless_prior(self):
        self.bless_prior = defaultdict(int)
        for i in list(self.team_member) + ["全局", config.team]:
            if i in self.character_prior:
                prior = self.character_prior[i]
                for j in prior:
                    self.bless_prior[j] += prior[j]

    def bless_score(self, text):
        score = 0
        for i in self.bless_prior:
            if i in text:
                score += self.bless_prior[i]
        for i in self.all_bless:
            if i[-4:] in text:
                score += int(self.all_bless[i][0]) - 1
        return score

    def drop_bless(self):
        self.bless(reverse=0)

    def bless_blood(self):
        self.bless(blood=1)

    def will_full(self):
        self.get_screen()
        if not self.click_img("new"):
            self.click((0.588, 0.5))
        time.sleep(0.2)
        # 点击后强制刷新，避免在旧帧上继续执行后续确认。
        self.get_screen()
        self.click_position([960, 975])
        time.sleep(1)

    def bless_mask(self):
        self.bless_solved = 1
        self.get_screen()
        target = cv.imread(img_path("divergent", "mask.png"))
        if target is None:
            log.warning("未找到模板图片 imgs/divergent/mask.png")
            return 0

        result = cv.matchTemplate(self.screen, target, cv.TM_CCORR_NORMED)
        ys, xs = np.where(result >= 0.95)
        if len(xs) == 0:
            return 0

        # 选择第一个匹配点（从上到下、从左到右）
        y, x = sorted(zip(ys.tolist(), xs.tolist()), key=lambda p: (p[0], p[1]))[0]
        self.click_position((x + target.shape[1] // 2, y + target.shape[0] // 2))
        self.click_position([1695, 962])
        time.sleep(0.3)
        return 1

    def choose_site_card(self):
        self.bless_solved = 1
        self.get_screen()
        target = cv.imread(img_path("divergent", "1.png"))
        if target is None:
            log.warning("未找到模板图片 imgs/divergent/1.png，直接点击确定")
            self.click_position([1629, 936])
            time.sleep(0.3)
            return 1

        result = cv.matchTemplate(self.screen, target, cv.TM_CCORR_NORMED)
        ys, xs = np.where(result >= 0.95)
        if len(xs) == 0:
            log.info("选择站点卡未匹配到 1.png，直接点击确定")
            self.click_position([1629, 936])
            time.sleep(0.3)
            return 1

        # 选择第一个匹配点（从上到下、从左到右）
        y, x = sorted(zip(ys.tolist(), xs.tolist()), key=lambda p: (p[0], p[1]))[0]
        self.click_position((x + target.shape[1] // 2, y + target.shape[0] // 2))
        self.click_position([1629, 936])
        time.sleep(0.3)
        return 1

    def bless(self, reverse=1, blood=0):
        self.bless_solved = 1
        # 屏幕下方
        # 金血祝福的位置会上下浮动, 故加大识别区域
        text = self.ts.find_with_box([350, 1550, 750, 900])
        if len(text) == 0:
            # 屏幕中间 (祝福名称)
            text = self.ts.find_with_box([350, 1550, 480, 530])
        if len(text) == 0:
            return
        self.update_bless_prior()
        blesses = []
        for i in text:
            box = i["box"]
            x, y = (box[0] + box[1]) // 2, (box[2] + box[3]) // 2
            box = [x - 220, x + 220, 450, 850]
            bless_text = self.ts.find_with_box(box)
            bless_raw_text = self.merge_text(bless_text, char=0)
            blesses.append(
                {
                    "raw_text": bless_raw_text,
                    "box": box,
                    "score": self.bless_score(bless_raw_text),
                }
            )
        blesses = sorted(blesses, key=lambda x: x["score"], reverse=reverse)
        print(blesses)
        box = blesses[0]["box"]
        # "new" 在不同亮度/动画帧下会出现轻微抖动，先多次尝试再回退。
        clicked_new = False
        for threshold in (0.95, 0.93, 0.91):
            if self.click_img("new", threshold=threshold):
                clicked_new = True
                break
            self.get_screen()
        if not clicked_new and not self.click_img(
            "divergent/suggested", threshold=0.93
        ):
            self.click_position([(box[0] + box[1]) // 2, 500])
        # 选卡后强制刷新，保证确认按钮点击时机基于最新界面。
        self.get_screen()
        if blood:
            self.click_position([960, 975])
        else:
            self.click_position([1695, 962])
        time.sleep(1)

    def end_of_uni(self):
        self.update_count(0)
        self.my_cnt += 1
        tm = int((time.time() - self.init_tm) / 60)
        remain_round = self.nums - self.my_cnt
        if remain_round > 0:
            remain = int(remain_round * (time.time() - self.init_tm) / self.my_cnt / 60)
        else:
            remain = 0
            remain_round = -1
        notif(
            "已完成",
            f"计数:{self.count} 剩余:{remain_round} 已使用：{tm // 60}小时{tm % 60}分钟  平均{tm // self.my_cnt}分钟一次  预计剩余{remain // 60}小时{remain % 60}分钟",
            cnt=str(self.count),
        )
        if self.nums <= self.my_cnt and self.nums >= 0:
            log.info("已完成上限，准备停止运行")
            self.end = 1
        self.floor = 0
        self.init_floor()

    def update_count(self, read=True):
        file_name = logs_path("notif.txt")
        if read:
            new_cnt = 0
            if os.path.exists(file_name):
                time_cnt = os.path.getmtime(file_name)
                with open(file_name, "r", encoding="utf-8", errors="ignore") as fh:
                    s = fh.readlines()
                    try:
                        new_cnt = int(s[0].strip("\n"))
                        time_cnt = float(s[3].strip("\n"))
                    except:
                        pass
            else:
                os.makedirs(logs_path(), exist_ok=True)
                with open(file_name, "w", encoding="utf-8") as file:
                    file.write("0")
                    file.close()
                time_cnt = os.path.getmtime(file_name)
        else:
            new_cnt = self.count + 1
            time_cnt = self.count_tm
        dt = datetime.datetime.now().astimezone()
        tz_info = None
        try:
            tz_dict = {
                "Default": None,
                "America": pytz.timezone("US/Central"),
                "Asia": pytz.timezone("Asia/Shanghai"),
                "Europe": pytz.timezone("Europe/London"),
            }
            tz_info = tz_dict[config.timezone]
        except:
            pass

        # 按配置时区计算周计数重置时间
        dt = dt.astimezone(tz_info)
        current_weekday = dt.weekday()
        monday = dt + datetime.timedelta(days=-current_weekday)
        target_datetime = datetime.datetime(
            monday.year, monday.month, monday.day, 4, 0, 0, tzinfo=tz_info
        )
        monday_ts = target_datetime.timestamp()
        if dt.timestamp() >= monday_ts and time_cnt < monday_ts:
            self.count = int(not read)
        else:
            self.count = new_cnt
        self.count_tm = time.time()

    def stop(self, *_, **__):
        stop_lock = getattr(self, "_stop_lock", None)
        if stop_lock is None:
            if self._stop:
                log.info("停止请求已在处理中，跳过重复停止")
                return
            self._stop = True
        else:
            with stop_lock:
                if self._stop:
                    log.info("停止请求已在处理中，跳过重复停止")
                    return
                self._stop = True
        log.info("尝试停止运行")
        try:
            self.portal_cnt = 0
            self.area_state = 0
            self.event_solved = 0
            self.bless_solved = 0
            self.fail_cnt = 0
            self.now_event = ""
            self._event_followup = ""
            if hasattr(self, "keys"):
                self.keys.fff = 0
                self.keys.events.clear()
            self._release_control_keys(label="stop")
        except:
            pass

    def on_key_press(self, event):
        if event.name == "f8":
            print("F8 已被按下，尝试停止运行")
            self.stop()

    def start(self):
        with self._stop_lock:
            self._stop = False
        self._enable_view_movement("DivergentUniverse.start")
        log.info(describe_runtime_context("DivergentUniverse.start"))
        keyboard.on_press(self.on_key_press)
        self.keys = KeyController(self)
        try:
            self.route()
        except KeyboardInterrupt:
            print("KeyboardInterrupt")
            try:
                log.info("用户终止进程")
            except:
                pass
            if not self._stop:
                self.stop()
        except Exception as e:
            # 运行中触发 stop() 后，底层按键函数会抛出 "正在退出"，属于正常退出流程。
            if self._stop and isinstance(e, ValueError) and str(e) == "正在退出":
                log.info("停止运行完成")
                return
            print_exc()
            traceback.print_exc()
            log.info(str(e))
            log.info("发生错误，尝试停止运行")
            self.stop()

    def start_door_test(self):
        with self._stop_lock:
            self._stop = False
        self._enable_view_movement("DivergentUniverse.start_door_test")
        keyboard.on_press(self.on_key_press)
        self.keys = KeyController(self)
        try:
            self.route_door_test()
        except KeyboardInterrupt:
            print("KeyboardInterrupt")
            try:
                log.info("用户终止对门测试")
            except:
                pass
            if not self._stop:
                self.stop()
        except Exception as e:
            if self._stop and isinstance(e, ValueError) and str(e) == "正在退出":
                log.info("对门测试停止完成")
                return
            print_exc()
            traceback.print_exc()
            log.info(str(e))
            log.info("对门测试发生错误，尝试停止运行")
            self.stop()

    def screen_test(self):
        cv.imshow("screen", self.get_screen())
        cv.waitKey(0)


def main():
    log.info(f"debug: {args.debug}")
    su = DivergentUniverse(args.debug, args.nums, args.speed)
    try:
        su.start()
    except Exception:
        print_exc()
    finally:
        su.stop()


def run():
    if not pyuac.isUserAdmin():
        pyuac.runAsAdmin()
    else:
        main()


def main_door_test():
    log.info(f"debug(door test): {args.debug}")
    su = DivergentUniverse(args.debug, args.nums, args.speed)
    try:
        su.start_door_test()
    except Exception:
        print_exc()
    finally:
        su.stop()


def run_door_test():
    if not pyuac.isUserAdmin():
        pyuac.runAsAdmin()
    else:
        main_door_test()


if __name__ == "__main__":
    run()
