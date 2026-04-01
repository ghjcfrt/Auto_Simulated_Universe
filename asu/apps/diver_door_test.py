"""兼容入口：差分宇宙对门测试模式。"""

from asu.workflows.diver import (
    DivergentUniverse,
    main_door_test,
    run_door_test,
    version,
)

__all__ = ["DivergentUniverse", "version", "main_door_test", "run_door_test"]


if __name__ == "__main__":
    run_door_test()
