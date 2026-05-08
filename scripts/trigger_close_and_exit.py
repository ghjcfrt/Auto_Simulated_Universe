"""手动触发 DivergentUniverse.close_and_exit 的实机测试脚本。"""

import argparse
import sys
import time
from pathlib import Path

import pyuac

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--click",
        action="store_true",
        help="执行 close_and_exit 的点击暂离流程；默认只触发 ESC。",
    )
    parser.add_argument(
        "--countdown",
        type=int,
        default=5,
        help="调用 close_and_exit 前等待的秒数，默认 5 秒。",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="以 debug=1 初始化 DivergentUniverse。",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if not pyuac.isUserAdmin():
        print("此脚本需要管理员权限运行，正在请求管理员权限...")
        pyuac.runAsAdmin()
        return

    from asu.workflows.diver import DivergentUniverse

    print("初始化 DivergentUniverse；如果窗口未切到游戏，程序会等待游戏窗口。")
    diver = DivergentUniverse(debug=int(args.debug), nums=-1, speed=0)
    diver._stop = False

    click_text = "会点击暂离按钮" if args.click else "不会点击暂离按钮"
    print(f"将在 {args.countdown} 秒后调用 close_and_exit(click={args.click})，{click_text}。")
    print("请保持游戏窗口可见，必要时手动切回游戏窗口。")
    for remaining in range(max(0, args.countdown), 0, -1):
        print(f"{remaining}...")
        time.sleep(1)

    try:
        print("开始调用 close_and_exit...")
        diver.close_and_exit(click=args.click)
        print("close_and_exit 调用完成。")
    finally:
        diver.stop()


if __name__ == "__main__":
    main()
