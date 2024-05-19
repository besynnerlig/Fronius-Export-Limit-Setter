#!/usr/bin/env python

import sys
import json
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from argparse import ArgumentParser

def parse_arguments():
    parser = ArgumentParser(description="Set Fronius inverter's soft limit field to a specified value.")
    parser.add_argument('-f', '--fronius_url', type=str, required=True, help='Fronius URL. Eg: http://192.168.2.100')
    parser.add_argument('-p', '--fronius_password', type=str, required=True, help='Fronius service account password')
    parser.add_argument('-e', '--export_limit', type=int, required=True, help='Export Limit as an integer value')
    parser.add_argument('-n', '--not_headless', action="store_true", help="Run Firefox in headless mode.")
    return parser.parse_args()

def configure_driver(not_headless):
    options = webdriver.FirefoxOptions()
    if not not_headless:
        options.add_argument("-headless")
    return webdriver.Firefox(options=options)

def set_export_limit(driver, fronius_url, fronius_password, export_limit):
    driver.implicitly_wait(10)
    driver.get(f"{fronius_url}/#/settings/evu")

    # Validate and adjust the desired limit
    desired_limit = max(export_limit, 0)
    result = {
        "desired_limit": desired_limit,
        "status": "unknown",
        "message": ""
    }

    try:
        username = driver.find_element(By.TAG_NAME, "select").get_property("value")
        password = driver.find_element(By.CSS_SELECTOR, "[type=password]")
        
        assert username == 'string:service', f"Unexpected username: {username}"
        
        password.send_keys(fronius_password)
        password.send_keys(Keys.RETURN)

        limit = driver.find_element(By.CSS_SELECTOR, '[input-validator="softLimitValidator"]')
        current_limit = limit.get_property("value")
        result["current_limit"] = current_limit

        if current_limit == str(desired_limit):
            result["status"] = "skipped"
            result["message"] = "Current limit matches desired limit. Skipping update."
            return result
        
        limit.clear()
        limit.send_keys(str(desired_limit))
        ok_button = driver.find_elements(By.CSS_SELECTOR, "button.OK")
        if ok_button:
            ok_button[2].click()
        else:
            raise NoSuchElementException("OK button not found.")

        # Confirm the limit has been set (optional additional verification step)
        new_limit = limit.get_property("value")
        if new_limit == str(desired_limit):
            result["status"] = "success"
            result["message"] = "Limit successfully updated."
            result["new_limit"] = new_limit
        else:
            result["status"] = "failure"
            result["message"] = "Failed to update the limit."

    except NoSuchElementException as e:
        result["status"] = "error"
        result["message"] = f"Element not found: {e}"
    except TimeoutException as e:
        result["status"] = "error"
        result["message"] = f"Operation timed out: {e}"
    except AssertionError as e:
        result["status"] = "error"
        result["message"] = f"Assertion failed: {e}"
    except Exception as e:
        result["status"] = "error"
        result["message"] = f"An unexpected error occurred: {e}"

    return result

def main():
    args = parse_arguments()
    result = {}

    try:
        with configure_driver(args.not_headless) as driver:
            result = set_export_limit(driver, args.fronius_url, args.fronius_password, args.export_limit)
    except Exception as e:
        result = {
            "status": "error",
            "message": f"An error occurred while setting the export limit: {e}"
        }
    
    print(json.dumps(result))
    if result.get("status") == "error":
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
