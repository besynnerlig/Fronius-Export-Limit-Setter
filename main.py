#!/usr/bin/env python

"""
This script is derived from the original work by shadow7412 on GitHub:
https://github.com/shadow7412/fronius-driver/blob/master/main.py

Original script was designed for Home Assistant integration and released
under the GPL-3.0 license. This modified version generalizes the functionality
to be used independently of any specific home automation system.

License: GPL-3.0

This script can be found at: https://github.com/besynnerlig/Fronius-Export-Limit-Setter
"""

import json
import sys
import os
import logging
from datetime import datetime
from argparse import ArgumentParser
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

class FroniusExportLimitSetter:
    def __init__(self, fronius_url, fronius_password, export_limit, not_headless, debug):
        self.fronius_url = fronius_url
        self.fronius_password = fronius_password
        self.export_limit = max(export_limit, 0)
        self.not_headless = not_headless
        self.debug = debug
        self.driver = self.configure_driver()
        self.setup_logging()
    
    def setup_logging(self):
        """Set up logging to a file in a subdirectory."""
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'fronius_export_limit_setter.log')

        logging.basicConfig(
            level=logging.DEBUG if self.debug else logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[logging.FileHandler(log_file)]
        )

        if self.debug:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.DEBUG)
            console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            logging.getLogger().addHandler(console_handler)

        self.logger = logging.getLogger(__name__)

    def configure_driver(self):
        """Configure and return the Selenium WebDriver."""
        options = webdriver.FirefoxOptions()
        if not self.not_headless:
            options.add_argument("-headless")
        return webdriver.Firefox(options=options)
    
    def set_export_limit(self):
        """Set the export limit on the Fronius inverter."""
        self.driver.implicitly_wait(10)
        self.driver.get(f"{self.fronius_url}/#/settings/evu")

        result = {
            "desired_limit": self.export_limit,
            "status": "unknown",
            "message": ""
        }

        try:
            # Locate the username field and validate it
            username = self.driver.find_element(By.TAG_NAME, "select").get_property("value")
            password = self.driver.find_element(By.CSS_SELECTOR, "[type=password]")

            assert username == 'string:service', f"Unexpected username: {username}"

            # Enter the password and submit
            password.send_keys(self.fronius_password)
            password.send_keys(Keys.RETURN)

            # Find the soft limit input field
            limit = self.driver.find_element(By.CSS_SELECTOR, '[input-validator="softLimitValidator"]')
            current_limit = limit.get_property("value")
            result["current_limit"] = current_limit

            # Check if the current limit matches the desired limit
            if current_limit == str(self.export_limit):
                result["status"] = "skipped"
                result["message"] = "Current limit matches desired limit. Skipping update."
                self.logger.info(json.dumps(result))
                return result

            # Update the soft limit
            limit.clear()
            limit.send_keys(str(self.export_limit))
            ok_button = self.driver.find_elements(By.CSS_SELECTOR, "button.OK")
            if ok_button:
                ok_button[2].click()
            else:
                raise NoSuchElementException("OK button not found.")

            # Confirm the limit has been set
            new_limit = limit.get_property("value")
            if new_limit == str(self.export_limit):
                result["status"] = "success"
                result["message"] = "Limit successfully updated."
                result["new_limit"] = new_limit
            else:
                result["status"] = "failure"
                result["message"] = "Failed to update the limit."

        except NoSuchElementException as e:
            result["status"] = "error"
            result["message"] = f"Element not found: {e}"
            self.log_error_with_screenshot(e)
        except TimeoutException as e:
            result["status"] = "error"
            result["message"] = f"Operation timed out: {e}"
            self.log_error_with_screenshot(e)
        except AssertionError as e:
            result["status"] = "error"
            result["message"] = f"Assertion failed: {e}"
            self.log_error_with_screenshot(e)
        except Exception as e:
            result["status"] = "error"
            result["message"] = f"An unexpected error occurred: {e}"
            self.log_error_with_screenshot(e)

        self.logger.info(json.dumps(result))
        return result

    def log_error_with_screenshot(self, error):
        """Log error details and save a screenshot."""
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        screenshot_path = os.path.join(log_dir, f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
        self.driver.save_screenshot(screenshot_path)
        self.logger.error(f"{error} - Screenshot saved to {screenshot_path}")

    def run(self):
        """Run the process to set the export limit and print the result as JSON."""
        try:
            result = self.set_export_limit()
        except Exception as e:
            result = {
                "status": "error",
                "message": f"An error occurred while setting the export limit: {e}"
            }
            self.log_error_with_screenshot(e)
        finally:
            self.driver.close()

        print(json.dumps(result, indent=4) if self.debug else json.dumps(result))

        if result.get("status") == "error":
            sys.exit(1)
        else:
            sys.exit(0)

def parse_arguments():
    """Parse command line arguments."""
    parser = ArgumentParser(description="Set Fronius inverter's soft limit field to a specified value.")
    parser.add_argument('-d', '--debug', action="store_true", help='Output debug information including screenshot on error')
    parser.add_argument('-f', '--fronius_url', type=str, required=True, help='Fronius URL. Eg: http://192.168.2.100')
    parser.add_argument('-p', '--fronius_password', type=str, required=True, help='Fronius service account password')
    parser.add_argument('-e', '--export_limit', type=int, required=True, help='Export Limit as an integer value')
    parser.add_argument('-n', '--not_headless', action="store_true", help="Run Firefox in headless mode.")
    return parser.parse_args()

def main():
    """Main entry point for the script."""
    args = parse_arguments()
    setter = FroniusExportLimitSetter(
        fronius_url=args.fronius_url,
        fronius_password=args.fronius_password,
        export_limit=args.export_limit,
        not_headless=args.not_headless,
        debug=args.debug
    )
    setter.run()

if __name__ == "__main__":
    main()
