import json
import os
import sys
from typing import Any, Dict, List

import yaml

from asu.core.diver.constants import (
    ALL_CHARACTER_LIST,
    DEFAULT_PORTAL_PRIOR,
    LONG_RANGE_LIST,
    RAW_ANGLES,
)


class Config:
    def __init__(self):
        self.abspath = os.path.dirname(
            os.path.dirname(os.path.dirname(__file__))
        )  # 获取项目根目录
        if getattr(sys, "frozen", False):
            self.abspath = "."
        self.angle = "1.0"
        self.difficult = "5"
        self.allow_difficult = [1, 2, 3, 4, 5]
        self.text = "info.yml"
        self.skill_char = ["符玄", "阮梅", "黄泉", "白厄"]
        self.long_range_list = list(LONG_RANGE_LIST)
        self.all_list = list(ALL_CHARACTER_LIST)
        self.angles = list(reversed(RAW_ANGLES))
        self.long_press_sprint = 0
        self.debug_mode = 0
        self.speed_mode = 0
        self.weekly_mode = 0
        self.cpu_mode = 0
        self.save_cnt = 4
        self.accuracy = 1440
        self.enable_portal_prior = 0
        self.portal_prior = dict(DEFAULT_PORTAL_PRIOR)
        self.team = "终结技"
        self.timezones = ["America", "Asia", "Europe", "Default"]
        self.timezone = "Default"
        self.origin_key = ["f", "m", "shift", "v", "e", "w", "a", "s", "d", "1", "2", "3", "4"]
        self.mapping = list(self.origin_key)
        self.max_run = 34
        self.match = self._load_json(self._project_path("actions", "character.json"))
        self.read()

    def _project_path(self, *parts: str) -> str:
        return os.path.join(self.abspath, *parts)

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _load_yaml(path: str) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                data = yaml.safe_load(f)
        except (OSError, yaml.YAMLError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _load_json(path: str) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    @property
    def multi(self) -> float:
        angle_value = self._safe_float(self.angle, 1.0)
        if angle_value > 5:
            self.angle = "1.0"
            return 1.0
        if angle_value > 2:
            return angle_value - 2
        return angle_value

    @property
    def diffi(self) -> int:
        difficulty = self._safe_int(self.difficult, 5)
        return difficulty if difficulty in self.allow_difficult else 5

    def clean_text(self, text: str, char: int = 1) -> str:
        symbols = r"[!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~—“”‘’«»„…·¿¡£¥€©®™°±÷×¶§‰]，。！？；：（）【】「」《》、￥"
        if char:
            symbols += r"0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        translator = str.maketrans("", "", symbols)
        return text.translate(translator)

    def update_skill(self, skill: List[str]):
        self.skill_char = []
        for char_name in skill:
            cleaned_name = self.clean_text(str(char_name), 0)
            if cleaned_name in self.match:
                cleaned_name = str(self.match[cleaned_name])
            if cleaned_name in self.all_list or cleaned_name in ["1", "2", "3", "4"]:
                self.skill_char.append(cleaned_name)
        print(f"秘技列表:{self.skill_char}")

    def read(self):
        config_path = self._project_path(self.text)
        if not os.path.exists(config_path):
            self.save()
            return

        yaml_data = self._load_yaml(config_path)
        config_data = yaml_data.get("config")
        if isinstance(config_data, dict):
            self.angle = str(config_data.get("angle", self.angle))
            self.difficult = str(config_data.get("difficulty", self.difficult))
            self.team = str(config_data.get("team", self.team))
            self.speed_mode = self._safe_int(config_data.get("speed_mode"), self.speed_mode)
            self.weekly_mode = self._safe_int(config_data.get("weekly_mode"), self.weekly_mode)
            self.cpu_mode = self._safe_int(config_data.get("cpu_mode"), self.cpu_mode)
            self.timezone = str(config_data.get("timezone", self.timezone))
            self.max_run = self._safe_int(config_data.get("max_run"), self.max_run)
            self.save_cnt = self._safe_int(config_data.get("save"), self.save_cnt)
            self.accuracy = self._safe_int(config_data.get("accuracy"), self.accuracy)
            self.enable_portal_prior = self._safe_int(
                config_data.get("enable_portal_prior"), self.enable_portal_prior
            )

            skill_data = config_data.get("skill")
            if isinstance(skill_data, list):
                self.update_skill([str(item) for item in skill_data])

            portal_prior = config_data.get("portal_prior")
            if isinstance(portal_prior, dict) and portal_prior:
                self.portal_prior = portal_prior

        mapping_data = yaml_data.get("key_mapping")
        if isinstance(mapping_data, list) and mapping_data:
            self.mapping = [str(item) for item in mapping_data]

    def save(self):
        config_path = self._project_path(self.text)
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                {
                    "config": {
                        "angle": self._safe_float(self.angle, 1.0),
                        "difficulty": self.diffi,
                        "team": self.team,
                        "speed_mode": self.speed_mode,
                        "weekly_mode": self.weekly_mode,
                        "cpu_mode": self.cpu_mode,
                        "skill": self.skill_char,
                        "save": self.save_cnt,
                        "timezone": self.timezone,
                        "max_run": self.max_run,
                        "accuracy": self.accuracy,
                        "enable_portal_prior": self.enable_portal_prior,
                        "portal_prior": self.portal_prior,
                    },
                    "key_mapping": self.mapping,
                },
                f,
                allow_unicode=True,
                sort_keys=False,
            )


config = Config()



