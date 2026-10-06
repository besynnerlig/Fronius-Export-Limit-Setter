"""Tests for reading the inverter password from the credentials file.

These tests do not need Firefox. Only test_cli_* run main.py, and only along
paths that exit before a browser is started.
"""

import io
import json
import os
import subprocess
import sys

import pytest

import fronius_credentials as fc
from fronius_credentials import CredentialsError, read_password, resolve_password

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSWORD_1 = "example-password-1"
PASSWORD_2 = "example-password-2"

CONTENT = f"""\
[192.0.2.10]
password = {PASSWORD_1}

[inverter2]
password = {PASSWORD_2}
"""


def write_credentials(tmp_path, content=CONTENT, mode=0o600, dir_mode=0o700):
    """Write a credentials file in its own directory and return its path."""
    directory = tmp_path / "fronius-export-limit-setter"
    directory.mkdir(exist_ok=True)
    path = directory / "credentials"
    path.write_text(content)
    path.chmod(mode)
    directory.chmod(dir_mode)
    return str(path)


def assert_no_secret(text):
    assert PASSWORD_1 not in text
    assert PASSWORD_2 not in text


# Lookup

def test_lookup_by_url_host_name(tmp_path):
    path = write_credentials(tmp_path)
    assert resolve_password(None, "http://192.0.2.10", credentials_file=path) == PASSWORD_1


def test_lookup_ignores_scheme_port_and_path(tmp_path):
    path = write_credentials(tmp_path)
    assert resolve_password(None, "https://192.0.2.10:8080/#/settings", credentials_file=path) == PASSWORD_1


def test_lookup_url_without_scheme(tmp_path):
    path = write_credentials(tmp_path)
    assert resolve_password(None, "192.0.2.10", credentials_file=path) == PASSWORD_1


def test_host_name_lookup_is_case_insensitive(tmp_path):
    path = write_credentials(tmp_path, f"[Inverter1.Example]\npassword = {PASSWORD_1}\n")
    assert resolve_password(None, "http://inverter1.example", credentials_file=path) == PASSWORD_1


def test_inverter_option_takes_precedence_over_host_name(tmp_path):
    path = write_credentials(tmp_path)
    assert resolve_password(None, "http://192.0.2.10", inverter="inverter2", credentials_file=path) == PASSWORD_2


def test_inverter_option_does_not_fall_back_to_host_name(tmp_path):
    path = write_credentials(tmp_path)
    with pytest.raises(CredentialsError) as e:
        resolve_password(None, "http://192.0.2.10", inverter="inverter3", credentials_file=path)
    assert e.value.exit_code == fc.EXIT_CREDENTIALS_INVALID
    assert "inverter3" in str(e.value)
    assert_no_secret(str(e.value))


def test_unknown_host_name(tmp_path):
    path = write_credentials(tmp_path)
    with pytest.raises(CredentialsError) as e:
        resolve_password(None, "http://198.51.100.7", credentials_file=path)
    assert e.value.exit_code == fc.EXIT_CREDENTIALS_INVALID
    assert_no_secret(str(e.value))


def test_url_without_host_name(tmp_path):
    path = write_credentials(tmp_path)
    with pytest.raises(CredentialsError) as e:
        resolve_password(None, "http://", credentials_file=path)
    assert e.value.exit_code == fc.EXIT_CREDENTIALS_INVALID
    assert "--inverter" in str(e.value)


def test_password_special_characters_are_kept(tmp_path):
    special = "p%(x)s=a:b;#c"
    path = write_credentials(tmp_path, f"[inverter1]\npassword = {special}\n")
    assert read_password(path, "inverter1") == special


def test_empty_password(tmp_path):
    path = write_credentials(tmp_path, "[inverter1]\npassword =\n")
    with pytest.raises(CredentialsError) as e:
        read_password(path, "inverter1")
    assert e.value.exit_code == fc.EXIT_CREDENTIALS_INVALID


def test_missing_password_key(tmp_path):
    path = write_credentials(tmp_path, f"[inverter1]\npasswort = {PASSWORD_1}\n")
    with pytest.raises(CredentialsError) as e:
        read_password(path, "inverter1")
    assert e.value.exit_code == fc.EXIT_CREDENTIALS_INVALID
    assert_no_secret(str(e.value))


# Missing, unreadable and invalid files

def test_missing_file(tmp_path):
    with pytest.raises(CredentialsError) as e:
        resolve_password(None, "http://192.0.2.10", credentials_file=str(tmp_path / "credentials"))
    assert e.value.exit_code == fc.EXIT_CREDENTIALS_MISSING
    assert "not found" in str(e.value)


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read any file")
def test_unreadable_file(tmp_path):
    path = write_credentials(tmp_path, mode=0o000)
    with pytest.raises(CredentialsError) as e:
        read_password(path, "inverter2")
    assert e.value.exit_code == fc.EXIT_CREDENTIALS_INVALID
    assert "permission denied" in str(e.value)


@pytest.mark.parametrize("content", [
    f"[inverter1]\npassword {PASSWORD_1}\n",           # no delimiter
    f"password = {PASSWORD_1}\n",                       # no section header
    f"[inverter1]\npassword = {PASSWORD_1}\n[inverter1]\npassword = {PASSWORD_2}\n",  # duplicate section
])
def test_parse_errors_do_not_leak_file_contents(tmp_path, content):
    path = write_credentials(tmp_path, content)
    with pytest.raises(CredentialsError) as e:
        read_password(path, "inverter1")
    assert e.value.exit_code == fc.EXIT_CREDENTIALS_INVALID
    assert "line" in str(e.value)
    assert_no_secret(str(e.value))


def test_invalid_utf8(tmp_path):
    path = write_credentials(tmp_path)
    with open(path, "wb") as f:
        f.write(b"[inverter1]\npassword = \xff\xfe\n")
    with pytest.raises(CredentialsError) as e:
        read_password(path, "inverter1")
    assert e.value.exit_code == fc.EXIT_CREDENTIALS_INVALID


# Permission checks

@pytest.mark.parametrize("mode", [0o600, 0o400, 0o700])
def test_owner_only_modes_are_accepted(tmp_path, mode):
    path = write_credentials(tmp_path, mode=mode)
    assert read_password(path, "inverter2") == PASSWORD_2


@pytest.mark.parametrize("mode", [0o640, 0o604, 0o644, 0o620, 0o602, 0o610, 0o666])
def test_group_or_other_access_is_refused(tmp_path, mode):
    path = write_credentials(tmp_path, mode=mode)
    with pytest.raises(CredentialsError) as e:
        read_password(path, "inverter2")
    assert e.value.exit_code == fc.EXIT_CREDENTIALS_INSECURE
    assert f"{mode:04o}" in str(e.value)
    assert "chmod 600" in str(e.value)
    assert_no_secret(str(e.value))


@pytest.mark.parametrize("dir_mode", [0o770, 0o707, 0o777])
def test_group_or_other_writable_directory_is_refused(tmp_path, dir_mode):
    path = write_credentials(tmp_path, dir_mode=dir_mode)
    with pytest.raises(CredentialsError) as e:
        read_password(path, "inverter2")
    assert e.value.exit_code == fc.EXIT_CREDENTIALS_INSECURE
    assert "chmod 700" in str(e.value)


def test_directory_instead_of_file_is_refused(tmp_path):
    directory = tmp_path / "credentials"
    directory.mkdir(mode=0o700)
    with pytest.raises(CredentialsError) as e:
        read_password(str(directory), "inverter2")
    assert e.value.exit_code == fc.EXIT_CREDENTIALS_INSECURE
    assert "not a regular file" in str(e.value)


def test_fifo_is_refused_without_blocking(tmp_path):
    fifo = tmp_path / "credentials"
    os.mkfifo(fifo, 0o600)
    with pytest.raises(CredentialsError) as e:
        read_password(str(fifo), "inverter2")
    assert e.value.exit_code == fc.EXIT_CREDENTIALS_INSECURE


def test_file_owned_by_another_user_is_refused(tmp_path, monkeypatch):
    path = write_credentials(tmp_path)
    monkeypatch.setattr(fc.os, "getuid", lambda: os.stat(path).st_uid + 1)
    with pytest.raises(CredentialsError) as e:
        read_password(path, "inverter2")
    assert e.value.exit_code == fc.EXIT_CREDENTIALS_INSECURE
    assert "owned by uid" in str(e.value)


# Default path and the deprecated -p option

def test_default_path_uses_xdg_config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    write_credentials(tmp_path)
    assert fc.default_credentials_path() == str(tmp_path / "fronius-export-limit-setter" / "credentials")
    assert resolve_password(None, "http://192.0.2.10") == PASSWORD_1


def test_default_path_without_xdg_config_home(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert fc.default_credentials_path() == str(tmp_path / ".config" / "fronius-export-limit-setter" / "credentials")


def test_cli_password_is_used_with_deprecation_warning(tmp_path):
    stderr = io.StringIO()
    password = resolve_password(PASSWORD_1, "http://192.0.2.10",
                                credentials_file=str(tmp_path / "does-not-exist"), stderr=stderr)
    assert password == PASSWORD_1
    assert "deprecated" in stderr.getvalue()
    assert_no_secret(stderr.getvalue())


def test_no_warning_when_reading_credentials_file(tmp_path):
    path = write_credentials(tmp_path)
    stderr = io.StringIO()
    resolve_password(None, "http://192.0.2.10", credentials_file=path, stderr=stderr)
    assert stderr.getvalue() == ""


# Command line: exits before Firefox is started

def run_main(*args, env=None):
    pytest.importorskip("selenium")  # imported by main.py, but no browser is started
    return subprocess.run([sys.executable, os.path.join(REPO_DIR, "main.py"), *args],
                          capture_output=True, text=True, timeout=60, env=env)


def test_cli_missing_credentials_file(tmp_path):
    result = run_main("-e", "100", "-f", "http://192.0.2.10", "-c", str(tmp_path / "credentials"))
    assert result.returncode == fc.EXIT_CREDENTIALS_MISSING
    assert json.loads(result.stdout)["status"] == "error"
    assert "not found" in result.stderr


def test_cli_insecure_credentials_file(tmp_path):
    path = write_credentials(tmp_path, mode=0o644)
    result = run_main("-e", "100", "-f", "http://192.0.2.10", "-c", path)
    assert result.returncode == fc.EXIT_CREDENTIALS_INSECURE
    assert json.loads(result.stdout)["status"] == "error"
    assert_no_secret(result.stdout + result.stderr)


def test_cli_unknown_inverter(tmp_path):
    path = write_credentials(tmp_path)
    result = run_main("-e", "100", "-f", "http://192.0.2.10", "-i", "inverter3", "-c", path)
    assert result.returncode == fc.EXIT_CREDENTIALS_INVALID
    assert json.loads(result.stdout)["status"] == "error"
    assert_no_secret(result.stdout + result.stderr)


def test_cli_password_option_is_optional():
    result = run_main("-h")
    assert result.returncode == 0
    assert "Deprecated" in result.stdout
