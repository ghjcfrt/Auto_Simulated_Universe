from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2 as cv
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCREENSHOT = (
    PROJECT_ROOT
    / "logs"
    / "door_debug"
    / "20260517_021419_418457_0028_portal_opening_days_f_raw.png"
)
DEFAULT_TEMPLATE_NAMES = ["all_door.png", "all_door_up.png", "all_door_down.png"]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "logs" / "door_match_confidence"


def make_door_color_masks(hsv_img: np.ndarray):
    pink = cv.inRange(hsv_img, np.array([140, 55, 70]), np.array([175, 255, 255]))
    yellow = cv.inRange(hsv_img, np.array([18, 65, 85]), np.array([42, 255, 255]))
    glass_cyan_green = cv.inRange(
        hsv_img, np.array([113, 49, 96]), np.array([123, 109, 156])
    )
    glass_highlight = cv.inRange(
        hsv_img, np.array([0, 0, 180]), np.array([180, 60, 255])
    )
    return pink, yellow, glass_cyan_green, glass_highlight


def enhance_mask_connectivity(mask_bin: np.ndarray) -> np.ndarray:
    mask_u8 = (mask_bin > 0).astype(np.uint8)
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


def normalized_mask_overlap_map(
    roi_mask: np.ndarray, tpl_mask: np.ndarray
) -> np.ndarray:
    roi_bin = enhance_mask_connectivity(roi_mask)
    tpl_bin = enhance_mask_connectivity(tpl_mask)
    tpl_area = float(tpl_bin.sum())
    if tpl_area <= 1e-6:
        out_h = roi_bin.shape[0] - tpl_bin.shape[0] + 1
        out_w = roi_bin.shape[1] - tpl_bin.shape[1] + 1
        return np.zeros((max(1, out_h), max(1, out_w)), dtype=np.float32)
    overlap_map = cv.matchTemplate(roi_bin, tpl_bin, cv.TM_CCORR)
    return overlap_map / tpl_area


def load_one_all_door_template(template_path: Path) -> dict[str, np.ndarray]:
    tpl = cv.imread(str(template_path))
    if tpl is None:
        raise FileNotFoundError(f"Template not found or unreadable: {template_path}")
    tpl_hsv = cv.cvtColor(tpl, cv.COLOR_BGR2HSV)
    tpl_pink, tpl_yellow, _, _ = make_door_color_masks(tpl_hsv)
    return {
        "name": template_path.name,
        "image": tpl,
        "edge": cv.Canny(tpl, 50, 150),
        "pink": tpl_pink,
        "yellow": tpl_yellow,
    }


def load_all_door_templates(template_path: Path | None) -> list[dict[str, np.ndarray]]:
    if template_path is not None:
        return [load_one_all_door_template(template_path)]
    return [
        load_one_all_door_template(PROJECT_ROOT / "imgs" / "divergent" / name)
        for name in DEFAULT_TEMPLATE_NAMES
    ]


def match_all_door(
    screen_bgr: np.ndarray,
    all_door_tpl: list[dict[str, np.ndarray]],
    origin_x: int = 0,
    origin_y: int = 0,
    distance_scales: list[float] | None = None,
) -> dict[str, float | int] | None:
    roi_h, roi_w = screen_bgr.shape[:2]
    roi_edge = cv.Canny(screen_bgr, 50, 150)
    roi_hsv = cv.cvtColor(screen_bgr, cv.COLOR_BGR2HSV)
    roi_pink, roi_yellow, _, _ = make_door_color_masks(roi_hsv)

    best = None
    if distance_scales is None:
        distance_scales = [0.45, 0.55, 0.65, 0.75, 0.85, 1.0, 1.15, 1.3, 1.5, 1.7]
    for tpl in all_door_tpl:
        tpl_edge = tpl["edge"]
        tpl_pink = tpl["pink"]
        tpl_yellow = tpl["yellow"]
        th, tw = tpl_edge.shape[:2]
        for scale in distance_scales:
            rw, rh = max(1, int(tw * scale)), max(1, int(th * scale))
            if rw >= roi_w or rh >= roi_h:
                continue

            scaled_edge = cv.resize(tpl_edge, (rw, rh), interpolation=cv.INTER_LINEAR)
            scaled_pink = cv.resize(tpl_pink, (rw, rh), interpolation=cv.INTER_NEAREST)
            scaled_yellow = cv.resize(
                tpl_yellow, (rw, rh), interpolation=cv.INTER_NEAREST
            )

            edge_map = cv.matchTemplate(roi_edge, scaled_edge, cv.TM_CCORR_NORMED)
            pink_map = normalized_mask_overlap_map(roi_pink, scaled_pink)
            yellow_map = normalized_mask_overlap_map(roi_yellow, scaled_yellow)

            frame_color_map = 0.70 * pink_map + 0.30 * yellow_map
            score_map = 0.70 * frame_color_map + 0.30 * edge_map

            _, conf, _, max_loc = cv.minMaxLoc(score_map)
            item = {
                "conf": float(conf),
                "template": tpl["name"],
                "scale": float(scale),
                "center_x": float(origin_x + max_loc[0] + rw / 2),
                "center_y": float(origin_y + max_loc[1] + rh / 2),
                "width": int(rw),
                "height": int(rh),
                "x": int(origin_x + max_loc[0]),
                "y": int(origin_y + max_loc[1]),
            }
            if best is None or item["conf"] > best["conf"]:
                best = item

    return best


def create_feature_detector(method: str):
    method = method.lower()
    if method == "sift" and hasattr(cv, "SIFT_create"):
        return "sift", cv.SIFT_create()
    if method == "sift":
        print("SIFT is unavailable in this OpenCV build; falling back to ORB.")
    return "orb", cv.ORB_create(nfeatures=5000)


def feature_match_door(
    screen_bgr: np.ndarray,
    tpl: dict[str, np.ndarray],
    detector_name: str,
    detector,
    ratio: float = 0.7,
    ransac_reproj_threshold: float = 5.0,
    min_good_matches: int | None = None,
) -> dict:
    if min_good_matches is None:
        min_good_matches = 4 if detector_name == "orb" else 10
    tpl_img = tpl["image"]
    tpl_gray = cv.cvtColor(tpl_img, cv.COLOR_BGR2GRAY)
    screen_gray = cv.cvtColor(screen_bgr, cv.COLOR_BGR2GRAY)

    kp_tpl, des_tpl = detector.detectAndCompute(tpl_gray, None)
    kp_scr, des_scr = detector.detectAndCompute(screen_gray, None)
    result = {
        "template": tpl["name"],
        "detector": detector_name,
        "template_keypoints": len(kp_tpl),
        "screenshot_keypoints": len(kp_scr),
        "raw_matches": 0,
        "good_matches": 0,
        "inliers": 0,
        "inlier_ratio": 0.0,
        "homography_found": False,
        "projected_corners": None,
        "center_x": None,
        "center_y": None,
        "projection_source": "none",
    }
    if des_tpl is None or des_scr is None or len(kp_tpl) < 2 or len(kp_scr) < 2:
        return result

    if detector_name == "sift":
        matcher = cv.FlannBasedMatcher(
            dict(algorithm=1, trees=5),
            dict(checks=50),
        )
        if des_tpl.dtype != np.float32:
            des_tpl = des_tpl.astype(np.float32)
        if des_scr.dtype != np.float32:
            des_scr = des_scr.astype(np.float32)
    else:
        matcher = cv.BFMatcher(cv.NORM_HAMMING)

    raw_matches = matcher.knnMatch(des_tpl, des_scr, k=2)
    good_matches = [
        pair[0]
        for pair in raw_matches
        if len(pair) == 2 and pair[0].distance < ratio * pair[1].distance
    ]
    result["raw_matches"] = len(raw_matches)
    result["good_matches"] = len(good_matches)

    if len(good_matches) < min_good_matches:
        return result

    src_pts = np.float32([kp_tpl[m.queryIdx].pt for m in good_matches]).reshape(
        -1, 1, 2
    )
    dst_pts = np.float32([kp_scr[m.trainIdx].pt for m in good_matches]).reshape(
        -1, 1, 2
    )
    matrix, mask = cv.findHomography(src_pts, dst_pts, cv.RANSAC, ransac_reproj_threshold)
    if matrix is None or mask is None:
        return result

    inlier_mask = mask.ravel().astype(bool)
    inliers = int(inlier_mask.sum())
    result["homography_found"] = True
    result["inliers"] = inliers
    result["inlier_ratio"] = float(inliers / max(1, len(good_matches)))

    h, w = tpl_img.shape[:2]
    corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
    projected = cv.perspectiveTransform(corners, matrix).reshape(-1, 2)
    result["projected_corners"] = [
        [float(x), float(y)] for x, y in projected.tolist()
    ]
    result["center_x"] = float(projected[:, 0].mean())
    result["center_y"] = float(projected[:, 1].mean())
    result["projection_source"] = "homography"
    return result


def door_align_roi_x_range(screen_bgr: np.ndarray) -> list[int]:
    w = screen_bgr.shape[1]
    x1 = int(w * 900 / 1920)
    x2 = int(w * 1030 / 1920)
    return [max(0, x1), min(w, x2)]


def door_match_in_align_roi(match: dict | None, roi_x_range: list[int]) -> bool:
    if match is None:
        return False
    if match.get("center_x") is None:
        return False
    x1, x2 = roi_x_range
    return x1 <= match["center_x"] <= x2


def draw_match(screen_bgr: np.ndarray, match: dict | None, label: str, color) -> None:
    if not match:
        return
    x1 = int(match["x"])
    y1 = int(match["y"])
    x2 = x1 + int(match["width"])
    y2 = y1 + int(match["height"])
    cv.rectangle(screen_bgr, (x1, y1), (x2, y2), color, 2)
    cv.putText(
        screen_bgr,
        f"{label} conf={match['conf']:.4f} scale={match['scale']:.2f}",
        (x1, max(24, y1 - 8)),
        cv.FONT_HERSHEY_SIMPLEX,
        0.6,
        color,
        2,
    )


def draw_align_roi(screen_bgr: np.ndarray, roi_x_range: list[int]) -> None:
    x1, x2 = roi_x_range
    cv.line(
        screen_bgr,
        (x1, 0),
        (x1, screen_bgr.shape[0] - 1),
        (255, 0, 0),
        1,
    )
    cv.line(
        screen_bgr,
        (x2, 0),
        (x2, screen_bgr.shape[0] - 1),
        (255, 0, 0),
        1,
    )


def draw_feature_match(
    screen_bgr: np.ndarray,
    feature_result: dict,
    roi_x_range: list[int],
    image_path: Path,
    fallback_match: dict | None = None,
) -> None:
    marked = screen_bgr.copy()
    draw_align_roi(marked, roi_x_range)

    corners = feature_result.get("projected_corners")
    if corners:
        pts = np.int32(corners).reshape(-1, 1, 2)
        cv.polylines(marked, [pts], True, (0, 0, 255), 2)
        center_x = feature_result.get("center_x")
        center_y = feature_result.get("center_y")
        if center_x is not None and center_y is not None:
            cv.circle(marked, (int(center_x), int(center_y)), 5, (0, 0, 255), -1)
    elif fallback_match:
        x1 = int(fallback_match["x"])
        y1 = int(fallback_match["y"])
        x2 = x1 + int(fallback_match["width"])
        y2 = y1 + int(fallback_match["height"])
        cv.rectangle(marked, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv.circle(
            marked,
            (int(fallback_match["center_x"]), int(fallback_match["center_y"])),
            5,
            (0, 0, 255),
            -1,
        )
        feature_result["projected_corners"] = [
            [float(x1), float(y1)],
            [float(x2), float(y1)],
            [float(x2), float(y2)],
            [float(x1), float(y2)],
        ]
        feature_result["center_x"] = float(fallback_match["center_x"])
        feature_result["center_y"] = float(fallback_match["center_y"])
        feature_result["projection_source"] = "fallback_template_match"

    cv.putText(
        marked,
        (
            f"{feature_result['template']} {feature_result['detector']} "
            f"kp={feature_result['template_keypoints']}/"
            f"{feature_result['screenshot_keypoints']} "
            f"good={feature_result['good_matches']} "
            f"inliers={feature_result['inliers']} "
            f"source={feature_result['projection_source']}"
        ),
        (20, 40),
        cv.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 0, 255),
        2,
    )
    cv.imwrite(str(image_path), marked)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the current find-door all_door matcher on a saved screenshot."
    )
    parser.add_argument("screenshot", nargs="?", type=Path, default=DEFAULT_SCREENSHOT)
    parser.add_argument(
        "--template",
        type=Path,
        default=None,
        help="Optional single template path. Defaults to all_door/all_door_up/all_door_down.",
    )
    parser.add_argument(
        "--feature-detector",
        choices=["sift", "orb"],
        default="sift",
        help="Feature detector used for the SIFT/ORB + RANSAC experiment.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    screenshot = args.screenshot
    if not screenshot.is_absolute():
        screenshot = PROJECT_ROOT / screenshot
    template = args.template
    if template is not None and not template.is_absolute():
        template = PROJECT_ROOT / template

    screen = cv.imread(str(screenshot))
    if screen is None:
        raise FileNotFoundError(f"Screenshot not found or unreadable: {screenshot}")

    all_door_tpl = load_all_door_templates(template)
    full_match = match_all_door(screen, all_door_tpl)
    detector_name, detector = create_feature_detector(args.feature_detector)

    align_roi_x_range = door_align_roi_x_range(screen)
    full_match_in_roi = door_match_in_align_roi(full_match, align_roi_x_range)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = screenshot.stem.replace("_raw", "")

    template_matches = []
    feature_matches = []
    for tpl in all_door_tpl:
        template_full_match = match_all_door(screen, [tpl])
        template_in_roi = door_match_in_align_roi(
            template_full_match, align_roi_x_range
        )
        feature_result = feature_match_door(screen, tpl, detector_name, detector)
        feature_in_roi = door_match_in_align_roi(feature_result, align_roi_x_range)

        template_stem = Path(str(tpl["name"])).stem
        image_path = args.output_dir / f"{stem}_{template_stem}_match.png"
        feature_image_path = (
            args.output_dir / f"{stem}_{template_stem}_{detector_name}_ransac.png"
        )
        marked = screen.copy()
        draw_match(
            marked,
            template_full_match,
            f"{template_stem} full",
            (0, 220, 0),
        )
        draw_align_roi(marked, align_roi_x_range)
        cv.imwrite(str(image_path), marked)
        draw_feature_match(
            screen,
            feature_result,
            align_roi_x_range,
            feature_image_path,
            fallback_match=template_full_match,
        )

        template_matches.append(
            {
                "template": tpl["name"],
                "full_match": template_full_match,
                "in_align_roi": template_in_roi,
                "image_path": str(image_path),
            }
        )
        feature_result["in_align_roi"] = door_match_in_align_roi(
            feature_result, align_roi_x_range
        )
        feature_result["fallback_match"] = (
            template_full_match if feature_result["projection_source"] != "homography" else None
        )
        feature_result["image_path"] = str(feature_image_path)
        feature_matches.append(feature_result)

    result = {
        "screenshot": str(screenshot),
        "templates": [str(t["name"]) for t in all_door_tpl],
        "threshold": 0.60,
        "align_roi_x_range": align_roi_x_range,
        "align_roi_y": "all",
        "full_match": full_match,
        "full_match_in_align_roi": full_match_in_roi,
        "template_matches": template_matches,
        "feature_detector": detector_name,
        "feature_matches": feature_matches,
    }

    json_path = args.output_dir / f"{stem}_all_door_match.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"screenshot: {screenshot}")
    print(f"templates:  {[t['name'] for t in all_door_tpl]}")
    print(f"full_match:      {full_match}")
    print(f"align_roi_x:     {align_roi_x_range} (y=all)")
    print(f"full_in_roi:     {full_match_in_roi}")
    for item in template_matches:
        print(
            f"{item['template']}: full={item['full_match']} "
            f"in_align_roi={item['in_align_roi']}"
        )
        print(f"marked: {item['image_path']}")
    for item in feature_matches:
        print(
            f"{item['template']} {detector_name}: "
            f"kp={item['template_keypoints']}/{item['screenshot_keypoints']} "
            f"good={item['good_matches']} inliers={item['inliers']} "
            f"ratio={item['inlier_ratio']:.3f} "
            f"homography={item['homography_found']} "
            f"in_align_roi={item['in_align_roi']}"
        )
        print(f"feature_marked: {item['image_path']}")
    print(f"json:   {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
