"""兼容入口：视角校准。"""

from asu.apps.align_angle import get_angle, main, run

__all__ = ["get_angle", "main", "run"]


if __name__ == "__main__":
    run()
