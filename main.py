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
from selenium.common.exceptions import (NoSuchElementException, StaleElementReferenceException,
                                        TimeoutException, WebDriverException)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from fronius_credentials import CredentialsError, default_credentials_path, resolve_password

PAGE_TIMEOUT = 30
LOGIN_TIMEOUT = 15
LOGIN_POLL_FREQUENCY = 0.5
PASSWORD_SELECTOR = "[type=password]"
LIMIT_SELECTOR = '[input-validator="softLimitValidator"]'
# The "Logout" link in the navigation, only shown to a logged-in user
LOGGED_IN_SELECTOR = 'a[ng-click="logoutUser()"]'

class LoginError(Exception):
    """The inverter did not confirm the login. The message never contains the password."""

def is_displayed(driver, selector):
    """Return True if an element matching the CSS selector is displayed."""
    return any(e.is_displayed() for e in driver.find_elements(By.CSS_SELECTOR, selector))

def is_logged_in(driver):
    """Return True if the web interface shows the logged-in state: no login form, but the Logout link."""
    return not is_displayed(driver, PASSWORD_SELECTOR) and is_displayed(driver, LOGGED_IN_SELECTOR)

def wait_for_login(driver, timeout=None, poll_frequency=None):
    """Wait until the web interface shows the logged-in state, or raise LoginError."""
    timeout = LOGIN_TIMEOUT if timeout is None else timeout
    try:
        WebDriverWait(driver, timeout, poll_frequency=poll_frequency or LOGIN_POLL_FREQUENCY,
                      ignored_exceptions=[StaleElementReferenceException]).until(is_logged_in)
    except TimeoutException:
        raise LoginError(f"Login not confirmed within {timeout} s: the login form is still shown or the "
                         "logged-in navigation did not appear. Check the inverter password.") from None

def clear_password_fields(driver):
    """Empty all password fields, so a screenshot does not even show the password length."""
    try:
        for field in driver.find_elements(By.CSS_SELECTOR, PASSWORD_SELECTOR):
            field.clear()
    except WebDriverException:
        pass

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

        # At DEBUG level Selenium logs every WebDriver request, including typed text such as the password
        logging.getLogger('selenium').setLevel(logging.INFO)

        self.logger = logging.getLogger(__name__)

    def configure_driver(self):
        """Configure and return the Selenium WebDriver."""
        options = webdriver.FirefoxOptions()
        if not self.not_headless:
            options.add_argument("-headless")
        options.set_preference("security.sandbox.content.level", 0)
        options.set_preference("gfx.webrender.force-disabled", True)
        options.set_preference("layers.acceleration.disabled", True)
        options.set_preference("security.sandbox.content.level", 0)
        return webdriver.Firefox(options=options)
    
    def set_export_limit(self):
        """Set the export limit on the Fronius inverter."""
        self.driver.implicitly_wait(0)  # explicit waits only
        self.driver.get(f"{self.fronius_url}/#/settings/evu")

        result = {
            "desired_limit": self.export_limit,
            "status": "unknown",
            "message": ""
        }

        try:
            wait = WebDriverWait(self.driver, PAGE_TIMEOUT)

            # Locate the username field and validate it
            username = wait.until(EC.presence_of_element_located((By.TAG_NAME, "select"))).get_property("value")
            password = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, PASSWORD_SELECTOR)))

            assert username == 'string:service', f"Unexpected username: {username}"

            # Enter the password and submit
            password.send_keys(self.fronius_password)
            password.send_keys(Keys.RETURN)

            # Neither read nor write the limit unless the inverter confirmed the login
            wait_for_login(self.driver)
            self.logger.info("Login confirmed")

            # Find the soft limit input field, which is shown a few seconds after the login
            limit = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, LIMIT_SELECTOR)))
            current_limit = limit.get_property("value")
            result["current_limit"] = int(current_limit)

            # Check if the current limit matches the desired limit
            if current_limit == str(self.export_limit):
                result["status"] = "skipped"
                result["message"] = "Current limit matches desired limit. Skipping update."
                self.logger.info(json.dumps(result))
                return result

            # Update the soft limit
            limit.clear()
            limit.send_keys(str(self.export_limit))
            ok_button = wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, "button.OK"))
            if ok_button:
                ok_button[2].click()
            else:
                raise NoSuchElementException("OK button not found.")

            # Confirm the limit has been set
            new_limit = limit.get_property("value")
            if not is_logged_in(self.driver):
                raise LoginError("Logged out before the new limit could be confirmed.")
            if new_limit == str(self.export_limit):
                result["status"] = "success"
                result["message"] = "Limit successfully updated."
                result["new_limit"] = int(new_limit)
            else:
                result["status"] = "failure"
                result["message"] = "Failed to update the limit."

        except LoginError as e:
            result["status"] = "error"
            result["message"] = str(e)
            self.log_error_with_screenshot(e)
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
        clear_password_fields(self.driver)
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        screenshot_path = os.path.join(log_dir, f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
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
    parser.add_argument('-f', '--fronius_url', type=str, required=True, help='Fronius URL. Eg: http://192.0.2.10')
    parser.add_argument('-p', '--fronius_password', type=str, help='Deprecated: Fronius service account password. Use the credentials file instead')
    parser.add_argument('-i', '--inverter', type=str, help='Section name in the credentials file. Default: host name of the Fronius URL')
    parser.add_argument('-c', '--credentials_file', type=str, help=f'Credentials file. Default: {default_credentials_path()}')
    parser.add_argument('-e', '--export_limit', type=int, required=True, help='Export Limit as an integer value')
    parser.add_argument('-n', '--not_headless', action="store_true", help="Show the Firefox window instead of running headless. Useful for debugging")
    return parser.parse_args()

def main():
    """Main entry point for the script."""
    args = parse_arguments()
    try:
        fronius_password = resolve_password(
            cli_password=args.fronius_password,
            fronius_url=args.fronius_url,
            inverter=args.inverter,
            credentials_file=args.credentials_file
        )
    except CredentialsError as e:
        print(f"error: {e}", file=sys.stderr)
        result = {"status": "error", "message": str(e)}
        print(json.dumps(result, indent=4) if args.debug else json.dumps(result))
        sys.exit(e.exit_code)

    setter = FroniusExportLimitSetter(
        fronius_url=args.fronius_url,
        fronius_password=fronius_password,
        export_limit=args.export_limit,
        not_headless=args.not_headless,
        debug=args.debug
    )
    setter.run()

if __name__ == "__main__":
    main()
