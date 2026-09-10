"""
App-switch page object for the UNIFIED app.

The unified app has no role picker at login: after authenticating it redirects to
a home screen by PRIORITY —

    state_client (1) > state_farmer (2) > regular_farmer (3) > regular_client (4)

— landing on the highest-priority role the phone number is assigned to. So the app
you *land* on is not necessarily the app you want to *test*. This module:

  1. detect_landed_app()  — reads role-unique `home_markers` to identify which
     app's home the shared login actually landed on. Called ONCE after login.
  2. switch_to_app()      — given that detected `landed` app: if it already equals
     the target role selected in the UI, run directly; otherwise open the in-app
     switch toggle and switch to the target. The switch itself never re-detects.

Locators come from `unified_app.json` → `switch_control` and `home_markers`, bound
onto the test class by `pages/common/login_page.load_locators_once`.
"""
import time
import pytest
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from utils.wait_utils import smart_click

import sys
sys.dont_write_bytecode = True

# Highest → lowest priority. Detection probes in this order so that, if two home
# markers ever matched at once, the higher-priority app wins (mirrors the app).
ROLE_PRIORITY = ["state_farmer", "regular_farmer", "state_client", "regular_client"]


ROLE_LABELS = {
    "state_client":   "Telangana Client",
    "state_farmer":   "Telangana Farmerrrrrrrrrrrr",
    "regular_farmer": "Regular Farmer",
    # "regular_client": "Administrator, \uf222"
    "regular_client": "Field Agent",
}


def _log_step(steps, text, status="Success"):
    print(f"[switch] {text}")
    if steps is not None:
        steps.append({"step": text, "status": status})


def _element_present(driver, xpath, timeout=1) -> bool:
    if not xpath:
        return False
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, xpath))
        )
        return True
    except TimeoutException:
        return False
    except Exception:
        return False


def _configured_markers(obj) -> dict:
    """Home markers that actually have an xpath value (blank ones are 'not set')."""
    markers = getattr(obj, "home_markers", {}) or {}
    return {role: xp for role, xp in markers.items() if xp}


def detect_landed_app(driver, obj, timeout=10, probe_timeout=2):
    """
    Identify which role's home screen is currently shown by probing each
    configured `home_markers` locator in priority order.

    Returns the role key (e.g. 'regular_farmer'), or None if no marker matched
    (either none configured, or the home hasn't rendered / is an unknown screen).
    `probe_timeout` is the per-marker wait; keep it >1s so a slow find under a
    loading app doesn't produce a false negative.
    """
    configured = _configured_markers(obj)
    if not configured:
        print("[switch] No home_markers configured in unified_app.json — cannot detect landed app.")
        return None

    deadline = time.time() + timeout
    while time.time() < deadline:
        for role in ROLE_PRIORITY:
            xp = configured.get(role)
            if xp and _element_present(driver, xp, timeout=probe_timeout):
                print(f"[switch] Landed app detected → {role} - {configured.get(role)} - ({ROLE_LABELS.get(role, role)})")
                return role
        time.sleep(1)

    print(f"[switch] Could not detect landed app within {timeout}s. Probed these "
          f"home_markers (unified_app.json): {configured}")
    # Dump what's actually on screen so the real chip text is visible — the usual
    # cause of a None here is a home_marker that doesn't match the rendered text
    # (e.g. whitespace/label drift). Compare 'On-screen now' against the markers.
    _log_visible_text(driver)
    return None


def _log_visible_text(driver, limit=12):
    """On a detection miss, dump a few on-screen text/desc values so the run log
    shows WHAT screen we were stuck on (loader? re-prompt? a different home?)."""
    try:
        found = []
        for el in driver.find_elements(AppiumBy.XPATH, "//*[@text!='' or @content-desc!='']"):
            for attr in ("text", "content-desc"):
                v = (el.get_attribute(attr) or "").strip()
                if v and v not in found:
                    found.append(v)
            if len(found) >= limit:
                break
        print(f"[switch] On-screen now: {found}")
    except Exception as e:
        print(f"[switch] Could not read on-screen text: {e}")


def switch_to_app(driver, obj, target_role, test_flow_steps=None, landed=None):
    """
    Switch the unified app to `target_role`, then return so the target's test suite
    runs directly.

    By design this performs NO landed-app detection of its own — detection happens
    ONCE right after login and its result is passed in here as `landed`:

      • landed == target_role → already on the target, nothing to switch; run directly.
      • otherwise             → open the in-app switcher and select the target.

    The switch itself never re-detects (no dependency on `home_markers`, no slow
    post-switch probe); selecting the "Current App" entry would be a harmless no-op
    anyway, so an unknown `landed` (None) just falls through to a normal switch.

    • target_role falsy → nothing to switch, returns True.
    """
    if not target_role:
        print("[switch] No target_role provided; skipping app-switch.")
        return True

    if target_role not in ROLE_PRIORITY:
        pytest.fail(f"[switch] Unknown target_role '{target_role}'. Expected one of {ROLE_PRIORITY}.")

    # Detected after login (passed in) — if we already landed on the target, there is
    # nothing to switch. We never detect INSIDE this function.
    if landed and landed == target_role:
        _log_step(
            test_flow_steps,
            f"Already on target app '{ROLE_LABELS.get(target_role, target_role)}' (detected after login; no switch needed)",
        )
        return True

    print(f"[switch] Landed on '{landed}', switching to target app '{target_role}' via toggle (no detection)…")

    # 1. Open the in-app switcher.
    if not obj.switch_toggle_button_xpath:
        pytest.fail("[switch] switch_control.switch_toggle_button is not configured in unified_app.json.")
    if not smart_click(driver, "App switch toggle", obj.switch_toggle_button_xpath, "Switch"):
        pytest.fail("[switch] Could not open the app switcher (switch_toggle_button).")

    # 2. Select the target app in the switcher.
    target_xpath = (getattr(obj, "switch_targets", {}) or {}).get(target_role)
    if not target_xpath:
        pytest.fail(
            f"[switch] No switch target locator for '{target_role}' "
            f"(set switch_control.target_{target_role} in unified_app.json)."
        )
    if not smart_click(driver, f"Switch to {target_role}", target_xpath, ROLE_LABELS.get(target_role)):
        pytest.fail(f"[switch] Could not select target app '{target_role}' in the switcher.")

    # 3. Let the switch settle, then run the target's suite directly — NO post-switch
    #    landed-app detection/verification (per requirement).
    time.sleep(3)
    _log_step(test_flow_steps, f"Switched to target app '{ROLE_LABELS.get(target_role, target_role)}'")
    return True


def assert_on_app(driver, obj, target_role, test_flow_steps=None):
    """Hard assertion that the current home is `target_role`'s (skips if not configured)."""
    if not _configured_markers(obj):
        print("[switch] assert_on_app skipped: home_markers not configured.")
        return True
    landed = detect_landed_app(driver, obj)
    if landed != target_role:
        pytest.fail(f"[switch] Expected to be on '{target_role}' home but detected '{landed}'.")
    _log_step(test_flow_steps, f"Verified on target app '{ROLE_LABELS.get(target_role, target_role)}'")
    return True
