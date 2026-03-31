"""兼容入口：桌面通知。"""

from asu.apps.notif import clear, exit_program, main, maopao, notif, notify

__all__ = ["main", "notif", "notify", "maopao", "clear", "exit_program"]


if __name__ == "__main__":
    main()
