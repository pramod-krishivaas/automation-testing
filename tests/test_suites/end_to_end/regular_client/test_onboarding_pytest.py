import time
import allure
import pytest
import json
import os

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from appium.webdriver.common.appiumby import AppiumBy

from utils.wait_utils import smart_click
from utils.location_utils import reset_device_location
from utils.location_utils import reset_device_location

from tests.pages.regular_client.regular_client_onboarding_page import (
    inter_crop_name_dropdown, inter_crop_name_item, inter_crop_name_search_input, inter_crop_short_duration_button, inter_crop_sowing_date_input, load_locators_once, add_button, add_farmer_button,
    crop_name_dropdown, crop_name_item, plantation_date,
    calendar_ok_button, submit_crop_button, add_farmer_name_input, add_farmer_phone_input, submit_button_add_farmer,
    submit_button_add_farm, field_agent_dropdown, field_agent_dropdown_item, draw_boundary_buton_on_modal, draw_boundary_on_map, save_boundary_button, search_input, search_result,
    set_run_location,
from tests.pages.regular_client.regular_client_onboarding_page import (
    inter_crop_name_dropdown, inter_crop_name_item, inter_crop_name_search_input, inter_crop_short_duration_button, inter_crop_sowing_date_input, load_locators_once, add_button, add_farmer_button,
    crop_name_dropdown, crop_name_item, plantation_date,
    calendar_ok_button, submit_crop_button, add_farmer_name_input, add_farmer_phone_input, submit_button_add_farmer,
    submit_button_add_farm, field_agent_dropdown, field_agent_dropdown_item, draw_boundary_buton_on_modal, draw_boundary_on_map, save_boundary_button, search_input, search_result,
    set_run_location,
)


@allure.epic("Onboarding Flow")
@allure.feature("Authentication")
class TestOnboarding:

    @pytest.fixture(scope="class", autouse=True)
    def setup(self, request):
        load_locators_once(self, request)

    @allure.story("Successful Onboarding")
    @allure.title("Dashboard → Add Farmer → Add Farm → Add Crop")
    def test_add_new_farmer_farm_crop_flow(self, driver):
            test_flow_steps = []
            try:
                # This run's own spot for the farm boundary: mock the GPS there now,
                # so the app has the location by the time the map opens.
                # set_run_location(driver, self, test_flow_steps)
                # After the login run lands on the dashboard, a loader overlays the
                # screen briefly. Wait it out so the Add button is actually tappable
                # (without this the tap can land on the loader and the test fails).
                time.sleep(6)
                add_button(driver, self, test_flow_steps)
                add_farmer_button(driver, self, test_flow_steps)
                add_farmer_name_input(driver, self, test_flow_steps)
                add_farmer_phone_input(driver, self, test_flow_steps)
                field_agent_dropdown(driver, self, test_flow_steps)
                field_agent_dropdown_item(driver, self, test_flow_steps)
                # add farm clicks
                submit_button_add_farmer(driver, self, test_flow_steps)
                draw_boundary_buton_on_modal(driver, self, test_flow_steps)
                submit_button_add_farm(driver, self, test_flow_steps)
                crop_name_dropdown(driver, self, test_flow_steps)
                crop_name_item(driver, self, test_flow_steps)
                plantation_date(driver, self, test_flow_steps)
                calendar_ok_button(driver, self, test_flow_steps)
                inter_crop_name_dropdown(driver, self, test_flow_steps)
                time.sleep(2)
                inter_crop_name_search_input(driver, self, test_flow_steps)
                time.sleep(2)
                inter_crop_name_item(driver, self, test_flow_steps)
                inter_crop_short_duration_button(driver, self, test_flow_steps)
                inter_crop_sowing_date_input(driver, self, test_flow_steps)
                calendar_ok_button(driver, self, test_flow_steps)
                submit_crop_button(driver, self, test_flow_steps)
                draw_boundary_on_map(driver, self, test_flow_steps)
                # search_input(driver, self, test_flow_steps)
                # search_result(driver, self, test_flow_steps)
                save_boundary_button(driver, self, test_flow_steps)

                add_farmer_name_input(driver, self, test_flow_steps)
                add_farmer_phone_input(driver, self, test_flow_steps)
                field_agent_dropdown(driver, self, test_flow_steps)
                field_agent_dropdown_item(driver, self, test_flow_steps)
                # add farm clicks
                submit_button_add_farmer(driver, self, test_flow_steps)
                draw_boundary_buton_on_modal(driver, self, test_flow_steps)
                submit_button_add_farm(driver, self, test_flow_steps)
                crop_name_dropdown(driver, self, test_flow_steps)
                crop_name_item(driver, self, test_flow_steps)
                plantation_date(driver, self, test_flow_steps)
                calendar_ok_button(driver, self, test_flow_steps)
                inter_crop_name_dropdown(driver, self, test_flow_steps)
                time.sleep(2)
                inter_crop_name_search_input(driver, self, test_flow_steps)
                time.sleep(2)
                inter_crop_name_item(driver, self, test_flow_steps)
                inter_crop_short_duration_button(driver, self, test_flow_steps)
                inter_crop_sowing_date_input(driver, self, test_flow_steps)
                calendar_ok_button(driver, self, test_flow_steps)
                submit_crop_button(driver, self, test_flow_steps)
                draw_boundary_on_map(driver, self, test_flow_steps)
                # search_input(driver, self, test_flow_steps)
                # search_result(driver, self, test_flow_steps)
                save_boundary_button(driver, self, test_flow_steps)

    
            finally:
                reset_device_location(driver)
                reset_device_location(driver)
                os.makedirs("test-flows", exist_ok=True)
                with open("test-flows/onboarding_flow_success.json", "w") as f:
                    json.dump(test_flow_steps, f, indent=4)