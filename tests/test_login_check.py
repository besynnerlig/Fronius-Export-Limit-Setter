"""Tests for the login check in main.py.

No browser is started: a fake WebDriver simulates the inverter's login page and
settings page. Only example values are used.
"""

import json

import pytest

main = pytest.importorskip("main")  # needs the selenium package, not Firefox
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.keys import Keys

PASSWORD = "example-password-1"


class FakeElement:
    def __init__(self, driver, kind, displayed=True, value=""):
        self.driver = driver
        self.kind = kind
        self.displayed = displayed
        self.value = value

    def is_displayed(self):
        return self.displayed

    def get_property(self, name):
        assert name == "value"
        if self.kind == "limit":
            self.driver.limit_reads += 1
        return self.value

    def send_keys(self, text):
        if self.kind == "password" and text == Keys.RETURN:
            self.driver.submitted = True
        else:
            self.value += text

    def clear(self):
        self.value = ""

    def click(self):
        self.driver.ok_clicks += 1
        if self.driver.logout_after_save:
            self.driver.page = "login"
        if not self.driver.save_works:
            self.driver.limit.value = self.driver.stored_limit


class FakeDriver:
    """Login page until the password is submitted; then the settings page after
    `login_polls` checks, or never if `login_accepted` is False."""

    def __init__(self, login_accepted=True, limit="100", login_polls=2, save_works=True,
                 logout_after_save=False, show_logout_link=True):
        self.login_accepted = login_accepted
        self.login_polls = login_polls
        self.save_works = save_works
        self.logout_after_save = logout_after_save
        self.show_logout_link = show_logout_link
        self.page = "login"
        self.submitted = False
        self.logged_in_once = False
        self.polls = 0
        self.limit_reads = 0
        self.ok_clicks = 0
        self.screenshot_password_values = []
        self.stored_limit = limit
        self.select = FakeElement(self, "select", value="string:service")
        self.password = FakeElement(self, "password")
        self.limit = FakeElement(self, "limit", value=limit)
        self.logout_link = FakeElement(self, "logout", displayed=show_logout_link)
        self.ok_buttons = [FakeElement(self, "ok") for _ in range(3)]

    def implicitly_wait(self, seconds):
        pass

    def get(self, url):
        pass

    def find_elements(self, by, selector):
        if self.page == "login" and self.submitted and self.login_accepted and not self.logged_in_once:
            self.polls += 1
            if self.polls >= self.login_polls:
                self.page = "settings"
                self.logged_in_once = True
        if self.page == "login":
            return {"select": [self.select], main.PASSWORD_SELECTOR: [self.password]}.get(selector, [])
        return {main.LOGGED_IN_SELECTOR: [self.logout_link], main.LIMIT_SELECTOR: [self.limit],
                "button.OK": self.ok_buttons}.get(selector, [])

    def find_element(self, by, selector):
        found = self.find_elements(by, selector)
        if not found:
            raise NoSuchElementException(selector)
        return found[0]

    def save_screenshot(self, path):
        self.screenshot_password_values.append(self.password.value)
        return True

    def close(self):
        pass


@pytest.fixture(autouse=True)
def fast_waits(monkeypatch):
    monkeypatch.setattr(main, "LOGIN_TIMEOUT", 0.3)
    monkeypatch.setattr(main, "LOGIN_POLL_FREQUENCY", 0.01)
    monkeypatch.setattr(main, "PAGE_TIMEOUT", 0.3)


def run_setter(monkeypatch, capsys, driver, export_limit):
    monkeypatch.setattr(main.FroniusExportLimitSetter, "configure_driver", lambda self: driver)
    setter = main.FroniusExportLimitSetter("http://192.0.2.10", PASSWORD, export_limit, False, debug=False)
    with pytest.raises(SystemExit) as exit_info:
        setter.run()
    out = capsys.readouterr()
    assert PASSWORD not in out.out + out.err
    return json.loads(out.out), exit_info.value.code


# wait_for_login / is_logged_in

def test_login_confirmed_when_form_gone_and_logout_link_shown():
    driver = FakeDriver(login_polls=3)
    driver.submitted = True
    main.wait_for_login(driver)
    assert driver.page == "settings"


def test_login_not_confirmed_while_login_form_is_shown():
    driver = FakeDriver(login_accepted=False)
    driver.submitted = True
    with pytest.raises(main.LoginError) as e:
        main.wait_for_login(driver)
    assert "Login not confirmed" in str(e.value)


def test_no_logout_link_is_not_logged_in():
    driver = FakeDriver(show_logout_link=False)
    driver.page = "settings"
    assert not main.is_logged_in(driver)


def test_logout_link_with_password_field_is_not_logged_in():
    driver = FakeDriver()
    driver.page = "settings"
    original = driver.find_elements
    driver.find_elements = lambda by, sel: [driver.password] if sel == main.PASSWORD_SELECTOR else original(by, sel)
    assert not main.is_logged_in(driver)


def test_stale_elements_are_retried():
    driver = FakeDriver()
    driver.page = "settings"
    original = driver.find_elements
    calls = {"n": 0}

    def flaky(by, selector):
        calls["n"] += 1
        if calls["n"] == 1:
            raise StaleElementReferenceException("page changed")
        return original(by, selector)

    driver.find_elements = flaky
    main.wait_for_login(driver)
    assert calls["n"] > 1


# Whole run, including exit codes

def test_rejected_login_is_an_error_and_touches_no_limit(monkeypatch, capsys):
    driver = FakeDriver(login_accepted=False)
    result, code = run_setter(monkeypatch, capsys, driver, 100)
    assert code == 1
    assert result["status"] == "error"
    assert "Login not confirmed" in result["message"]
    assert "current_limit" not in result
    assert driver.limit_reads == 0
    assert driver.ok_clicks == 0
    assert driver.screenshot_password_values == [""]  # password field emptied before the screenshot


def test_confirmed_login_and_same_limit_is_skipped(monkeypatch, capsys):
    driver = FakeDriver(limit="100")
    result, code = run_setter(monkeypatch, capsys, driver, 100)
    assert (result["status"], code) == ("skipped", 0)
    assert result["current_limit"] == 100
    assert driver.ok_clicks == 0


def test_confirmed_login_and_new_limit_is_success(monkeypatch, capsys):
    driver = FakeDriver(limit="100")
    result, code = run_setter(monkeypatch, capsys, driver, 200)
    assert (result["status"], code) == ("success", 0)
    assert result["new_limit"] == 200
    assert driver.ok_clicks == 1


def test_logged_out_after_saving_is_an_error(monkeypatch, capsys):
    driver = FakeDriver(limit="100", logout_after_save=True)
    result, code = run_setter(monkeypatch, capsys, driver, 200)
    assert (result["status"], code) == ("error", 1)
    assert "Logged out" in result["message"]


def test_unsaved_limit_is_still_failure_with_exit_0(monkeypatch, capsys):
    driver = FakeDriver(limit="100", save_works=False)
    result, code = run_setter(monkeypatch, capsys, driver, 200)
    assert (result["status"], code) == ("failure", 0)
