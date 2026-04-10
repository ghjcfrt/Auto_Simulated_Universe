import argparse

from asu.core.diver.config import config


def str2bool(v):
    if isinstance(v, bool):
        return v
    return v.lower() in ("true", "t", "1")


def infer_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", default=False)
    parser.add_argument("--nums", type=int, default=config.max_run)
    parser.add_argument("--speed", action="store_true", default=False)
    parser.add_argument("--cpu", action="store_true", default=False)
    return parser


def get_args():
    return infer_args().parse_known_args()[0]


def parse_args():
    # 兼容旧用法
    return infer_args().parse_known_args()[0]


if __name__ == "__main__":
    args = get_args()
