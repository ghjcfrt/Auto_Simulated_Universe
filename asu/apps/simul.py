"""兼容入口：模拟宇宙模式。"""

from asu.workflows.simul import SimulatedUniverse, main, run, version

__all__ = ["SimulatedUniverse", "version", "main", "run"]


if __name__ == "__main__":
    run()
