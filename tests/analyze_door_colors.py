"""分析门的颜色成分分布，调试 HSV 阈值"""

from pathlib import Path

import cv2 as cv
import numpy as np

SCALES = [0.85, 1.0, 1.15]
ROI_X1, ROI_X2 = 900, 1030
ROI_Y1, ROI_Y2 = 115, 920


def main():
    repo_root = Path(__file__).resolve().parents[1]
    image_path = repo_root / "tests" / "door_test.png"
    tpl_dir = repo_root / "imgs" / "divergent"

    image = cv.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Cannot read test image: {image_path}")

    h, w = image.shape[:2]
    x1 = max(0, min(w, ROI_X1))
    x2 = max(0, min(w, ROI_X2))
    y1 = max(0, min(h, ROI_Y1))
    y2 = max(0, min(h, ROI_Y2))

    roi_bgr = image[y1:y2, x1:x2]
    roi_hsv = cv.cvtColor(roi_bgr, cv.COLOR_BGR2HSV)

    # 分析模板 4 的颜色
    tpl_path = tpl_dir / "door4.png"
    tpl = cv.imread(str(tpl_path))
    tpl_hsv = cv.cvtColor(tpl, cv.COLOR_BGR2HSV)

    print("=== 模板 door4 颜色分析 ===")
    print(f"模板形状: {tpl_hsv.shape}")

    # 按象限分析
    h_tpl, w_tpl = tpl_hsv.shape[:2]
    regions = {
        "中心": tpl_hsv[
            int(h_tpl * 0.3) : int(h_tpl * 0.7), int(w_tpl * 0.3) : int(w_tpl * 0.7)
        ],
        "左侧": tpl_hsv[:, : int(w_tpl * 0.3)],
        "右侧": tpl_hsv[:, int(w_tpl * 0.7) :],
        "顶部": tpl_hsv[: int(h_tpl * 0.3), :],
        "底部": tpl_hsv[int(h_tpl * 0.7) :, :],
    }

    for region_name, region in regions.items():
        if region.size == 0:
            continue
        h_vals = region[:, :, 0]
        s_vals = region[:, :, 1]
        v_vals = region[:, :, 2]
        print(f"\n{region_name}:")
        print(f"  H 范围: {h_vals.min()}-{h_vals.max()} (平均: {h_vals.mean():.1f})")
        print(f"  S 范围: {s_vals.min()}-{s_vals.max()} (平均: {s_vals.mean():.1f})")
        print(f"  V 范围: {v_vals.min()}-{v_vals.max()} (平均: {v_vals.mean():.1f})")

    # 尝试不同的掩码
    print("\n=== 模板中心玻璃部分的掩码效果 ===")
    center = tpl_hsv[
        int(h_tpl * 0.3) : int(h_tpl * 0.7), int(w_tpl * 0.3) : int(w_tpl * 0.7)
    ]

    test_masks = [
        ("低sat灰", [0, 0, 60], [180, 50, 230]),
        ("低sat灰V宽", [0, 0, 50], [180, 50, 255]),
        ("低sat高V白", [0, 0, 200], [180, 50, 255]),
        ("H+低s灰", [0, 0, 70], [180, 60, 220]),
    ]

    for mask_name, lower, upper in test_masks:
        mask = cv.inRange(center, np.array(lower), np.array(upper))
        ratio = mask.sum() / (mask.shape[0] * mask.shape[1] * 255)
        print(f"{mask_name}: {ratio * 100:.1f}% 像素匹配")


if __name__ == "__main__":
    main()
