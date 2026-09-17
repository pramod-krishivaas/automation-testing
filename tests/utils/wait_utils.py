import os
import time
import allure
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from appium.webdriver.common.appiumby import AppiumBy
from utils.ocr_utils import click_element_by_ocr_text
from selenium.common.exceptions import NoSuchElementException
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.common.actions.action_builder import ActionBuilder
import sys
from selenium.webdriver.common.by import By

sys.dont_write_bytecode = True

# Default for the dynamic waits below: long enough for a slow screen to render,
# short enough that a genuinely missing element doesn't stall the run.
DEFAULT_WAIT_TIMEOUT = 30


def _console_log(msg: str) -> None:
    # flush=True is important when output is piped (subprocess -> backend -> UI)
    print(msg, flush=True)


def _auto_ui_shot(driver, label: str) -> None:
    """
    Optional automatic screenshot capture.
    Enable with: AUTO_UI_SHOTS=1
    Uses driver.ui_shot(label) if present (bound in conftest.py).
    """
    if os.getenv("AUTO_UI_SHOTS") != "1":
        return
    fn = getattr(driver, "ui_shot", None)
    if callable(fn):
        try:
            fn(label)
        except Exception:
            # Never break test flow because screenshots failed
            pass


def find_and_click(driver, by, value, fallback_text=None, timeout=20):
    """
    Tries to find and click an element by its primary locator.
    If that fails and a fallback_text is provided, it tries to click by text.

    Args:
        driver: The Appium driver instance.
        by: The locator strategy (e.g., AppiumBy.XPATH).
        value: The locator string (e.g., "//your/xpath").
        fallback_text: The visible text to use as a fallback locator.
        timeout: The maximum time to wait for the element.

    Returns:
        True if the element was clicked successfully, False otherwise.
    """
    try:
        # 1. Try to click using the primary locator (e.g., XPath)
        print(f"Attempting to click element with locator: {by}='{value}'")
        element = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((by, value))
        )
        element.click()
        print("Click successful using primary locator.")
        return True
    except TimeoutException:
        print(f"Primary locator failed. Trying fallback text: '{fallback_text}'")

        # 2. If primary locator fails, try the fallback text
        if fallback_text:
            try:
                # Construct a generic XPath to find any element containing the text
                fallback_xpath = f"//*[contains(@text, '{fallback_text}')]"
                print(
                    f"Attempting to click element with fallback locator: xpath='{fallback_xpath}'"
                )

                element = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, fallback_xpath))
                )
                element.click()
                print("Click successful using fallback text.")
                return True
            except TimeoutException:
                print(f"Fallback text '{fallback_text}' also failed.")
                return False

    return False


# def smart_find_element(driver, name, xpath, fallback_text=None, screenshot_path="screenshots/ocr_fallback.png"):
#     """
#     Find element with OCR fallback.
#     Returns tuple: (element, was_found_by_ocr)
#     """
#     try:
#         # Try finding by XPath first
#         element = WebDriverWait(driver, 10).until(
#             EC.presence_of_element_located((By.XPATH, xpath))
#         )
#         return element, False
#     except:
#         print(f"Element '{name}' not found via XPath. Trying OCR fallback...")

#         # Take screenshot
#         driver.save_screenshot(screenshot_path)

#         # Try clicking by text via OCR
#         if fallback_text:
#             found = click_element_by_ocr_text(driver, fallback_text, screenshot_path)
#             if found:
#                 print(f"OCR clicked on '{fallback_text}' successfully.")
#                 return None, True  # Indicate OCR was used
#             else:
#                 print(f"OCR failed to find '{fallback_text}' on screen.")

#         return None, False


def _xpath_literal(s: str) -> str:
    """Return an XPath string literal that safely handles quotes."""
    if s is None:
        return "''"
    if "'" not in s:
        return f"'{s}'"
    # concat('foo', "'", 'bar')
    parts = s.split("'")
    return "concat(" + ', "\'", '.join([f"'{p}'" for p in parts]) + ")"


def _swipe_vertical_w3c(
    driver, start_y_ratio=0.8, end_y_ratio=0.2, x_ratio=0.5, pause_s=0.05
):
    """Reliable vertical swipe using W3C actions (works in parallel / modern Appium)."""
    size = driver.get_window_size()
    start_x = int(size["width"] * x_ratio)
    start_y = int(size["height"] * start_y_ratio)
    end_y = int(size["height"] * end_y_ratio)

    actions = ActionBuilder(driver)
    finger = actions.pointer_action
    finger.move_to_location(start_x, start_y)
    finger.pointer_down()
    finger.pause(pause_s)
    finger.move_to_location(start_x, end_y)
    finger.pointer_up()
    actions.perform()


def _escape_uiautomator_text(s: str) -> str:
    """Escape for embedding inside UiAutomator Java string literals."""
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


# def _android_scroll_into_view(driver, text: str):

# def _xpath_literal(s: str) -> str:
#     """Return an XPath string literal that safely handles quotes."""
#     if s is None:
#         return "''"
#     if "'" not in s:
#         return f"'{s}'"
#     # concat('foo', "'", 'bar')
#     parts = s.split("'")
#     return "concat(" + ", \"'\", ".join([f"'{p}'" for p in parts]) + ")"


def _swipe_vertical_w3c(
    driver, start_y_ratio=0.8, end_y_ratio=0.2, x_ratio=0.5, pause_s=0.05
):
    """Reliable vertical swipe using W3C actions (works in parallel / modern Appium)."""
    size = driver.get_window_size()
    start_x = int(size["width"] * x_ratio)
    start_y = int(size["height"] * start_y_ratio)
    end_y = int(size["height"] * end_y_ratio)

    actions = ActionBuilder(driver)
    finger = actions.pointer_action
    finger.move_to_location(start_x, start_y)
    finger.pointer_down()
    finger.pause(pause_s)
    finger.move_to_location(start_x, end_y)
    finger.pointer_up()
    actions.perform()


def _escape_uiautomator_text(s: str) -> str:
    """Escape for embedding inside UiAutomator Java string literals."""
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def _android_scroll_into_view(driver, text: str):
    """
    Uses Android UiScrollable to scroll a scrollable container until an item
    with matching text/description is in view. Returns WebElement or None.
    """
    t = _escape_uiautomator_text(text)

    # Try textContains first
    ua_text = (
        "new UiScrollable(new UiSelector().scrollable(true))"
        f'.scrollIntoView(new UiSelector().textContains("{t}"));'
    )
    try:
        el = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, ua_text)
        if el:
            return el
    except Exception:
        pass

    # Then descriptionContains (content-desc)
    ua_desc = (
        "new UiScrollable(new UiSelector().scrollable(true))"
        f'.scrollIntoView(new UiSelector().descriptionContains("{t}"));'
    )
    try:
        el = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, ua_desc)
        if el:
            return el
    except Exception:
        pass

    return None


def _ocr_screenshot_path(driver, name: str, attempt: int) -> str:
    """
    Prefer saving OCR screenshots into the same per-test ui_screenshots folder.
    Falls back to local screenshots/ if driver.ui_shot_path is not available.
    """
    fn = getattr(driver, "ui_shot_path", None)
    if callable(fn):
        return fn(f"ocr__{name}__attempt_{attempt}")
    return "screenshots/ocr_fallback.png"


def smart_find_element(
    driver,
    name,
    xpath,
    fallback_text=None,
    screenshot_path="screenshots/ocr_fallback.png",
    max_swipes=6,
    per_try_wait_s=1.5,
    stop_if_no_change=True,
    *,
    force_ocr: bool = False,
    enable_scroll: bool = True,
    enable_dom_fallback: bool = True,
    ocr_attempts: int = 2,
    ocr_wait_s: float = 0.7,
    timeout: float = DEFAULT_WAIT_TIMEOUT,
):
    """
    Find element with optional OCR-first mode.

    If force_ocr=True:
      - try primary xpath once
      - then do OCR click attempts (no UiScrollable, no DOM/scroll loop)
    """
    # 1) Primary XPath Strategy (always try) — dynamic wait: returns the moment
    # the element is visible, instead of blocking for a flat timeout either way.
    element = wait_until_displayed(driver, xpath, timeout=timeout)
    if element:
        _console_log(f"[FOUND] name='{name}' via XPATH")
        return element, False
    print(f"[{name}] Not found via Primary XPath (waited {timeout}s).")

    if not xpath:
       raise ValueError(f"XPath is empty for element: {name}")

    # If user explicitly wants OCR, skip scroll/DOM strategies.
    if force_ocr:
        enable_scroll = False
        enable_dom_fallback = False

    # 2) Secondary Strategy (Android): UiScrollable (only if enabled)
    if fallback_text and enable_scroll:
        print(
            f"   -> Attempting Android UiScrollable scrollIntoView for {fallback_text!r}..."
        )
        el = _android_scroll_into_view(driver, fallback_text)
        if el:
            print(f"   -> Found {fallback_text!r} via UiScrollable! Skipping OCR.")
            return el, False

    # 3) Secondary Strategy: DOM Text Search (only if enabled)
    if fallback_text and enable_dom_fallback:
        literal = _xpath_literal(fallback_text)
        text_xpath = (
            f"//*[contains(@text, {literal}) or contains(@content-desc, {literal})]"
        )
        print(f"   -> Attempting DOM fallback for text {fallback_text!r}...")

        last_source = None
        for i in range(max_swipes + 1):
            try:
                element = WebDriverWait(driver, per_try_wait_s).until(
                    EC.presence_of_element_located((AppiumBy.XPATH, text_xpath))
                )
                print(f"   -> Found {fallback_text!r} via DOM search! Skipping OCR.")
                return element, False
            except TimeoutException:
                if not enable_scroll or i >= max_swipes:
                    break

                if stop_if_no_change:
                    try:
                        source = driver.page_source
                        if last_source is not None and source == last_source:
                            print(
                                "   -> Page source did not change after swipe; stopping DOM scroll search."
                            )
                            break
                        last_source = source
                    except Exception:
                        pass

                print(
                    f"   -> Not visible yet (attempt {i + 1}/{max_swipes}). Scrolling down..."
                )
                _swipe_vertical_w3c(driver)

    # 4) OCR Strategy (Last Resort or Forced)
    if fallback_text:
        print("   -> Initiating OCR fallback (this may take time)...")

        for attempt in range(1, max(1, int(ocr_attempts)) + 1):
            # IMPORTANT: put OCR screenshot into the same per-test folder (when available)
            shot_path = _ocr_screenshot_path(driver, name, attempt)

            try:
                os.makedirs(os.path.dirname(shot_path) or ".", exist_ok=True)
            except Exception:
                pass

            try:
                # Use Appium-native screenshot to file
                driver.get_screenshot_as_file(shot_path)
            except Exception:
                try:
                    driver.save_screenshot(shot_path)
                except Exception:
                    pass

            found = click_element_by_ocr_text(driver, fallback_text, shot_path)
            if found:
                print(f"OCR clicked on '{fallback_text}' successfully.")
                return None, True

            print(
                f"OCR did not find '{fallback_text}' (attempt {attempt}/{ocr_attempts})."
            )
            time.sleep(ocr_wait_s)

    return None, False

def wait_for_loader_to_disappear(driver, timeout=60):
    """
    Wait until loader/spinner disappears.
    Handles multiple possible loaders.
    """

    loader_xpaths = [
        "//*[contains(@resource-id,'progress')]",
        "//*[contains(@resource-id,'loader')]",
        "//*[contains(@resource-id,'loading')]",
        "//*[contains(@class,'ProgressBar')]",
        "//*[contains(@text,'Loading')]",
        "//*[contains(@text,'Please wait')]",
        "//*[contains(@content-desc,'Loading')]",
    ]

    print("[INFO] Waiting for loader to disappear...")

    start_time = time.time()

    while time.time() - start_time < timeout:
        loader_found = False

        for xpath in loader_xpaths:
            try:
                elements = driver.find_elements(AppiumBy.XPATH, xpath)

                visible_elements = [e for e in elements if e.is_displayed()]

                if visible_elements:
                    loader_found = True
                    print(f"[INFO] Loader still visible: {xpath}")
                    break

            except Exception:
                pass

        if not loader_found:
            print("[INFO] Loader disappeared")
            return True

        time.sleep(2)

    print("[WARNING] Loader wait timeout reached")
    return False

def smart_click(
    driver,
    name,
    xpath,
    fallback_text=None,
    screenshot_path="screenshots/ocr_fallback.png",
    *,
    force_ocr: bool = False,
    enable_scroll: bool = True,
    enable_dom_fallback: bool = True,
    ocr_attempts: int = 2,
    timeout: float = DEFAULT_WAIT_TIMEOUT,
):
    """
    Wrapper around smart_find_element to perform a click.
    AUTO screenshots:
      - before click attempt
      - after success
      - after failure
    """
    _auto_ui_shot(driver, f"before__click__{name}")

    element, used_ocr = smart_find_element(
        driver,
        name,
        xpath,
        fallback_text=fallback_text,
        screenshot_path=screenshot_path,
        force_ocr=force_ocr,
        enable_scroll=enable_scroll,
        enable_dom_fallback=enable_dom_fallback,
        ocr_attempts=ocr_attempts,
        timeout=timeout,
    )

    if element:
        try:
            element.click()
            _auto_ui_shot(driver, f"after__click__{name}__ok")
            return True
        except Exception as e:
            print(f"Failed to click element '{name}': {e}")
            _auto_ui_shot(driver, f"after__click__{name}__exc")
            return False

    # If OCR clicked successfully, treat as success and still capture an "after"
    if used_ocr:
        _auto_ui_shot(driver, f"after__click__{name}__ocr_ok")
        return True

    _auto_ui_shot(driver, f"after__click__{name}__not_found")
    return False


def scroll_and_click_by_text_robust(driver, text_to_find, max_swipes=5):
    """
    Scrolls down to find an element with specific text, then attempts to click it.
    If the element itself isn't clickable, it tries to click its clickable parent.
    """
    for _ in range(max_swipes):
        try:
            # First, find the element by its text
            element_xpath = f"//*[contains(@text, '{text_to_find}')]"
            text_element = driver.find_element(AppiumBy.XPATH, element_xpath)

            # --- THE CRITICAL LOGIC ---
            # Check if the element itself is clickable. If not, find its ancestor.
            if text_element.get_attribute("clickable") == "true":
                print(
                    f"Text element '{text_to_find}' is directly clickable. Clicking it."
                )
                text_element.click()
                return True
            else:
                print(
                    f"Element with text '{text_to_find}' is not clickable. Searching for a clickable parent..."
                )
                # This XPath finds the first ancestor of the text element that IS clickable.
                parent_xpath = f"({element_xpath})/ancestor::*[@clickable='true']"
                clickable_parent = driver.find_element(AppiumBy.XPATH, parent_xpath)

                print("Found a clickable parent. Clicking it.")
                clickable_parent.click()
                return True

        except NoSuchElementException:
            # If the element isn't on screen, scroll down
            print(f"'{text_to_find}' not found, scrolling...")
            size = driver.get_window_size()
            start_x = size["width"] / 2
            start_y = size["height"] * 0.8
            end_y = size["height"] * 0.2
            driver.swipe(start_x, start_y, start_x, end_y, 400)

    print(f"Failed to find or click '{text_to_find}' after {max_swipes} swipes.")
    return False


def scroll_and_tap_by_text(driver, text_to_find, max_swipes=5):
    """
    Scrolls down to find an element by its text and performs a coordinate-based tap
    on its center. This version uses the W3C Actions API, making it compatible with
    the latest Appium Python Client and robust for parallel testing.

    Args:
        driver: The Appium driver instance.
        text_to_find: The visible text of the element to tap.
        max_swipes: The maximum number of swipes to prevent an infinite loop.

    Returns:
        True if the element was found and tapped, False otherwise.
    """
    for i in range(max_swipes):
        try:
            # 1. Use the universal XPath to find the element (this part is correct)
            universal_xpath = f"//*[contains(@text, '{text_to_find}') or contains(@content-desc, '{text_to_find}')]"
            element = driver.find_element(AppiumBy.XPATH, universal_xpath)

            # 2. Dynamically get the element's location (this part is correct)
            location = element.location
            size = element.size
            center_x = location["x"] + size["width"] / 2
            center_y = location["y"] + size["height"] / 2

            print(
                f"Found '{text_to_find}'. Tapping at dynamic coordinates: ({center_x}, {center_y})"
            )
            allure.attach(
                f"Tapping '{text_to_find}' on {driver.capabilities.get('deviceName')} at ({center_x}, {center_y})",
                name="Dynamic Coordinate Tap",
                attachment_type=allure.attachment_type.TEXT,
            )

            # --- REPLACEMENT for TouchAction ---
            # 3. Perform the raw tap action using W3C Actions
            actions = ActionBuilder(driver)
            finger = actions.pointer_action
            finger.move_to_location(center_x, center_y)
            finger.pointer_down()
            finger.pause(0.1)  # A brief pause improves tap reliability
            finger.pointer_up()
            actions.perform()
            # --- END REPLACEMENT ---

            return True

        except NoSuchElementException:
            # 4. If not found, scroll down and try again
            if i < max_swipes - 1:
                print(f"'{text_to_find}' not found, scrolling down...")
                screen_size = driver.get_window_size()
                start_x = screen_size["width"] / 2
                start_y = screen_size["height"] * 0.8
                end_y = screen_size["height"] * 0.2

                # --- REPLACEMENT for driver.swipe() ---
                # 5. Perform the swipe using W3C Actions
                actions = ActionBuilder(driver)
                finger = actions.pointer_action
                finger.move_to_location(start_x, start_y)
                finger.pointer_down()
                finger.move_to_location(start_x, end_y)
                finger.pointer_up()
                actions.perform()
                # --- END REPLACEMENT ---

            else:
                # This is the last swipe attempt, and it still wasn't found.
                print(
                    f"Could not find element '{text_to_find}' after {max_swipes} swipes."
                )
                return False

    return False

def scroll_and_click_card_icon(
    driver,
    card_text,
    icon_xpath,
    max_swipes=8,
    swipe_duration=400
):
    """Scrolls until card_text is visible, then clicks the icon inside that card."""
    t = _escape_uiautomator_text(card_text)
    ua = (
        'new UiScrollable(new UiSelector().scrollable(true))'
        f'.scrollIntoView(new UiSelector().textContains("{t}"));'
    )
    try:
        driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, ua)
        print(f"[INFO] UiScrollable scrolled '{card_text}' into view.")
        time.sleep(1)
    except Exception:
        print(f"[INFO] UiScrollable could not reach '{card_text}', falling back to manual swipes.")

    for swipe in range(max_swipes):
        try:
            card_xpath = f"//*[contains(@text,'{card_text}')]"
            card_element = driver.find_element(AppiumBy.XPATH, card_xpath)

            # Strategy A: global XPath
            try:
                icon_element = driver.find_element(AppiumBy.XPATH, icon_xpath)
                if not icon_element.is_displayed():
                    try:
                        driver.execute_script(
                            "mobile: scrollGesture",
                            {"elementId": icon_element.id, "direction": "down", "percent": 0.3}
                        )
                        time.sleep(1)
                    except Exception:
                        pass
                try:
                    icon_element.click()
                except Exception:
                    loc = icon_element.location
                    sz = icon_element.size
                    x = loc["x"] + sz["width"] // 2
                    y = loc["y"] + sz["height"] // 2
                    actions = ActionBuilder(driver)
                    f = actions.pointer_action
                    f.move_to_location(x, y); f.pointer_down(); f.pause(0.1); f.pointer_up()
                    actions.perform()
                return True
            except NoSuchElementException:
                pass

            # Strategy B: relative to card ancestor
            for level in [2, 3, 4]:
                try:
                    container = driver.find_element(
                        AppiumBy.XPATH,
                        f"({card_xpath})/ancestor::android.view.ViewGroup[{level}]"
                    )
                    icon_el = container.find_element(AppiumBy.XPATH, icon_xpath)
                    try:
                        icon_el.click()
                    except Exception:
                        loc = icon_el.location
                        sz = icon_el.size
                        x = loc["x"] + sz["width"] // 2
                        y = loc["y"] + sz["height"] // 2
                        actions = ActionBuilder(driver)
                        f = actions.pointer_action
                        f.move_to_location(x, y); f.pointer_down(); f.pause(0.1); f.pointer_up()
                        actions.perform()
                    return True
                except Exception:
                    continue

        except NoSuchElementException:
            print(f"[INFO] Card '{card_text}' not on screen yet, swiping...")
        except Exception as e:
            print(f"[WARNING] Unexpected error: {e}")

        size = driver.get_window_size()
        driver.swipe(size["width"]//2, int(size["height"]*0.8),
                     size["width"]//2, int(size["height"]*0.3), swipe_duration)
        time.sleep(2)

    print(f"[ERROR] Failed to find/click icon for '{card_text}' after {max_swipes} attempts.")
    return False

def scroll_to_card_and_click_icon(
    driver,
    card_title_text: str,
    icon_xpath: str,
    name: str,
    max_swipes: int = 15,
    nudge_steps: int = 8,
    y_tolerance: int = 80,
):
    """
    Scrolls so that `card_title_text` is near the TOP of the screen
    (ensuring the full card body and its icons are visible), then
    clicks the icon matching `icon_xpath` that is spatially INSIDE
    that card (Y position >= card title Y).
 
    Args:
        driver           : Appium driver.
        card_title_text  : Visible text of the card header, e.g. "Soil Moisture".
        icon_xpath       : XPath for the icon (may be shared across all cards).
        name             : Human-readable label for logs / error messages.
        max_swipes       : Max swipes when the card title isn't found at all.
        nudge_steps      : Small additional swipes after positioning the card.
        y_tolerance      : Allow icon to be up to this many px above card title.
    """
    from selenium.webdriver.common.actions.action_builder import ActionBuilder
    from appium.webdriver.common.appiumby import AppiumBy
    import time
 
    t = _escape_uiautomator_text(card_title_text)
    size     = driver.get_window_size()
    screen_h = size["height"]
    screen_w = size["width"]
 
    # ── Helpers ──────────────────────────────────────────────────────────
 
    def _get_title_el():
        try:
            return driver.find_element(
                AppiumBy.ANDROID_UIAUTOMATOR,
                f'new UiSelector().textContains("{t}")'
            )
        except Exception:
            return None
 
    def _precise_swipe(from_y: int, to_y: int, duration_ms: int = 400):
        """Swipe vertically by exact pixel amounts."""
        from_y = max(10, min(screen_h - 10, from_y))
        to_y   = max(10, min(screen_h - 10, to_y))
        actions = ActionBuilder(driver)
        f = actions.pointer_action
        f.move_to_location(screen_w // 2, from_y)
        f.pointer_down()
        f.pause(duration_ms / 1000)
        f.move_to_location(screen_w // 2, to_y)
        f.pointer_up()
        actions.perform()
 
    def _tap(el) -> bool:
        try:
            el.click()
            return True
        except Exception:
            try:
                loc = el.location
                sz  = el.size
                cx  = loc["x"] + sz["width"]  // 2
                cy  = loc["y"] + sz["height"] // 2
                ab  = ActionBuilder(driver)
                f   = ab.pointer_action
                f.move_to_location(cx, cy)
                f.pointer_down()
                f.pause(0.1)
                f.pointer_up()
                ab.perform()
                return True
            except Exception as e:
                print(f"[WARNING] Tap failed for '{name}': {e}")
                return False
 
    # ── Step 1: UiScrollable — get card title SOMEWHERE on screen ────────
    ua = (
        'new UiScrollable(new UiSelector().scrollable(true))'
        f'.scrollIntoView(new UiSelector().textContains("{t}"));'
    )
    try:
        driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, ua)
        print(f"[INFO] UiScrollable found '{card_title_text}'.")
        time.sleep(1)
    except Exception:
        print(f"[INFO] UiScrollable could not find '{card_title_text}'. Trying manual scroll.")
        # Manual fallback scroll
        last_src = None
        for _ in range(max_swipes):
            if _get_title_el():
                break
            src = driver.page_source
            if src == last_src:
                break
            last_src = src
            _precise_swipe(int(screen_h * 0.75), int(screen_h * 0.30))
            time.sleep(0.8)
 
    # ── Step 2: Push card title to top 15% of screen ─────────────────────
    # KEY FIX: UiScrollable may leave the title at the bottom of the screen.
    # We must push it to the top so the CARD BODY (with icons) is visible.
    TARGET_Y = int(screen_h * 0.15)  # where we want the card title to sit
 
    for attempt in range(4):
        title_el = _get_title_el()
        if not title_el:
            print(f"[WARN] Could not find '{card_title_text}' title at positioning attempt {attempt}.")
            break
 
        card_y = title_el.location["y"]
        print(f"[INFO] '{card_title_text}' title at Y={card_y} (target={TARGET_Y})")
 
        if card_y <= TARGET_Y + 60:
            # Already near top — card body should be visible
            print(f"[INFO] Card title near top. Card body should be visible.")
            break
 
        # Scroll UP by exactly (card_y - TARGET_Y) pixels
        scroll_px   = card_y - TARGET_Y
        swipe_from  = min(int(screen_h * 0.80), card_y + 80)
        swipe_to    = max(30, swipe_from - scroll_px)
 
        print(f"[INFO] Scrolling up {scroll_px}px to push card title to top.")
        _precise_swipe(swipe_from, swipe_to)
        time.sleep(1)
 
    # ── Step 3: Nudge loop — find icon with Y-position filter ────────────
    for nudge in range(nudge_steps + 1):
        title_el = _get_title_el()
 
        if title_el:
            card_y = title_el.location["y"]
 
            try:
                candidates = driver.find_elements(AppiumBy.XPATH, icon_xpath)
                valid = []
 
                for el in candidates:
                    try:
                        el_loc = el.location
                        el_sz  = el.size
                        el_y   = el_loc["y"]
                        # Must be: below card title, displayed, has size, within screen
                        if (el_y >= (card_y - y_tolerance)
                                and el.is_displayed()
                                and el_sz["width"] > 0
                                and el_sz["height"] > 0
                                and 0 < el_y < screen_h):
                            valid.append(el)
                    except Exception:
                        continue
 
                if valid:
                    valid.sort(key=lambda e: e.location["y"])
                    target = valid[0]
                    print(
                        f"[FOUND] '{name}' at Y={target.location['y']} "
                        f"(card title Y={card_y}, nudge={nudge})"
                    )
                    if _tap(target):
                        print(f"[CLICKED] '{name}' successfully.")
                        return True
                else:
                    # Debug: print all candidates so we know why they were filtered
                    print(
                        f"[INFO] Card '{card_title_text}' at Y={card_y}. "
                        f"{len(candidates)} xpath match(es), none valid "
                        f"(need Y>={card_y - y_tolerance}, on-screen). "
                        f"Nudge {nudge}/{nudge_steps}."
                    )
                    for i, el in enumerate(candidates):
                        try:
                            print(
                                f"       [candidate {i}] Y={el.location['y']}, "
                                f"displayed={el.is_displayed()}, size={el.size}"
                            )
                        except Exception:
                            print(f"       [candidate {i}] Could not read location/size.")
 
            except Exception as e:
                print(f"[INFO] Icon search error at nudge {nudge}: {e}")
 
        else:
            # Title scrolled off screen — re-anchor
            print(f"[WARN] '{card_title_text}' title lost at nudge {nudge}. Re-scrolling…")
            try:
                driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, ua)
                time.sleep(1)
                # Re-position to top
                title_el = _get_title_el()
                if title_el and title_el.location["y"] > TARGET_Y + 60:
                    card_y_now = title_el.location["y"]
                    _precise_swipe(
                        min(int(screen_h * 0.8), card_y_now + 80),
                        max(30, min(int(screen_h * 0.8), card_y_now + 80) - (card_y_now - TARGET_Y))
                    )
                    time.sleep(0.8)
            except Exception:
                pass
 
        if nudge < nudge_steps:
            # Small nudge to reveal icons that might be just below viewport
            _precise_swipe(int(screen_h * 0.60), int(screen_h * 0.47))
            time.sleep(0.8)
 
    print(f"[ERROR] Failed to click '{name}' after {nudge_steps} nudges.")
    return False

def scroll_to_card_and_click_icon(
    driver,
    card_title_text,
    icon_xpath,
    name="Card Icon",
    max_swipes=15,
):
    """
    Scrolls until a specific card title is visible,
    then clicks the icon INSIDE that card.

    Prevents wrong icon clicks from other cards.
    """

    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from appium.webdriver.common.appiumby import AppiumBy

    for swipe in range(max_swipes):

        try:

            # Find card title first
            card_xpath = (
                f"//*[contains(@text,'{card_title_text}') "
                f"or contains(@content-desc,'{card_title_text}')]"
            )

            card_element = WebDriverWait(driver, 2).until(
                EC.presence_of_element_located(
                    (AppiumBy.XPATH, card_xpath)
                )
            )

            print(f"[FOUND] Card '{card_title_text}' visible.")

            # Find icon relative to card
            parent = card_element.find_element(
                AppiumBy.XPATH,
                "./ancestor::android.view.ViewGroup[1]"
            )

            icon_element = parent.find_element(
                AppiumBy.XPATH,
                icon_xpath
            )

            # Ensure visible
            if icon_element.is_displayed():

                try:
                    icon_element.click()

                except Exception:

                    # W3C fallback tap
                    loc = icon_element.location
                    size = icon_element.size

                    center_x = loc["x"] + size["width"] // 2
                    center_y = loc["y"] + size["height"] // 2

                    actions = ActionBuilder(driver)

                    finger = actions.pointer_action

                    finger.move_to_location(center_x, center_y)

                    finger.pointer_down()

                    finger.pause(0.1)

                    finger.pointer_up()

                    actions.perform()

                print(f"[CLICKED] {name}")

                return True

        except Exception as e:

            print(
                f"[INFO] '{card_title_text}' not found yet "
                f"(attempt {swipe + 1}/{max_swipes})"
            )

        # Swipe
        try:

            _swipe_vertical_w3c(
                driver,
                start_y_ratio=0.8,
                end_y_ratio=0.3,
            )

        except Exception:

            size = driver.get_window_size()

            driver.swipe(
                size["width"] // 2,
                int(size["height"] * 0.8),
                size["width"] // 2,
                int(size["height"] * 0.3),
                500
            )

        time.sleep(1)

    print(f"[ERROR] Failed to click {name}")

    return False

def scroll_up_and_tap_by_text(driver, text_to_find, max_swipes=5):

    for i in range(max_swipes):

        try:
            universal_xpath = (
                f"//*[contains(@text, '{text_to_find}') "
                f"or contains(@content-desc, '{text_to_find}')]"
            )

            element = driver.find_element(
                AppiumBy.XPATH,
                universal_xpath
            )
            location = element.location
            size = element.size

            center_x = location['x'] + size['width'] / 2
            center_y = location['y'] + size['height'] / 2

            print(
                f"Found '{text_to_find}'. "
                f"Tapping at ({center_x}, {center_y})"
            )

            allure.attach(
                f"Tapping '{text_to_find}' "
                f"at ({center_x}, {center_y})",
                name="Dynamic Coordinate Tap",
                attachment_type=allure.attachment_type.TEXT
            )

            # ---------------------------------------------------------
            # 3. Tap element using W3C actions
            # ---------------------------------------------------------
            actions = ActionBuilder(driver)
            finger = actions.pointer_action

            finger.move_to_location(center_x, center_y)
            finger.pointer_down()
            finger.pause(0.1)
            finger.pointer_up()

            actions.perform()

            return True

        except NoSuchElementException:

            if i < max_swipes - 1:

                print(
                    f"'{text_to_find}' not found, "
                    f"scrolling UP..."
                )

                screen_size = driver.get_window_size()

                start_x = screen_size['width'] / 2

                # Finger starts upper-middle
                start_y = screen_size['height'] * 0.55

                # Finger moves downward
                end_y = screen_size['height'] * 0.85

                actions = ActionBuilder(driver)
                finger = actions.pointer_action

                finger.move_to_location(start_x, start_y)
                finger.pointer_down()
                finger.pause(0.5)

                finger.move_to_location(start_x, end_y)
                finger.pause(0.5)

                finger.pointer_up()

                actions.perform()

                time.sleep(2)

            else:
                print(
                    f"Could not find element "
                    f"'{text_to_find}' after {max_swipes} swipes."
                )

                return False

    return False

def scroll_and_tap_by_text(driver, text_to_find, max_swipes=5):

    for i in range(max_swipes):
        try:
            # 1. Use the universal XPath to find the element (this part is correct)
            universal_xpath = f"//*[contains(@text, '{text_to_find}') or contains(@content-desc, '{text_to_find}')]"
            element = driver.find_element(AppiumBy.XPATH, universal_xpath)

            # 2. Dynamically get the element's location (this part is correct)
            location = element.location
            size = element.size
            center_x = location["x"] + size["width"] / 2
            center_y = location["y"] + size["height"] / 2

            print(
                f"Found '{text_to_find}'. Tapping at dynamic coordinates: ({center_x}, {center_y})"
            )
            allure.attach(
                f"Tapping '{text_to_find}' on {driver.capabilities.get('deviceName')} at ({center_x}, {center_y})",
                name="Dynamic Coordinate Tap",
                attachment_type=allure.attachment_type.TEXT,
            )

            # --- REPLACEMENT for TouchAction ---
            # 3. Perform the raw tap action using W3C Actions
            actions = ActionBuilder(driver)
            finger = actions.pointer_action
            finger.move_to_location(center_x, center_y)
            finger.pointer_down()
            finger.pause(0.1)  # A brief pause improves tap reliability
            finger.pointer_up()
            actions.perform()
            # --- END REPLACEMENT ---

            return True

        except NoSuchElementException:
            # 4. If not found, scroll down and try again
            if i < max_swipes - 1:
                print(f"'{text_to_find}' not found, scrolling down...")
                screen_size = driver.get_window_size()
                start_x = screen_size["width"] / 2
                start_y = screen_size["height"] * 0.8
                end_y = screen_size["height"] * 0.2

                # --- REPLACEMENT for driver.swipe() ---
                actions = ActionBuilder(driver)
                finger = actions.pointer_action
                
                finger.move_to_location(start_x, start_y)
                finger.pointer_down()
                finger.pause(0.5)
                
                finger.move_to_location(start_x, end_y)
                finger.pause(0.5)
                
                finger.pointer_up()
                
                actions.perform()
                
            else:
                # This is the last swipe attempt, and it still wasn't found.
                print(
                    f"Could not find element '{text_to_find}' after {max_swipes} swipes."
                )
                return False

    return False

def wait_for_otp(fetch_otp_func, timeout=30, poll_interval=2):
    """
    Waits dynamically for OTP using polling.

    fetch_otp_func → function that returns OTP or None
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        otp = fetch_otp_func()
        if otp:
            return otp
        time.sleep(poll_interval)

    raise TimeoutError("OTP not received within timeout")


def wait_for_element(driver, xpath, timeout=20):
    return WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((By.XPATH, xpath))
    )


def wait_and_click(driver, xpath, timeout=20):
    element = wait_for_element(driver, xpath, timeout)
    element.click()
    return True


def wait_for_first_displayed(driver, xpaths, timeout=DEFAULT_WAIT_TIMEOUT,
                             poll_interval=0.5, require_visible=True):
    """Wait for whichever of several locators appears first.

    `xpaths` is {name: xpath} or a list of xpaths; blank entries are skipped.
    Returns (name, element) — the list index as the name for a list — or
    (None, None) if none appeared within `timeout`.

    Every locator is probed on each sweep instead of each getting its own
    timeout, so one slow locator can't eat the whole budget and the first
    element to render wins. Ties go to the earlier entry, which is how callers
    express priority.
    """
    items = list(xpaths.items()) if isinstance(xpaths, dict) else list(enumerate(xpaths))
    deadline = time.time() + timeout
    while True:
        for name, xpath in items:
            if not xpath:
                continue
            try:
                for element in driver.find_elements(AppiumBy.XPATH, xpath):
                    if not require_visible or element.is_displayed():
                        return name, element
            except Exception:
                continue  # transient (stale element, screen mid-render): retry next sweep
        if time.time() >= deadline:
            return None, None
        time.sleep(poll_interval)


def wait_until_displayed(driver, xpath, timeout=DEFAULT_WAIT_TIMEOUT,
                         poll_interval=0.5, require_visible=True):
    """Poll until `xpath` is on screen; return the element, or None if it never appears.

    Unlike wait_for_element(), this returns None instead of raising, for callers
    that treat "not there" as an outcome rather than a failure.
    """
    _, element = wait_for_first_displayed(
        driver, [xpath], timeout=timeout, poll_interval=poll_interval, require_visible=require_visible
    )
    return element


def wait_for_otp_filled(driver, otp_xpath, expected_length=6, timeout=30):
    def otp_ready(driver):
        elements = driver.find_elements(By.XPATH, otp_xpath)

        if not elements:
            return False

        otp = ""
        for el in elements:
            value = el.get_attribute("text") or el.get_attribute("content-desc") or ""
            otp += value.strip()

        return len(otp) == expected_length

    return WebDriverWait(driver, timeout).until(otp_ready)

    ######################## Scroller func ######################


def scroll_until_element_visible(driver, xpath, max_scrolls=4):
    for attempt in range(max_scrolls):
        try:
            element = driver.find_element(AppiumBy.XPATH, xpath)
            if element.is_displayed():
                return element  # ✅ Return the element to the caller
        except Exception:
            pass  # Element not in DOM yet, keep scrolling

        # Scroll up (swipe from bottom to top)
        size = driver.get_window_size()
        driver.swipe(
            start_x=size["width"] / 2,
            start_y=size["height"] * 0.8,
            end_x=size["width"] / 2,
            end_y=size["height"] * 0.2,
            duration=500
        )

    return None  # ✅ Explicit None so caller's `if not` check works

def scroll_to_card_icons_and_click(
    driver,
    card_title_text: str,
    icon_xpath: str,
    next_card_title_text: str | None = None,
    name: str = "icon",
    max_swipes: int = 25,       # raised from default 10–12
    nudge_px: int = 180,        # raised from ~100
) -> bool:
 
    size     = driver.get_window_size()
    screen_w = size["width"]
    screen_h = size["height"]
 
    # ── Centre column is the safest scrollable zone ───────────────────────
    SWIPE_X = int(screen_w * 0.50)   # FIX #1 — was 0.15
 
    # ── helpers ──────────────────────────────────────────────────────────────
    def _find_text(text: str):
        """Return first displayed element whose text matches, or None."""
        for by, expr in [
            (AppiumBy.XPATH, f'//*[@text="{text}"]'),
            (AppiumBy.XPATH, f'//*[contains(@text,"{text}")]'),
            (AppiumBy.ACCESSIBILITY_ID, text),
        ]:
            try:
                els = driver.find_elements(by, expr)
                for el in els:
                    if el.is_displayed():
                        return el
            except Exception:
                pass
        return None