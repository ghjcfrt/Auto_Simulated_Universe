"""兼容入口：差分宇宙对门测试模式。"""

from asu.apps.diver_door_test import (
    DivergentUniverse,
    main_door_test,
    run_door_test,
    version,
)

__all__ = ["DivergentUniverse", "version", "main_door_test", "run_door_test"]


if __name__ == "__main__":
    run_door_test()
