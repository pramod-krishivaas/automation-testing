"""
Common Login (unified app) — shared by ALL four apps.

Login is identical across regular_farmer / regular_client / state_farmer /
state_client, so this single test is mapped to every app's "Login" module:

  shared login (pages/common/login_page)  →  land by priority  →
  detect landed app  →  switch to the SELECTED app (pages/common/switch_page)  →
  assert on the selected app's home.

Which app to land on comes from the UI selection via the `--target-role` pytest
option (exposed as the `target_role` fixture in conftest.py). DEFAULT_ROLE is only
used for direct/local runs that don't pass --target-role.
"""
import os
import json
import allure
import pytest
from pages.common.login_page import load_locators_once, do_login
from pages.common.switch_page import detect_landed_app, switch_to_app

import sys
sys.dont_write_bytecode = True

# Only used for local/direct pytest runs; the UI always passes the selected app's
# variant via --target-role, which overrides this.
DEFAULT_ROLE = "regular_farmer"


def _account_for(role):
    """Return (phone, mpin) for a single-role account from test_data/accounts.json."""
    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "test_data", "accounts.json",
    )
    try:
        with open(data_path, "r", encoding="utf-8") as f:
            accounts = json.load(f)
        acct = accounts.get("single_role", {}).get(role, {})
        return acct.get("phone") or "7660852538", acct.get("mpin") or "1234"
    except Exception as e:
        print(f"[data] Could not load accounts.json ({e}); using defaults.")
        return "7660852538", "1234"


@allure.epic("Login Flow")
@allure.feature("Authentication")
class TestLogin:

    @pytest.fixture(scope="class", autouse=True)
    def setup(self, request):
        load_locators_once(self, request)

    @allure.story("Successful Login")
    @allure.title("test_LOGINPOS_TC_030 -- Verify user can login with valid credentials")
    def test_LOGINPOS_TC_030(self, driver, target_role, login_phone, login_mpin):
        test_flow_steps = []
        # The selected app (from the UI); DEFAULT_ROLE only for local runs.
        role = target_role or DEFAULT_ROLE
        # Prefer the mobile number provided in the UI; fall back to accounts.json
        # for the selected app's role. The number determines which apps are
        # reachable; `role` (the selected app) is where we end up after switching.
        if login_phone:
            phone, mpin = login_phone, (login_mpin or "1234")
        else:
            phone, mpin = _account_for(role)
        print(f"[test] Logging in with phone={phone} (mpin set: {bool(mpin)}) for role={role}")

        try:
            # 1. Shared login — lands on whichever home the number resolves to by priority.
            do_login(driver, self, test_flow_steps, phone_number=phone, mpin=mpin)

            # 2. Detect which app_variant the login landed on (detection happens HERE,
            #    once, after login — never inside the switch). The wait inside is
            #    dynamic, so no fixed sleep for the home screen to render.
            landed = detect_landed_app(driver, self)
            print(f"[test] Selected/target role = {role}; landed on = {landed}")

            # 3. Continue on the detected app: if it's already the selected app, run its
            #    suite directly; otherwise switch to the selected app (switch does NOT
            #    detect). `landed` is passed so the switch skips when already on target.
            switch_to_app(driver, self, role, test_flow_steps, landed=landed)

        finally:
            os.makedirs("test-flows", exist_ok=True)
            with open("test-flows/login_flow_success.json", "w") as f:
                json.dump(test_flow_steps, f, indent=4)
