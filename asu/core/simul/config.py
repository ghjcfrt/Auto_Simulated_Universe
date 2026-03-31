import copy
import os
import sys
from typing import Any, Dict, List

import yaml

from asu.core.simul.constants import DEFAULT_PRIOR, DEFAULT_SECONDARY_FATE


class Config:
    def __init__(self):
        self.abspath = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  # 获取项目根目录
        if getattr(sys, "frozen", False):
            self.abspath = "."
        self.order_text = "1 2 3 4"
        self.angle = "1.0"
        self.difficult = "5"
        self.allow_difficult = [1, 2, 3, 4, 5]
        self.text = "info_old.yml"
        self.fate = "巡猎"
        self.map_sha = ""
        self.fates = ["存护", "记忆", "虚无", "丰饶", "巡猎", "毁灭", "欢愉", "繁育", "智识"]
        self.show_map_mode = 0
        self.debug_mode = 0
        self.speed_mode = 0
        self.long_press_sprint = 0
        self.use_consumable = 0
        self.slow_mode = 0
        self.force_update = 0
        self.unlock = 0
        self.bonus = 0
        self.timezones = ["America", "Asia", "Europe", "Default"]
        self.timezone = "Default"
        self.origin_key = ["f", "m", "shift", "v", "e", "w", "a", "s", "d", "1", "2", "3", "4"]
        self.mapping = list(self.origin_key)
        self.max_run = 34
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

    def _load_secondary_fate(self) -> List[str]:
        for filename in [self.text, "info_example_old.yml"]:
            yaml_data = self._load_yaml(self._project_path(filename))
            config = yaml_data.get("config")
            if isinstance(config, dict):
                secondary_fate = config.get("secondary_fate")
                if isinstance(secondary_fate, list) and secondary_fate:
                    return [str(item) for item in secondary_fate]
        return list(DEFAULT_SECONDARY_FATE)

    def _load_prior(self) -> Dict[str, Any]:
        for filename in [self.text, "info_example_old.yml"]:
            yaml_data = self._load_yaml(self._project_path(filename))
            prior = yaml_data.get("prior")
            if isinstance(prior, dict) and prior:
                return copy.deepcopy(prior)
        return copy.deepcopy(DEFAULT_PRIOR)

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
    def order(self) -> List[int]:
        order_numbers: List[int] = []
        for token in self.order_text.strip().split():
            try:
                order_numbers.append(int(token))
            except ValueError:
                continue
        return order_numbers or [1, 2, 3, 4]

    @property
    def diffi(self) -> int:
        difficulty = self._safe_int(self.difficult, 1)
        return difficulty if difficulty in self.allow_difficult else 1

    def read(self):
        config_path = self._project_path(self.text)
        if not os.path.exists(config_path):
            self.save()
            return

        yaml_data = self._load_yaml(config_path)
        config = yaml_data.get("config")
        if isinstance(config, dict):
            order_text = config.get("order_text")
            if isinstance(order_text, list):
                self.order_text = " ".join(str(x) for x in order_text)
            elif isinstance(order_text, str):
                self.order_text = order_text

            self.angle = str(config.get("angle", self.angle))
            self.difficult = str(config.get("difficulty", self.difficult))
            self.fate = str(config.get("fate", self.fate))
            self.map_sha = str(config.get("map_sha", self.map_sha))
            self.show_map_mode = self._safe_int(config.get("show_map_mode"), self.show_map_mode)
            self.debug_mode = self._safe_int(config.get("debug_mode"), self.debug_mode)
            self.speed_mode = self._safe_int(config.get("speed_mode"), self.speed_mode)
            self.bonus = self._safe_int(config.get("bonus"), self.bonus)
            self.long_press_sprint = self._safe_int(
                config.get("long_press_sprint"), self.long_press_sprint
            )
            self.use_consumable = self._safe_int(config.get("use_consumable"), self.use_consumable)
            self.force_update = self._safe_int(config.get("force_update"), self.force_update)
            self.timezone = str(config.get("timezone", self.timezone))
            self.slow_mode = self._safe_int(config.get("slow_mode"), self.slow_mode)
            self.max_run = self._safe_int(config.get("max_run"), self.max_run)

        mapping = yaml_data.get("key_mapping")
        if isinstance(mapping, list) and mapping:
            self.mapping = [str(item) for item in mapping]

    def save(self):
        config_path = self._project_path(self.text)
        secondary_fate = self._load_secondary_fate()
        prior = self._load_prior()
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                {
                    "config": {
                        "order_text": [int(x) for x in self.order_text.split(" ") if x.strip().isdigit()],
                        "angle": self._safe_float(self.angle, 1.0),
                        "difficulty": self.diffi,
                        "fate": self.fate,
                        "secondary_fate": secondary_fate,
                        "map_sha": self.map_sha,
                        "show_map_mode": self.show_map_mode,
                        "debug_mode": self.debug_mode,
                        "speed_mode": self.speed_mode,
                        "bonus": self.bonus,
                        "long_press_sprint": self.long_press_sprint,
                        "use_consumable": self.use_consumable,
                        "slow_mode": self.slow_mode,
                        "force_update": self.force_update,
                        "timezone": self.timezone,
                        "max_run": self.max_run,
                    },
                    "prior": prior,
                    "key_mapping": self.mapping,
                },
                f,
                allow_unicode=True,
                sort_keys=False,
            )


config = Config()



