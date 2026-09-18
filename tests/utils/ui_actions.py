from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.common.actions import interaction
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.common.exceptions import WebDriverException

from selenium.common.exceptions import WebDriverException
import random
import time

from utils.wait_utils import DEFAULT_WAIT_TIMEOUT, wait_until_displayed

def _ensure_locator_is_tuple(locator):
    if isinstance(locator, str):
        return (AppiumBy.XPATH, locator)
    return locator

def tap_at_coordinates(driver, x, y):
    """
    Taps at specific (x, y) coordinates using W3C Actions.
    """
    try:
        actions = ActionBuilder(driver)
        touch_input = PointerInput(interaction.POINTER_TOUCH, "touch")
        actions.devices = [touch_input]
        
        finger = actions.pointer_action
        finger.move_to_location(x, y)
        finger.pointer_down()
        finger.pause(0.1)
        finger.pointer_up()
        actions.perform()
        print(f"   -> Tapped at coordinates ({x}, {y})")
        return True
    except Exception as e:
        print(f"   -> Failed to tap at ({x}, {y}): {e}")
        return False

def smart_click(driver, locator, coordinates=None, element_name="Element", timeout=10, fallback_text=None):
    """
    Tries to click by Locator -> Fallback Text -> Coordinates.
    """
    # 1. Try Locator (XPath/ID)
    if locator:
        try:
            locator_tuple = _ensure_locator_is_tuple(locator)
            element = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable(locator_tuple)
            )
            element.click()
            print(f"   -> Clicked '{element_name}' using locator.")
            return True
        except:
            pass # Continue to fallback

    # 2. Try Fallback Text (OCR/DOM)
    if fallback_text:
        try:
            xpath = f"//*[contains(@text, '{fallback_text}') or contains(@content-desc, '{fallback_text}')]"
            element = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, xpath))
            )
            element.click()
            print(f"   -> Clicked '{element_name}' using text '{fallback_text}'.")
            return True
        except:
            pass

    # 3. Try Coordinates
    if coordinates:
        print(f"   -> Locator/Text failed. Using coordinates for '{element_name}'...")
        return tap_at_coordinates(driver, coordinates[0], coordinates[1])
            
    print(f"   -> Failed to click '{element_name}'.")
    return False

def smart_send_keys(driver, locator, text, coordinates=None, element_name="Input", timeout=10):
    """
    Waits for element, clears it, and sends text.
    """
    locator_tuple = _ensure_locator_is_tuple(locator)
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.visibility_of_element_located(locator_tuple)
        )
        element.click()
        element.clear()
        element.send_keys(text)
        try:
            if driver.is_keyboard_shown():
                driver.hide_keyboard()
        except:
            pass
        return True
    except Exception as e:
        print(f"   -> Failed to send keys to '{element_name}': {e}")
        return False

def set_input_value(driver, xpath, value, element_name="Input", timeout=DEFAULT_WAIT_TIMEOUT):
    """Put `value` into an input without tapping it, so the soft keyboard never opens.

    Waits for the field, then sets its text through UiAutomator2
    (replaceElementValue), the way an accessibility service would, instead of
    focusing the field and typing. Returns True once the value is set.
    """
    if not xpath:
        print(f"   -> No locator configured for '{element_name}'.")
        return False
    element = wait_until_displayed(driver, xpath, timeout=timeout)
    if element is None:
        print(f"   -> '{element_name}' not found within {timeout}s.")
        return False
    text = str(value)
    try:
        driver.execute_script("mobile: replaceElementValue", {"elementId": element.id, "text": text})
    except WebDriverException:
        element.send_keys(text)  # UiAutomator2 sets this without focusing the field either
    # Screens that auto-focus a field open the keyboard on their own; close it so it
    # doesn't cover the next element.
    try:
        if driver.is_keyboard_shown():
            driver.hide_keyboard()
    except WebDriverException:
        pass
    print(f"   -> Set '{element_name}' to {text!r} without the keyboard.")
    return True

def smart_select_dropdown(driver, trigger_locator, option_text, coordinates=None, element_name="Dropdown", timeout=10):
    """
    Clicks a dropdown trigger and selects an option.
    """
    if not smart_click(driver, trigger_locator, coordinates, element_name, timeout):
        raise Exception(f"Could not open dropdown: {element_name}")

    time.sleep(1)
    # Try selecting option by text
    if not smart_click(driver, None, None, fallback_text=option_text):
        print(f"   -> Failed to select option '{option_text}'")
        return False
    return True

def scroll_and_tap_by_text(driver, text_to_find, max_swipes=5):
    """
    Finds element by text (even if not clickable), gets its center coordinates, and taps there.
    """
    print(f"   -> Looking for text '{text_to_find}' to tap...")
    xpath = f"//*[contains(@text, '{text_to_find}') or contains(@content-desc, '{text_to_find}')]"
    
    for i in range(max_swipes + 1):
        try:
            time.sleep(1) 
            element = driver.find_element(AppiumBy.XPATH, xpath)
            if element.is_displayed():
                rect = element.rect
                center_x = rect['x'] + rect['width'] / 2
                center_y = rect['y'] + rect['height'] / 2
                
                print(f"   -> Found '{text_to_find}' at ({center_x}, {center_y}). Tapping...")
                return tap_at_coordinates(driver, center_x, center_y)
        except NoSuchElementException:
            pass
            
        if i < max_swipes:
            print(f"   -> '{text_to_find}' not visible. Scrolling down...")
            try:
                actions = ActionBuilder(driver)
                touch_input = PointerInput(interaction.POINTER_TOUCH, "touch")
                actions.devices = [touch_input]
                finger = actions.pointer_action
                finger.move_to_location(500, 1500)
                finger.pointer_down()
                finger.pause(0.1)
                finger.move_to_location(500, 800)
                finger.pointer_up()
                actions.perform()
            except:
                pass

    print(f"   -> Failed to find '{text_to_find}' after scrolling.")
    return False

def android_back_func(driver) -> bool:
    """Navigate back on Android (driver.back() + fallback to KEYCODE_BACK)."""
    try:
        driver.back()
        return True
    except WebDriverException:
        pass
    except Exception:
        pass
    try:
        driver.press_keycode(4)  # KEYCODE_BACK
        return True
    except Exception:
        return False

def generate_mobile_number() -> str:
    return str(random.randint(1, 5)) + "".join(str(random.randint(0, 9)) for _ in range(9))

