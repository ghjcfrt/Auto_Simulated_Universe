"""兼容入口：图形界面。"""

from asu.apps.gui import clean_temp_files, cleanup, main, run

__all__ = ["main", "run", "cleanup", "clean_temp_files"]


if __name__ == "__main__":
    run()
