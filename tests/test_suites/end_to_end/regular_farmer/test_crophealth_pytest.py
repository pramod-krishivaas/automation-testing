import json
import os

import allure
import pytest

from tests.pages.regular_farmer.regular_farmer_crophealth_page import (
    load_locators_once, farm_card, crop_health_screen_loaded, crop_health_layer_shown, date_slider_until_stress,
    crop_health_stress_types,
)

def _save_flow(test_flow_steps):
    os.makedirs("test-flows", exist_ok=True)
    with open("test-flows/crophealth_flow_success.json", "w") as f:
        json.dump(test_flow_steps, f, indent=4)


@allure.epic("Crop Health Flow")
@allure.feature("Crop Health")
class TestCropHealth:

    @pytest.fixture(scope="class", autouse=True)
    def setup(self, request):
        load_locators_once(self, request)

    @allure.story("Crop health layer is shown")
    @allure.title("E2E_RF_003 -- Check Crop health layer and Crop health stress types and percentages")
    def test_E2E_RF_003(self, driver):
            test_flow_steps = []
            try:
                farm_card(driver, self, test_flow_steps)
                crop_health_screen_loaded(driver, self, test_flow_steps)
                # Screenshot + the detected layer + measurements go to Allure under a
                # step titled "Crop health layer: SHOWN" or "NOT SHOWN".
                crop_health_layer_shown(driver, self, test_flow_steps)
                # Clicks the date minus icon until stress pixels (Caution, Warning,
                # Stressed or Severely Stressed markers) appear on the farm.
                date_slider_until_stress(driver, self, test_flow_steps)
                # Fails if the displayed percentages don't match the markers, including
                # when all four are 0% while stress pixels are on the map.
                crop_health_stress_types(driver, self, test_flow_steps)
                # crop_health_legend_and_dates(driver, self, test_flow_steps)

            finally:
                _save_flow(test_flow_steps)

