import json
from datetime import datetime
from pathlib import Path

import cv2 as cv
import numpy as np

SCALES = [0.85, 1.0, 1.15]
ROI_X1, ROI_X2 = 900, 1030
ROI_Y1, ROI_Y2 = 115, 920


def make_door_color_masks(hsv_img):
    """提取玻璃深蓝灰和外框粉黄色彩掩码"""
    pink = cv.inRange(hsv_img, np.array([140, 55, 70]), np.array([175, 255, 255]))
    yellow = cv.inRange(hsv_img, np.array([18, 65, 85]), np.array([42, 255, 255]))
    # 玻璃主体：深蓝灰 #57597e -> HSV(118, 79, 126) H~113-123, S~49-109, V~96-156
    glass_cyan_green = cv.inRange(
        hsv_img, np.array([113, 49, 96]), np.array([123, 109, 156])
    )
    # 玻璃高光：高亮区域 V>180, S<60
    glass_highlight = cv.inRange(
        hsv_img, np.array([0, 0, 180]), np.array([180, 60, 255])
    )
    return pink, yellow, glass_cyan_green, glass_highlight


def match_single(
    roi_bgr,
    tpl_bgr,
    tpl_id,
    scale,
):
    """使用TM_CCORR_NORMED在BGR颜色图上匹配，关注模板颜色"""
    roi_h, roi_w = roi_bgr.shape[:2]
    th, tw = tpl_bgr.shape[:2]
    rw, rh = max(1, int(tw * scale)), max(1, int(th * scale))
    if rw >= roi_w or rh >= roi_h:
        return None

    # 缩放模板
    scaled_tpl = cv.resize(tpl_bgr, (rw, rh), interpolation=cv.INTER_LINEAR)

    # 使用TM_CCORR_NORMED进行颜色匹配
    score_map = cv.matchTemplate(roi_bgr, scaled_tpl, cv.TM_CCORR_NORMED)

    _, conf, _, max_loc = cv.minMaxLoc(score_map)
    center_x = max_loc[0] + rw / 2
    center_y = max_loc[1] + rh / 2
    return {
        "tpl_id": tpl_id,
        "scale": scale,
        "conf": float(conf),
        "center_x": float(center_x),
        "center_y": float(center_y),
        "width": int(rw),
        "height": int(rh),
        "x": int(max_loc[0]),
        "y": int(max_loc[1]),
    }


def adjusted_score(item):
    return item["conf"] - 0.015 * (item["tpl_id"] - 1)


def match_all_door_rough(
    roi_edge,
    tpl_edge,
    roi_w,
    roi_h,
    roi_gray=None,
    roi_pink=None,
    roi_yellow=None,
    roi_glass_gray=None,
    roi_glass_white=None,
    tpl_gray=None,
    tpl_pink=None,
    tpl_yellow=None,
    tpl_glass_gray=None,
    tpl_glass_white=None,
    top_k_candidates=8,
):
    """用 all_door.png 做大方向匹配，考虑颜色信息，返回最佳匹配信息"""

    def build_map_score_detail(score_map, best_loc):
        if score_map is None:
            return None
        _, peak_val, _, peak_loc = cv.minMaxLoc(score_map)
        bx, by = int(best_loc[0]), int(best_loc[1])
        return {
            "at_match": float(score_map[by, bx]),
            "peak": float(peak_val),
            "peak_x": int(peak_loc[0]),
            "peak_y": int(peak_loc[1]),
        }

    def build_map_score_value(score_map, loc):
        if score_map is None:
            return None
        lx, ly = int(loc[0]), int(loc[1])
        return float(score_map[ly, lx])

    def collect_top_locations(score_map, top_k):
        flat = score_map.reshape(-1)
        if flat.size == 0 or top_k <= 0:
            return []
        use_k = min(top_k, flat.size)
        top_indices = np.argpartition(flat, -use_k)[-use_k:]
        sorted_indices = top_indices[np.argsort(flat[top_indices])[::-1]]
        locations = []
        map_w = score_map.shape[1]
        for idx in sorted_indices:
            y, x = divmod(int(idx), map_w)
            locations.append((x, y))
        return locations

    def enhance_mask_connectivity(mask_bin):
        """增强掩码连通性：闭开运算 + 过滤小连通域。"""
        mask_u8 = (mask_bin > 0).astype(np.uint8)

        # 先连通临近区域，再去掉孤立噪点
        kernel = np.ones((3, 3), dtype=np.uint8)
        mask_u8 = cv.morphologyEx(mask_u8, cv.MORPH_CLOSE, kernel, iterations=1)
        mask_u8 = cv.morphologyEx(mask_u8, cv.MORPH_OPEN, kernel, iterations=1)

        num_labels, labels, stats, _ = cv.connectedComponentsWithStats(
            mask_u8, connectivity=8
        )
        if num_labels <= 1:
            return mask_u8.astype(np.float32)

        fg_area = int(mask_u8.sum())
        min_area = max(6, int(fg_area * 0.005))
        kept = np.zeros_like(mask_u8, dtype=np.uint8)
        for comp_id in range(1, num_labels):
            area = int(stats[comp_id, cv.CC_STAT_AREA])
            if area >= min_area:
                kept[labels == comp_id] = 1

        if int(kept.sum()) == 0:
            largest_idx = 1 + int(np.argmax(stats[1:, cv.CC_STAT_AREA]))
            kept[labels == largest_idx] = 1

        return kept.astype(np.float32)

    def normalized_mask_overlap_map(roi_mask, tpl_mask):
        """面积归一化匹配：sum(roi&tpl) / sum(tpl_area)"""
        roi_bin = enhance_mask_connectivity(roi_mask)
        tpl_bin = enhance_mask_connectivity(tpl_mask)
        tpl_area = float(tpl_bin.sum())
        if tpl_area <= 1e-6:
            out_h = roi_bin.shape[0] - tpl_bin.shape[0] + 1
            out_w = roi_bin.shape[1] - tpl_bin.shape[1] + 1
            return np.zeros((max(1, out_h), max(1, out_w)), dtype=np.float32)
        overlap_map = cv.matchTemplate(roi_bin, tpl_bin, cv.TM_CCORR)
        return overlap_map / tpl_area

    th, tw = tpl_edge.shape[:2]
    best = None
    top_candidates = []

    scales = [0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3]
    for scale in scales:
        rw, rh = max(1, int(tw * scale)), max(1, int(th * scale))
        if rw >= roi_w or rh >= roi_h:
            continue

        scaled_edge = cv.resize(tpl_edge, (rw, rh), interpolation=cv.INTER_LINEAR)
        edge_map = cv.matchTemplate(roi_edge, scaled_edge, cv.TM_CCORR_NORMED)
        gray_map = None
        pink_map = None
        yellow_map = None
        glass_gray_map = None
        glass_white_map = None
        frame_color_map = None
        glass_color_map = None

        # 组合多种评分，加入颜色信息
        score_map = edge_map.copy()
        weights = {"edge": 1.0}
        if roi_gray is not None and tpl_gray is not None:
            scaled_gray = cv.resize(tpl_gray, (rw, rh), interpolation=cv.INTER_LINEAR)
            gray_map = cv.matchTemplate(roi_gray, scaled_gray, cv.TM_CCORR_NORMED)
            score_map = 0.70 * edge_map + 0.30 * gray_map
            weights = {"edge": 0.70, "gray": 0.30}

        # 如果有颜色掩码，进一步合并颜色评分
        if (
            roi_pink is not None
            and tpl_pink is not None
            and roi_yellow is not None
            and tpl_yellow is not None
            and roi_glass_gray is not None
            and tpl_glass_gray is not None
            and roi_glass_white is not None
            and tpl_glass_white is not None
        ):
            scaled_pink = cv.resize(tpl_pink, (rw, rh), interpolation=cv.INTER_NEAREST)
            scaled_yellow = cv.resize(
                tpl_yellow, (rw, rh), interpolation=cv.INTER_NEAREST
            )
            scaled_glass_gray = cv.resize(
                tpl_glass_gray, (rw, rh), interpolation=cv.INTER_NEAREST
            )
            scaled_glass_white = cv.resize(
                tpl_glass_white, (rw, rh), interpolation=cv.INTER_NEAREST
            )

            pink_map = normalized_mask_overlap_map(roi_pink, scaled_pink)
            yellow_map = normalized_mask_overlap_map(roi_yellow, scaled_yellow)
            glass_gray_map = cv.matchTemplate(
                roi_glass_gray, scaled_glass_gray, cv.TM_CCORR_NORMED
            )
            glass_white_map = cv.matchTemplate(
                roi_glass_white, scaled_glass_white, cv.TM_CCORR_NORMED
            )

            frame_color_map = 0.70 * pink_map + 0.30 * yellow_map
            glass_color_map = 0.62 * glass_gray_map + 0.38 * glass_white_map

            score_map = 0.70 * frame_color_map + 0.30 * edge_map
            weights = {
                "frame_color": 0.70,
                "edge": 0.30,
                "gray": 0.00,
                "glass_color": 0.00,
            }

        _, conf, _, max_loc = cv.minMaxLoc(score_map)
        center_x = max_loc[0] + rw / 2
        center_y = max_loc[1] + rh / 2

        score_breakdown = {
            "weights": weights,
            "combined": build_map_score_detail(score_map, max_loc),
            "edge": build_map_score_detail(edge_map, max_loc),
            "gray": build_map_score_detail(gray_map, max_loc),
            "frame_color": build_map_score_detail(frame_color_map, max_loc),
            "glass_color": build_map_score_detail(glass_color_map, max_loc),
            "pink": build_map_score_detail(pink_map, max_loc),
            "yellow": build_map_score_detail(yellow_map, max_loc),
            "glass_gray": build_map_score_detail(glass_gray_map, max_loc),
            "glass_white": build_map_score_detail(glass_white_map, max_loc),
        }

        for loc_x, loc_y in collect_top_locations(score_map, top_k_candidates):
            top_candidates.append(
                {
                    "scale": scale,
                    "conf": float(score_map[loc_y, loc_x]),
                    "center_x": float(loc_x + rw / 2),
                    "center_y": float(loc_y + rh / 2),
                    "width": int(rw),
                    "height": int(rh),
                    "x": int(loc_x),
                    "y": int(loc_y),
                    "score_breakdown": {
                        "weights": weights,
                        "combined": build_map_score_value(score_map, (loc_x, loc_y)),
                        "edge": build_map_score_value(edge_map, (loc_x, loc_y)),
                        "gray": build_map_score_value(gray_map, (loc_x, loc_y)),
                        "frame_color": build_map_score_value(
                            frame_color_map, (loc_x, loc_y)
                        ),
                        "glass_color": build_map_score_value(
                            glass_color_map, (loc_x, loc_y)
                        ),
                        "pink": build_map_score_value(pink_map, (loc_x, loc_y)),
                        "yellow": build_map_score_value(yellow_map, (loc_x, loc_y)),
                        "glass_gray": build_map_score_value(
                            glass_gray_map, (loc_x, loc_y)
                        ),
                        "glass_white": build_map_score_value(
                            glass_white_map, (loc_x, loc_y)
                        ),
                    },
                }
            )

        item = {
            "scale": scale,
            "conf": float(conf),
            "center_x": float(center_x),
            "center_y": float(center_y),
            "width": int(rw),
            "height": int(rh),
            "x": int(max_loc[0]),
            "y": int(max_loc[1]),
            "score_breakdown": score_breakdown,
        }

        if best is None or conf > best["conf"]:
            best = item

    if best is not None:
        top_candidates.sort(key=lambda x: x["conf"], reverse=True)
        best["top_candidates"] = top_candidates[:top_k_candidates]

    return best


def test_single_door(image_path, output_dir, tpl_dir):
    """单张图像测试，输出结果到指定文件夹"""

    image = cv.imread(str(image_path))
    if image is None:
        return {"status": "failed", "reason": f"Cannot read test image: {image_path}"}

    h, w = image.shape[:2]
    # 使用全图进行匹配
    x1, y1, x2, y2 = 0, 0, w, h
    roi_bgr = image[y1:y2, x1:x2]

    # [第1步] 优先使用 all_door.png 及其变体做大方向匹配（仅大方向，使用边缘+颜色）
    # 为 all_door 计算所需的图像派生
    roi_w, roi_h = roi_bgr.shape[1], roi_bgr.shape[0]
    roi_edge = cv.Canny(roi_bgr, 50, 150)
    roi_gray = cv.cvtColor(roi_bgr, cv.COLOR_BGR2GRAY)
    roi_hsv = cv.cvtColor(roi_bgr, cv.COLOR_BGR2HSV)
    roi_pink, roi_yellow, roi_glass_gray, roi_glass_white = make_door_color_masks(
        roi_hsv
    )
    all_door_variants = [
        "all_door.png",
        "all_door_3_4.png",
        "all_door_2_4.png",
        "all_door_1_4.png",
    ]
    all_door_matches = {}  # 存储所有变体的匹配结果
    all_door_match = None  # 最佳匹配

    for variant_name in all_door_variants:
        variant_path = tpl_dir / variant_name
        if variant_path.exists():
            variant_tpl = cv.imread(str(variant_path))
            variant_edge = cv.Canny(variant_tpl, 50, 150)
            variant_gray = cv.cvtColor(variant_tpl, cv.COLOR_BGR2GRAY)
            variant_hsv = cv.cvtColor(variant_tpl, cv.COLOR_BGR2HSV)
            variant_pink, variant_yellow, variant_glass_gray, variant_glass_white = (
                make_door_color_masks(variant_hsv)
            )

            variant_match = match_all_door_rough(
                roi_edge,
                variant_edge,
                roi_w,
                roi_h,
                roi_gray,
                roi_pink,
                roi_yellow,
                roi_glass_gray,
                roi_glass_white,
                variant_gray,
                variant_pink,
                variant_yellow,
                variant_glass_gray,
                variant_glass_white,
            )
            if variant_match:
                all_door_matches[variant_name] = variant_match
                # 保留置信度最高的匹配作为all_door_match
                if (
                    all_door_match is None
                    or variant_match["conf"] > all_door_match["conf"]
                ):
                    all_door_match = variant_match

    # 保存all_door的匹配结果到JSON（用于调试）
    if all_door_matches:
        variant_summary = {k: v for k, v in all_door_matches.items()}
        json_path = output_dir / "all_door_variants.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(variant_summary, f, ensure_ascii=False, indent=2)

    all_matches = []
    door_best_matches = {}  # 保存每个 door 的最佳匹配

    for tpl_id in [1, 2, 3, 4]:
        tpl_path = tpl_dir / f"door{tpl_id}.png"
        tpl = cv.imread(str(tpl_path))
        if tpl is None:
            continue

        door_best = None
        for scale in SCALES:
            item = match_single(
                roi_bgr,
                tpl,
                tpl_id,
                scale,
            )
            if item is None:
                continue
            all_matches.append(item)

            if door_best is None:
                door_best = item
            else:
                if adjusted_score(item) > adjusted_score(door_best):
                    door_best = item

        if door_best is not None:
            door_best_matches[tpl_id] = door_best

    if not all_matches:
        return {"status": "failed", "reason": "No valid matches were produced"}

    all_matches.sort(key=lambda x: x["conf"], reverse=True)
    best = all_matches[0]

    # 保存 all_door.png 的匹配结果
    if all_door_match:
        annotated = image.copy()
        ax1, ay1 = all_door_match["x"], all_door_match["y"]
        ax2, ay2 = ax1 + all_door_match["width"], ay1 + all_door_match["height"]
        cv.rectangle(annotated, (ax1, ay1), (ax2, ay2), (255, 0, 0), 2)
        label = f"all_door conf={all_door_match['conf']:.4f} scale={all_door_match['scale']:.2f}"
        cv.putText(
            annotated,
            label,
            (10, 30),
            cv.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 0, 0),
            2,
            cv.LINE_AA,
        )

        img_path = output_dir / "all_door_match_result.png"
        cv.imwrite(str(img_path), annotated)

        json_path = output_dir / "all_door_match_result.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(all_door_match, f, ensure_ascii=False, indent=2)

    # 保存每个 door 的匹配结果（图像 + JSON）
    for tpl_id in [1, 2, 3, 4]:
        if tpl_id not in door_best_matches:
            continue

        best_item = door_best_matches[tpl_id]

        # 保存图像
        annotated = image.copy()
        bx1, by1 = best_item["x"], best_item["y"]
        bx2, by2 = bx1 + best_item["width"], by1 + best_item["height"]
        cv.rectangle(annotated, (bx1, by1), (bx2, by2), (0, 255, 0), 2)
        label = f"door{best_item['tpl_id']} conf={best_item['conf']:.4f} scale={best_item['scale']:.2f}"
        cv.putText(
            annotated,
            label,
            (10, 30),
            cv.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
            cv.LINE_AA,
        )

        img_path = output_dir / f"door{tpl_id}_match_result.png"
        cv.imwrite(str(img_path), annotated)

        # 保存 JSON
        json_path = output_dir / f"door{tpl_id}_match_result.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(best_item, f, ensure_ascii=False, indent=2)

    return {
        "status": "success",
        "image": image_path.name,
        "best_match": best,
        "all_door_match": all_door_match,
        "top_matches": all_matches[:3],
    }


def batch_test_doors():
    """批量测试 door_test1.png 到 door_test8.png"""
    repo_root = Path(__file__).resolve().parents[1]
    tests_dir = repo_root / "tests"
    tpl_dir = repo_root / "imgs" / "divergent"

    # 创建时间戳文件夹
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_output_dir = tests_dir / f"batch_results_{timestamp}"
    batch_output_dir.mkdir(parents=True, exist_ok=True)

    results_summary = []

    print("=" * 80)
    print(f"开始门图像批量测试，结果保存至: {batch_output_dir}")
    print("=" * 80)

    for test_num in range(1, 9):  # door_test1 到 door_test8
        image_filename = f"door_test{test_num if test_num > 1 else ''}.png"
        image_path = tests_dir / image_filename

        if not image_path.exists():
            print(f"\n⚠  【第{test_num}张】 {image_filename} 不存在，跳过")
            results_summary.append(
                {
                    "num": test_num,
                    "filename": image_filename,
                    "status": "skipped",
                    "reason": "文件不存在",
                }
            )
            continue

        print(f"\n{'=' * 80}")
        print(f"【第{test_num}张】开始测试: {image_filename}")
        print("=" * 80)

        # 创建该测试的输出文件夹
        test_output_dir = (
            batch_output_dir / f"test_{test_num:02d}_{image_filename[:-4]}"
        )
        test_output_dir.mkdir(parents=True, exist_ok=True)

        # 执行单张测试
        result = test_single_door(image_path, test_output_dir, tpl_dir)
        result["num"] = test_num
        result["filename"] = image_filename
        results_summary.append(result)

        # 输出测试结果
        if result["status"] == "success":
            best = result["best_match"]
            print("✓ 测试成功")
            print(f"  最佳匹配: door{best['tpl_id']} - 置信度: {best['conf']:.4f}")
            if result["all_door_match"]:
                all_door = result["all_door_match"]
                print(f"  all_door 匹配: 置信度: {all_door['conf']:.4f}")
            print(f"  结果保存至: {test_output_dir}")
        else:
            print(f"✗ 测试失败: {result.get('reason', '未知原因')}")

    # 保存总结报告
    print(f"\n{'=' * 80}")
    print("批量测试完成，生成总结报告")
    print("=" * 80)

    summary_json_path = batch_output_dir / "batch_summary.json"
    with open(summary_json_path, "w", encoding="utf-8") as f:
        json.dump(results_summary, f, ensure_ascii=False, indent=2)

    # 打印总结
    success_count = sum(1 for r in results_summary if r["status"] == "success")
    skipped_count = sum(1 for r in results_summary if r["status"] == "skipped")
    failed_count = sum(1 for r in results_summary if r["status"] == "failed")

    print("\n总结:")
    print(f"  成功: {success_count} / {len(results_summary)}")
    print(f"  跳过: {skipped_count}")
    print(f"  失败: {failed_count}")
    print(f"\n总结报告已保存: {summary_json_path}")
    print(f"所有结果已保存至: {batch_output_dir}")


def main():
    """
    执行模式选择：
    - 如果存在 door_test1.png，执行批量测试
    - 否则，执行单个 door_test.png 测试
    """
    repo_root = Path(__file__).resolve().parents[1]
    tests_dir = repo_root / "tests"

    if (tests_dir / "door_test1.png").exists():
        batch_test_doors()
    else:
        print("执行单张测试模式")
        image_path = tests_dir / "door_test.png"
        tpl_dir = repo_root / "imgs" / "divergent"
        output_dir = tests_dir / "single_test_result"
        output_dir.mkdir(parents=True, exist_ok=True)

        result = test_single_door(image_path, output_dir, tpl_dir)
        if result["status"] == "success":
            print("✓ 测试成功")
            print(f"结果已保存至: {output_dir}")
        else:
            print(f"✗ 测试失败: {result.get('reason', '未知原因')}")


if __name__ == "__main__":
    main()
