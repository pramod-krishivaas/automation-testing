import os
import cv2
import numpy as np
import logging

# scikit-image used to be imported here for SSIM. It is not in requirements.txt,
# so this whole module failed to import; SSIM is computed with OpenCV below.

logger = logging.getLogger(__name__)

# ─── HSV color ranges ─────────────────────────────────────────────────────────
GREEN_LOWER = np.array([35, 40, 40])
GREEN_UPPER = np.array([90, 255, 255])

BLUE_LOWER  = np.array([90, 50, 50])
BLUE_UPPER  = np.array([140, 255, 255])

# ─── Percentage thresholds ────────────────────────────────────────────────────
CROP_HEALTH_GREEN_MIN_PCT = 5.0   # crop-health map must have ≥ 5% green pixels
CROP_HEALTH_BLUE_MAX_PCT  = 1.0   # crop-health map must have < 1% blue pixels
MOISTURE_BLUE_MIN_PCT     = 3.0   # moisture cards must have ≥ 3% blue pixels
MOISTURE_GREEN_MAX_PCT    = 1.0   # moisture cards must have < 1% green pixels
SSIM_CHANGE_THRESHOLD     = 0.95  # score < 0.95 → map changed after slider tap

# ─────────────────────────────────────────────────────────────────────────────
# PIXEL FINGERPRINT CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
# Both leaf moisture and soil moisture render the same blue colour family.
# The ONLY reliable way to tell them apart is to:
#   1. Manually open a known-good screenshot of each screen in any image editor.
#   2. Note the (x, y) of a stable, always-blue pixel in the card map area.
#   3. Read its RGB values and paste them below.
#   4. During the test, sample that exact pixel and check it falls within
#      PIXEL_TOLERANCE of the stored reference.
#
# HOW TO CALIBRATE:
#   python - <<'EOF'
#   from utils.cv_validator import get_pixel_rgb
#   # Run this after saving a reference screenshot from the device
#   print(get_pixel_rgb("screenshots/leaf_moisture_reference.png", 540, 900))
#   print(get_pixel_rgb("screenshots/soil_moisture_reference.png", 540, 900))
#   EOF
#
# Then replace the placeholder values below with the printed output.

LEAF_MOISTURE_REFERENCE_PIXEL = {"red": 0, "green": 0, "blue": 0}   # ← FILL IN
SOIL_MOISTURE_REFERENCE_PIXEL = {"red": 0, "green": 0, "blue": 0}   # ← FILL IN

# x, y pixel coordinate to sample on each screen (same point used for both)
MOISTURE_SAMPLE_X = 540   # ← adjust to centre of the coloured card map area
MOISTURE_SAMPLE_Y = 900   # ← adjust to centre of the coloured card map area

# How many RGB units of wiggle room we allow (device rendering variance)
PIXEL_TOLERANCE   = 20


# ─── Internal helpers ─────────────────────────────────────────────────────────

def as_image(image) -> np.ndarray:
    """A BGR array from what the callers hand in. A screenshot taken from the driver
    during the run is passed as an array (see `decode_png`); a file path still works
    for saved reference images. Every function below accepts either."""
    if isinstance(image, (str, os.PathLike)):
        img = cv2.imread(os.fspath(image))
        if img is None:
            raise FileNotFoundError(f"crop_health: cannot read '{image}'")
        return img
    if image is None or not hasattr(image, "shape"):
        raise TypeError("crop_health: expected an image array or a file path")
    return image


def decode_png(png_bytes: bytes) -> np.ndarray:
    """A BGR array from PNG bytes, e.g. `driver.get_screenshot_as_png()`."""
    img = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("crop_health: the screenshot bytes are not a readable image")
    return img


def encode_png(image: np.ndarray) -> bytes:
    """PNG bytes of an image array, e.g. to attach to an Allure report."""
    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("crop_health: could not encode the image as PNG")
    return buffer.tobytes()


def _describe(image) -> str:
    """Short label for logs: the path, or the size of an in-memory screenshot."""
    if isinstance(image, (str, os.PathLike)):
        return os.fspath(image)
    shape = getattr(image, "shape", None)
    return f"<screenshot {shape[1]}x{shape[0]}>" if shape else "<image>"


def _load_and_crop(image_path, roi: tuple | None):
    img = as_image(image_path)
    if roi:
        x, y, w, h = roi
        img = img[y : y + h, x : x + w]
    return img


def _mask_color(img_bgr, lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, lower, upper)


def _pct(mask: np.ndarray, total_pixels: int) -> float:
    return round(cv2.countNonZero(mask) / total_pixels * 100, 2)


def _pixel_within_tolerance(actual: dict, reference: dict,
                             tolerance: int = PIXEL_TOLERANCE) -> bool:
    """
    Return True if actual RGB is within `tolerance` units of reference RGB
    on all three channels.
    """
    return all(
        abs(actual[ch] - reference[ch]) <= tolerance
        for ch in ("red", "green", "blue")
    )


# ─── Pixel-level accessors ────────────────────────────────────────────────────

def get_pixel_rgb(image_path, x: int, y: int) -> dict:
    img = as_image(image_path)
    b, g, r = img[y, x]
    return {"red": int(r), "green": int(g), "blue": int(b)}


def get_pixel_hsv(image_path, x: int, y: int) -> dict:
    img = as_image(image_path)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[y, x]
    return {"hue": int(h), "saturation": int(s), "value": int(v)}


def calculate_pixel_intensity(pixel: dict) -> float:
    return round((pixel["red"] + pixel["green"] + pixel["blue"]) / 3, 2)


# ─── Percentage utilities ──────────────────────────────────────────────────────

def calculate_green_percentage(image_path: str, roi: tuple | None = None) -> float:
    img   = _load_and_crop(image_path, roi)
    mask  = _mask_color(img, GREEN_LOWER, GREEN_UPPER)
    total = img.shape[0] * img.shape[1]
    pct   = _pct(mask, total)
    logger.debug("Green%%: %.2f  image=%s", pct, _describe(image_path))
    return pct


def calculate_blue_percentage(image_path: str, roi: tuple | None = None) -> float:
    img   = _load_and_crop(image_path, roi)
    mask  = _mask_color(img, BLUE_LOWER, BLUE_UPPER)
    total = img.shape[0] * img.shape[1]
    pct   = _pct(mask, total)
    logger.debug("Blue%%: %.2f  image=%s", pct, _describe(image_path))
    return pct


# ─── The crop-health layer ────────────────────────────────────────────────────
# The map draws the vegetation index as a layer of pure green (R and B close to
# 0) whose brightness is the value: bright green = "No issue", black = "May be
# issue". A regular grid of holes lets the satellite basemap show through.
#
# This is NOT the palette of the legend bar under the map (a yellower green), so
# pixels are classified by green brightness rather than by matching legend
# colours. The old HSV "stress" buckets looked for yellow, red and magenta hues,
# which never appear on this green-to-black scale, and counted the black end
# (V < 40) as nothing at all.
HEAT_GREEN_LEAD        = 25     # G must lead both R and B by at least this much
HEAT_SIDE_RATIO        = 0.45   # ...and R, B must stay under this share of G
HEAT_NEAR_BLACK_MAX    = 14     # every channel at or below this: the black end
MIN_LAYER_COVERAGE_PCT = 3.0    # the largest layer region, as % of the map area

# Bands of the index scale (index = green channel / 255). The keys are the names
# the date-slider validator already reports.
VEGETATION_BANDS = (
    ("healthy",  0.60, 1.01),   # "No issue" end
    ("moderate", 0.35, 0.60),
    ("stressed", 0.15, 0.35),
    ("severe",   0.00, 0.15),   # black: "May be issue"
)
LEGEND_MIN_FALL_OFF = 60        # legend: green channel must drop this much, left to right


def heat_mask(img_bgr: np.ndarray) -> np.ndarray:
    """True where a pixel is the crop-health layer: pure green of any brightness,
    or its black end. Satellite fields (a lot of red) and the dark grey map
    buttons (all channels equal, well above black) are not."""
    b, g, r = (img_bgr[..., i].astype(np.int16) for i in range(3))
    side = np.maximum(r, b)
    green = (g - side >= HEAT_GREEN_LEAD) & (side <= HEAT_SIDE_RATIO * g)
    black = np.maximum(g, side) <= HEAT_NEAR_BLACK_MAX
    return green | black


def _layer_region(mask: np.ndarray):
    """The layer's largest connected region, with the grid of holes closed.
    Returns (region_mask, bbox_x_y_w_h, area_px); an empty mask if there is none."""
    h, w = mask.shape
    k = max(3, int(round(w * 0.012)) | 1)
    closed = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    if count <= 1:
        return np.zeros_like(mask, dtype=bool), (0, 0, 0, 0), 0
    best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, bw, bh, area = (int(v) for v in stats[best])
    return labels == best, (x, y, bw, bh), area


def _bands(green_values: np.ndarray) -> dict:
    """Share of layer pixels in each band, % of the layer."""
    out = {f"{name}_pct": 0.0 for name, _, _ in VEGETATION_BANDS}
    if green_values.size == 0:
        return out
    index = green_values.astype(np.float32) / 255.0
    for name, low, high in VEGETATION_BANDS:
        out[f"{name}_pct"] = round(float(((index >= low) & (index < high)).mean()) * 100, 2)
    return out


def analyze_legend(img_bgr: np.ndarray, legend_roi: tuple | None) -> dict | None:
    """Read the gradient bar under the map: is it there, and does it fade from a
    bright green on the left ("No issue") to something darker on the right?"""
    if not legend_roi:
        return None
    x, y, w, h = legend_roi
    band = img_bgr[y:y + h, x:x + w]
    if band.size == 0:
        return {"present": False, "ok": False, "reason": "legend area is outside the screenshot"}
    # Median over the band's rows: the "No issue" / "May be issue" labels sit on
    # the bar and cover only some rows at any column.
    columns = np.median(band, axis=0)[:, ::-1]            # RGB per column
    edge = max(1, int(len(columns) * 0.10))
    left, right = columns[:edge].mean(0), columns[-edge:].mean(0)
    left_green = left[1] - max(left[0], left[2]) >= HEAT_GREEN_LEAD
    falls_off = (left[1] - right[1]) >= LEGEND_MIN_FALL_OFF
    return {"present": True, "ok": bool(left_green and falls_off),
            "left_rgb": [int(v) for v in left], "right_rgb": [int(v) for v in right],
            "reason": "OK" if (left_green and falls_off) else
                      f"legend left={tuple(int(v) for v in left)} right={tuple(int(v) for v in right)}: "
                      "expected a bright green on the left fading darker to the right"}


def analyze_crop_health(image, roi: tuple | None = None, legend_roi: tuple | None = None,
                        min_coverage_pct: float = MIN_LAYER_COVERAGE_PCT) -> dict:
    """Is the crop-health layer on the map, and how is it distributed?

    `image` is a path or a BGR array; `roi` = (x, y, w, h) is the map area (not
    the buttons or icon row drawn over its bottom), `legend_roi` the gradient bar.
    Returns a dict; `shown` is the verdict, `reason` says why.
    """
    img = as_image(image)
    x0, y0, w0, h0 = roi if roi else (0, 0, img.shape[1], img.shape[0])
    crop = img[y0:y0 + h0, x0:x0 + w0]
    total = crop.shape[0] * crop.shape[1]

    raw = heat_mask(crop)
    region, (rx, ry, rw, rh), area = _layer_region(raw)
    coverage = round(area / total * 100, 2) if total else 0.0
    in_layer = raw & region
    bands = _bands(crop[..., 1][in_layer])           # green channel of the layer's pixels
    dominant = max((n for n, _, _ in VEGETATION_BANDS), key=lambda n: bands[f"{n}_pct"]) \
        if in_layer.any() else None
    legend = analyze_legend(img, legend_roi)

    shown = coverage >= min_coverage_pct
    if shown:
        reason = f"layer covers {coverage}% of the map (need >= {min_coverage_pct}%)"
    else:
        reason = (f"no crop-health layer: its largest region covers {coverage}% of the map "
                  f"(need >= {min_coverage_pct}%)")
    result = {
        "shown": shown, "reason": reason,
        "coverage_pct": coverage, "min_coverage_pct": min_coverage_pct,
        "heat_pixel_pct": round(float(raw.mean()) * 100, 2) if total else 0.0,
        "region_bbox": (x0 + rx, y0 + ry, rw, rh) if area else None,
        "bands": bands, "dominant": dominant, "legend": legend,
        "roi": (x0, y0, w0, h0), "legend_roi": legend_roi,
    }
    logger.info("crop health: %s", {k: v for k, v in result.items() if k != "bands"})
    return result


def annotate_crop_health(image, result: dict, out_path: str | None = None) -> np.ndarray:
    """Evidence image: the map area outlined, the detected layer tinted magenta
    (a colour the layer itself never has) and the verdict written on it.
    Returns the image; it is also written to `out_path` when one is given. The
    input is not modified."""
    img = as_image(image).copy()
    x0, y0, w0, h0 = result["roi"]
    crop = img[y0:y0 + h0, x0:x0 + w0]
    region, _, _ = _layer_region(heat_mask(crop))
    tint = crop.copy()
    tint[region] = (255, 0, 255)
    img[y0:y0 + h0, x0:x0 + w0] = cv2.addWeighted(crop, 0.55, tint, 0.45, 0)
    cv2.rectangle(img, (x0, y0), (x0 + w0, y0 + h0), (0, 215, 255), 2)
    legend = result.get("legend")
    verdict = "CROP HEALTH SHOWN" if result["shown"] else "CROP HEALTH NOT SHOWN"
    label = f"{verdict} - {result['coverage_pct']}% of the map"
    colour = (60, 160, 40) if result["shown"] else (40, 40, 220)
    scale = max(0.5, img.shape[1] / 900)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
    cv2.rectangle(img, (0, 0), (tw + 20, th + 24), colour, -1)
    cv2.putText(img, label, (10, th + 10), cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), 2, cv2.LINE_AA)
    if legend and result.get("legend_roi"):
        lx, ly, lw, lh = result["legend_roi"]
        cv2.rectangle(img, (lx, ly), (lx + lw, ly + lh),
                      (60, 160, 40) if legend["ok"] else (40, 40, 220), 2)
    if out_path:
        cv2.imwrite(out_path, img)
    return img


# ─── Stress markers ───────────────────────────────────────────────────────────
# Parts of the farm that need attention are marked on the map with small outlined
# cells in four flat colours, which the legend card under the date slider names
# and gives the share of (Caution 0.30% ...). The colours are the legend dots'.
STRESS_TYPES = ("caution", "warning", "stressed", "severely_stressed")
STRESS_LABELS = {"caution": "Caution", "warning": "Warning",
                 "stressed": "Stressed", "severely_stressed": "Severely Stressed"}
STRESS_MARKER_RGB = {                        # measured on the legend dots
    "caution":           (255, 255, 1),      # yellow
    "warning":           (255, 165, 1),      # orange
    "stressed":          (255, 65, 255),     # magenta
    "severely_stressed": (255, 1, 1),        # red
}
STRESS_MAX_COLOUR_DISTANCE = 60   # RGB distance to the nearest stress colour
STRESS_MIN_PART_PX = 8            # smaller specks are anti-aliasing, not markers


def analyze_stress(image, roi: tuple | None = None) -> dict:
    """Find the stress markers on the map, by colour, and estimate each type's share.

    `roi` = (x, y, w, h) is the map area. Markers are only looked for on and just
    around the crop-health layer, so the legend dots and icons are not counted.
    The estimate is the markers' filled area as a % of the layer's area; it is
    approximate (a marker is an outlined cell) and meant to corroborate the
    percentages the app displays, not replace them.
    """
    img = as_image(image)
    x0, y0, w0, h0 = roi if roi else (0, 0, img.shape[1], img.shape[0])
    crop = img[y0:y0 + h0, x0:x0 + w0]
    region, _, layer_area = _layer_region(heat_mask(crop))
    types = {name: {"detected": False, "parts": 0, "marker_px": 0, "area_px": 0,
                    "area_pct_of_layer": 0.0, "boxes": []} for name in STRESS_TYPES}
    result = {"layer_area_px": int(layer_area), "types": types}
    if layer_area == 0:
        return result

    reach = max(5, int(round(w0 * 0.03)) | 1)          # markers sit on the layer's edge cells too
    near = cv2.dilate(region.astype(np.uint8), np.ones((reach, reach), np.uint8)).astype(bool)
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.int32)
    distance = np.stack([((rgb - np.array(STRESS_MARKER_RGB[n])) ** 2).sum(-1) for n in STRESS_TYPES], -1)
    nearest = distance.argmin(-1)
    close = (distance.min(-1) <= STRESS_MAX_COLOUR_DISTANCE ** 2) & near

    for i, name in enumerate(STRESS_TYPES):
        mask = (close & (nearest == i)).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        keep = [j for j in range(1, count) if stats[j, cv2.CC_STAT_AREA] >= STRESS_MIN_PART_PX]
        kept = np.isin(labels, keep).astype(np.uint8)
        contours, _ = cv2.findContours(kept, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        filled = np.zeros_like(kept)
        cv2.drawContours(filled, contours, -1, 1, thickness=cv2.FILLED)
        types[name] = {
            "detected": bool(keep), "parts": len(keep), "marker_px": int(kept.sum()),
            "area_px": int(filled.sum()),
            "area_pct_of_layer": round(float(filled.sum()) / layer_area * 100, 2),
            "boxes": [(x0 + int(stats[j, 0]), y0 + int(stats[j, 1]),
                       int(stats[j, 2]), int(stats[j, 3])) for j in keep],
        }
    logger.info("stress markers: %s", {n: (t["parts"], t["area_pct_of_layer"]) for n, t in types.items()})
    return result


_STRESS_DRAW_BGR = {"caution": (0, 255, 255), "warning": (0, 165, 255),
                    "stressed": (255, 0, 255), "severely_stressed": (0, 0, 255)}


def annotate_stress_markers(image, stress: dict) -> np.ndarray:
    """Evidence image: every detected marker boxed in white, with a key of how
    many of each type were found. The input is not modified."""
    img = as_image(image).copy()
    scale = max(0.4, img.shape[1] / 900)
    pad = max(3, int(round(img.shape[1] * 0.012)))
    for name, info in stress["types"].items():
        for x, y, w, h in info["boxes"]:
            cv2.rectangle(img, (x - pad, y - pad), (x + w + pad, y + h + pad), (255, 255, 255), 2)
    row_h = int(34 * scale) + 6
    cv2.rectangle(img, (0, 0), (img.shape[1], row_h), (30, 30, 30), -1)
    x = 8
    for name in STRESS_TYPES:
        info = stress["types"][name]
        text = f"{STRESS_LABELS[name]}: {info['parts']}"
        cv2.circle(img, (x + 6, row_h // 2), 6, _STRESS_DRAW_BGR[name], -1)
        cv2.putText(img, text, (x + 18, row_h // 2 + int(5 * scale)), cv2.FONT_HERSHEY_SIMPLEX,
                    0.45 * scale, (255, 255, 255), 1, cv2.LINE_AA)
        x += 18 + int(cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.45 * scale, 1)[0][0]) + 14
    return img


def get_stress_level(image_path: str, roi: tuple | None = None) -> dict:
    """Share of the layer in each band, and the dominant one. Same keys as before,
    now measured on the green-to-black scale of this screen."""
    result = analyze_crop_health(image_path, roi)
    out = dict(result["bands"])
    out["dominant"] = result["dominant"] or "none"
    logger.info("Stress level: %s", out)
    return out


# ─── SSIM image comparison ────────────────────────────────────────────────────

def compare_images_ssim(img1_path, img2_path, roi: tuple | None = None) -> float:
    img1 = _load_and_crop(img1_path, roi)
    img2 = _load_and_crop(img2_path, roi)
    if img1.shape != img2.shape:
        img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
    score = _ssim(gray1, gray2)
    logger.info("SSIM: %.4f  (%s vs %s)", score, _describe(img1_path), _describe(img2_path))
    return round(float(score), 4)


def _ssim(a: np.ndarray, b: np.ndarray) -> float:
    """Mean structural similarity of two grey images (Gaussian window 11, sigma
    1.5: the standard definition), without scikit-image."""
    a, b = a.astype(np.float64), b.astype(np.float64)
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    blur = lambda m: cv2.GaussianBlur(m, (11, 11), 1.5)   # noqa: E731
    mu_a, mu_b = blur(a), blur(b)
    var_a = blur(a * a) - mu_a * mu_a
    var_b = blur(b * b) - mu_b * mu_b
    cov = blur(a * b) - mu_a * mu_b
    ssim_map = ((2 * mu_a * mu_b + c1) * (2 * cov + c2)) / \
               ((mu_a * mu_a + mu_b * mu_b + c1) * (var_a + var_b + c2))
    return float(ssim_map.mean())


# ─── High-level validators ────────────────────────────────────────────────────

def validate_crop_health(image_path: str, roi: tuple | None = None,
                         legend_roi: tuple | None = None) -> dict:
    """
    Assert the crop-health layer is on the map (see analyze_crop_health). The
    old check passed on any 5% of green-ish pixels and ignored the black end,
    so a basemap of fields passed with no layer drawn at all.
    """
    result = analyze_crop_health(image_path, roi, legend_roi)
    result["screen"] = "crop_health"
    result["passed"] = result["shown"]
    if not result["shown"]:
        raise AssertionError(f"[crop_health] {result['reason']}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# MOISTURE SCREEN IDENTIFICATION VIA PIXEL FINGERPRINT
# ─────────────────────────────────────────────────────────────────────────────
# Because leaf moisture and soil moisture both render blue pixels at the same
# intensity, the ONLY way to differentiate them programmatically (without
# relying solely on OCR) is to compare the sampled pixel at a fixed (x, y)
# against a pre-calibrated reference value for each screen.
#
# Workflow:
#   Step 1 – Blue pixel check  →  confirms we are on a moisture screen at all
#   Step 2 – Pixel fingerprint →  identifies WHICH moisture screen
#   Step 3 – OCR title check   →  secondary confirmation (in ocr_utils.py)
# ─────────────────────────────────────────────────────────────────────────────

def _validate_moisture_common(image_path: str, roi: tuple | None) -> dict:
    """Shared blue-pixel check used by both leaf and soil validators."""
    blue_pct  = calculate_blue_percentage(image_path, roi)
    green_pct = calculate_green_percentage(image_path, roi)
    passed    = (blue_pct  >= MOISTURE_BLUE_MIN_PCT and
                 green_pct <  MOISTURE_GREEN_MAX_PCT)
    return {
        "blue_pct":  blue_pct,
        "green_pct": green_pct,
        "blue_check_passed": passed,
    }


def validate_leaf_moisture(image_path: str,
                            sample_x: int = MOISTURE_SAMPLE_X,
                            sample_y: int = MOISTURE_SAMPLE_Y,
                            roi: tuple | None = None) -> dict:

    common   = _validate_moisture_common(image_path, roi)
    actual   = get_pixel_rgb(image_path, sample_x, sample_y)
    fp_match = _pixel_within_tolerance(actual, LEAF_MOISTURE_REFERENCE_PIXEL)

    passed   = common["blue_check_passed"] and fp_match
    result   = {
        "screen":        "leaf_moisture",
        **common,
        "sample_xy":     (sample_x, sample_y),
        "actual_pixel":  actual,
        "reference_pixel": LEAF_MOISTURE_REFERENCE_PIXEL,
        "fingerprint_match": fp_match,
        "tolerance":     PIXEL_TOLERANCE,
        "passed":        passed,
        "reason":        (
            "OK" if passed else
            f"blue_check={common['blue_check_passed']} | "
            f"fp_match={fp_match} actual={actual} ref={LEAF_MOISTURE_REFERENCE_PIXEL}"
        ),
    }
    if not passed:
        raise AssertionError(f"[leaf_moisture] {result['reason']}")
    logger.info("validate_leaf_moisture PASSED: %s", result)
    return result


def validate_soil_moisture(image_path: str,
                            sample_x: int = MOISTURE_SAMPLE_X,
                            sample_y: int = MOISTURE_SAMPLE_Y,
                            roi: tuple | None = None) -> dict:
    
    common   = _validate_moisture_common(image_path, roi)
    actual   = get_pixel_rgb(image_path, sample_x, sample_y)
    fp_match = _pixel_within_tolerance(actual, SOIL_MOISTURE_REFERENCE_PIXEL)

    passed   = common["blue_check_passed"] and fp_match
    result   = {
        "screen":        "soil_moisture",
        **common,
        "sample_xy":     (sample_x, sample_y),
        "actual_pixel":  actual,
        "reference_pixel": SOIL_MOISTURE_REFERENCE_PIXEL,
        "fingerprint_match": fp_match,
        "tolerance":     PIXEL_TOLERANCE,
        "passed":        passed,
        "reason":        (
            "OK" if passed else
            f"blue_check={common['blue_check_passed']} | "
            f"fp_match={fp_match} actual={actual} ref={SOIL_MOISTURE_REFERENCE_PIXEL}"
        ),
    }
    if not passed:
        raise AssertionError(f"[soil_moisture] {result['reason']}")
    logger.info("validate_soil_moisture PASSED: %s", result)
    return result


# ─── Calibration helper ───────────────────────────────────────────────────────

def calibrate_moisture_pixels(leaf_screenshot: str,
                               soil_screenshot: str,
                               sample_x: int = MOISTURE_SAMPLE_X,
                               sample_y: int = MOISTURE_SAMPLE_Y) -> dict:
   
    leaf_pixel = get_pixel_rgb(leaf_screenshot, sample_x, sample_y)
    soil_pixel = get_pixel_rgb(soil_screenshot, sample_x, sample_y)
    print("=" * 50)
    print(f"LEAF_MOISTURE_REFERENCE_PIXEL = {leaf_pixel}")
    print(f"SOIL_MOISTURE_REFERENCE_PIXEL = {soil_pixel}")
    print(f"Sample coordinate: ({sample_x}, {sample_y})")
    print("=" * 50)
    return {"leaf": leaf_pixel, "soil": soil_pixel}


# ─── Date slider validator ────────────────────────────────────────────────────

def validate_date_slider_changed(before, after, roi: tuple | None = None) -> dict:
    """
    Confirm map re-rendered after a plus/minus tap (SSIM < threshold).
    Also records green-pixel delta and stress-level change across dates.
    `before` and `after` are the screenshots taken from the driver (arrays), or paths.
    """
    score  = compare_images_ssim(before, after, roi)
    changed = score < SSIM_CHANGE_THRESHOLD

    green_before   = calculate_green_percentage(before, roi)
    green_after    = calculate_green_percentage(after, roi)
    stress_before  = get_stress_level(before, roi)
    stress_after   = get_stress_level(after, roi)

    result = {
        "ssim_score":         score,
        "map_changed":        changed,
        "green_before_pct":   green_before,
        "green_after_pct":    green_after,
        "green_delta":        round(green_after - green_before, 2),
        "stress_before":      stress_before["dominant"],
        "stress_after":       stress_after["dominant"],
        "full_stress_before": stress_before,
        "full_stress_after":  stress_after,
    }
    if not changed:
        logger.warning("Slider may not have updated map (SSIM=%.4f)", score)
    else:
        logger.info("Slider map change confirmed (SSIM=%.4f): %s", score, result)
    return result