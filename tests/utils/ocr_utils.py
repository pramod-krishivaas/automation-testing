import re
import sys
from difflib import SequenceMatcher

import cv2
import numpy as np
import pytesseract
from PIL import Image

sys.dont_write_bytecode = True

from utils.tesseract_setup import configure_tesseract

# Point pytesseract at the Tesseract engine binary regardless of the caller's PATH
# (the platform runs pytest in a subprocess whose env may not include scoop shims).
configure_tesseract()

# Sparse text: UI labels are scattered over the screen, not laid out as a page.
OCR_CONFIG = "--oem 3 --psm 11"
# Low on purpose: a misread word is still useful to the fuzzy phrase match below,
# which is what decides whether the target was found.
MIN_WORD_CONFIDENCE = 20
MIN_MATCH_RATIO = 0.8


def extract_text_with_coordinates(image_path):
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)

    texts = []
    for i in range(len(data["text"])):
        if int(data["conf"][i]) > 70:
            text = data["text"][i].strip()
            if text:
                (x, y, w, h) = (data["left"][i], data["top"][i], data["width"][i], data["height"][i])
                texts.append({"text": text, "coords": (x + w//2, y + h//2)})
    return texts


def _normalize(text):
    return " ".join(re.sub(r"[^0-9a-z]+", " ", str(text or "").lower()).split())


def _variants(gray):
    """Images to OCR, cheapest first: as captured, then upscaled and binarised,
    which recovers small list text that Tesseract misses at phone resolution."""
    yield 1.0, gray
    big = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    yield 2.0, binary


def _ocr_words(image, scale, offset):
    """Recognised words with boxes in screenshot coordinates."""
    data = pytesseract.image_to_data(image, config=OCR_CONFIG, output_type=pytesseract.Output.DICT)
    words = []
    for i, raw in enumerate(data["text"]):
        text = (raw or "").strip()
        try:
            confidence = float(data["conf"][i])
        except (TypeError, ValueError):
            confidence = -1
        if not text or confidence < MIN_WORD_CONFIDENCE:
            continue
        words.append({
            "text": text,
            "left": data["left"][i] / scale + offset[0],
            "top": data["top"][i] / scale + offset[1],
            "width": data["width"][i] / scale,
            "height": data["height"][i] / scale,
        })
    return words


def _group_lines(words):
    """Cluster words into visual rows, each ordered left to right, so a phrase
    split into several OCR words ("Bengal" + "Gram") can be matched as a whole."""
    rows = []
    for word in sorted(words, key=lambda w: (w["top"], w["left"])):
        centre = word["top"] + word["height"] / 2
        for row in rows:
            if abs(row["centre"] - centre) <= max(row["height"], word["height"]) * 0.6:
                row["words"].append(word)
                break
        else:
            rows.append({"centre": centre, "height": word["height"], "words": [word]})
    return [sorted(row["words"], key=lambda w: w["left"]) for row in rows]


MIN_WORD_RATIO = 0.6       # each word of a same-length phrase: tolerates "Sowmg", not "Type" for "Date"
MIN_JOINED_RATIO = 0.9     # words split or merged by OCR ("Are canut", "BengalGram")


def _phrase_score(want, got):
    """Similarity of two normalised phrases, word-aware so that labels differing
    by a whole word ("Sowing Type" vs "Sowing Date") never pass as a match."""
    ratio = lambda a, b: SequenceMatcher(None, a, b).ratio()  # noqa: E731
    joined = ratio(want.replace(" ", ""), got.replace(" ", ""))
    want_words, got_words = want.split(), got.split()
    if len(want_words) == len(got_words):
        if min(ratio(a, b) for a, b in zip(want_words, got_words)) < MIN_WORD_RATIO:
            return 0.0
        return max(ratio(want, got), joined)
    return joined if joined >= MIN_JOINED_RATIO else 0.0


def _best_match(rows, target):
    """(score, words) for the run of consecutive words that best matches `target`."""
    want = _normalize(target)
    if not want:
        return 0.0, None, ""
    size = len(want.split())
    best = (0.0, None, "")
    for words in rows:
        for length in range(max(1, size - 1), size + 2):
            for start in range(len(words) - length + 1):
                window = words[start:start + length]
                # Words far apart on one row belong to different labels.
                if any(b["left"] - (a["left"] + a["width"]) > 3 * max(a["height"], b["height"])
                       for a, b in zip(window, window[1:])):
                    continue
                got = _normalize(" ".join(w["text"] for w in window))
                if not got:
                    continue
                score = 1.0 if got == want else _phrase_score(want, got)
                if f" {want} " in f" {got} ":
                    score = max(score, 0.9)  # label with extra text, e.g. "Arecanut (Supari)"
                if score > best[0]:
                    best = (score, window, got)
    return best


def find_text_on_screen(image_path, target_text, region=None, min_ratio=MIN_MATCH_RATIO):
    """Centre (x, y) of `target_text` in a screenshot, or None.

    Matches whole phrases, case-insensitively and tolerating small OCR errors.
    `region` = (left, top, width, height) limits the search to part of the screen,
    e.g. an open dropdown, which is faster and avoids matching the page behind it.
    """
    box = find_text_box_on_screen(image_path, target_text, region=region, min_ratio=min_ratio)
    if box is None:
        return None
    return int(box["x"] + box["width"] / 2), int(box["y"] + box["height"] / 2)


def find_text_box_on_screen(image_path, target_text, region=None, min_ratio=MIN_MATCH_RATIO):
    """Bounds {x, y, width, height} of `target_text` in a screenshot, or None.
    Same matching as find_text_on_screen()."""
    image = cv2.imread(image_path)
    if image is None:
        print(f"[OCR] Could not read screenshot: {image_path}")
        return None
    offset = (0, 0)
    if region:
        left, top, width, height = (int(v) for v in region)
        image = image[max(top, 0):top + height, max(left, 0):left + width]
        offset = (max(left, 0), max(top, 0))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    for scale, variant in _variants(gray):
        rows = _group_lines(_ocr_words(variant, scale, offset))
        score, window, got = _best_match(rows, target_text)
        print(f"[OCR] pass x{scale:g}: {len(rows)} row(s), best match {got!r} ({score:.2f})")
        if window and score >= min_ratio:
            left = min(w["left"] for w in window)
            top = min(w["top"] for w in window)
            right = max(w["left"] + w["width"] for w in window)
            bottom = max(w["top"] + w["height"] for w in window)
            return {"x": int(left), "y": int(top), "width": int(right - left), "height": int(bottom - top)}
    print(f"[OCR] '{target_text}' not found in {image_path}")
    return None


def click_element_by_ocr_text(driver, target_text, screenshot_path, region=None):
    print(f"[OCR] Looking for '{target_text}' in screenshot: {screenshot_path}")
    point = find_text_on_screen(screenshot_path, target_text, region=region)
    if not point:
        print(f"[OCR] No match found for '{target_text}'")
        return False
    x, y = point
    print(f"[OCR] Match found! Tapping at ({x}, {y})")
    driver.tap([(x, y)], 100)  # duration=100ms
    return True


def extract_text_from_image(image_path):
    img = Image.open(image_path)
    return pytesseract.image_to_string(img)
