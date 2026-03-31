"""兼容入口：差分宇宙模式。"""

from asu.apps.diver import DivergentUniverse, main, run, version

__all__ = ["DivergentUniverse", "version", "main", "run"]


if __name__ == "__main__":
    run()
