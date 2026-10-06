"""Debug mode must not log WebDriver requests, which contain typed text such as the password.

No browser is started: configure_driver is replaced by a stub.
"""

import logging

import pytest

main = pytest.importorskip("main")  # needs the selenium package, not Firefox

PASSWORD = "example-password-1"


def test_debug_mode_does_not_log_webdriver_requests(monkeypatch, caplog):
    monkeypatch.setattr(main.FroniusExportLimitSetter, "configure_driver", lambda self: object())
    main.FroniusExportLimitSetter("http://192.0.2.10", PASSWORD, 100, False, debug=True)

    caplog.set_level(logging.DEBUG)
    request_logger = logging.getLogger("selenium.webdriver.remote.remote_connection")
    request_logger.debug("POST /session/1/element/2/value {'text': '%s'}", PASSWORD)

    assert not request_logger.isEnabledFor(logging.DEBUG)
    assert PASSWORD not in caplog.text
