"""
Read the Fronius inverter password from a credentials file that only its owner
can access, so the password never has to appear on a command line.

The file is in INI format with one section per inverter:

    [inverter1]
    password = ...

A section is selected by --inverter NAME, or else by the host name of the
Fronius URL. Messages never include the password or any line of the file.

License: GPL-3.0
"""

import configparser
import os
import stat
import sys
from urllib.parse import urlparse

EXIT_CREDENTIALS_MISSING = 3
EXIT_CREDENTIALS_INSECURE = 4
EXIT_CREDENTIALS_INVALID = 5

DEPRECATION_WARNING = (
    "warning: -p/--fronius_password is deprecated and will be removed: the password is "
    "visible to other users in the process list. Store it in the credentials file "
    "instead (see README)."
)


class CredentialsError(Exception):
    """A credentials problem with a message that is safe to print and an exit code."""

    def __init__(self, message, exit_code):
        super().__init__(message)
        self.exit_code = exit_code


def default_credentials_path():
    """Return the default credentials file path, honouring XDG_CONFIG_HOME."""
    config_home = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(config_home, "fronius-export-limit-setter", "credentials")


def inverter_key(fronius_url, inverter=None):
    """Return the section name to look up: --inverter if given, else the URL's host name."""
    if inverter:
        return inverter
    host = urlparse(fronius_url if "://" in fronius_url else f"//{fronius_url}").hostname
    if not host:
        raise CredentialsError(
            "cannot determine the inverter host name from the Fronius URL; use --inverter NAME",
            EXIT_CREDENTIALS_INVALID)
    return host.rstrip(".")


def check_permissions(path, file_stat):
    """Refuse a file that is not a regular file owned by us with no group/other access."""
    if not stat.S_ISREG(file_stat.st_mode):
        raise CredentialsError(f"refusing to read {path}: not a regular file", EXIT_CREDENTIALS_INSECURE)
    if file_stat.st_uid != os.getuid():
        raise CredentialsError(
            f"refusing to read {path}: owned by uid {file_stat.st_uid}, not by the current user "
            f"(uid {os.getuid()})", EXIT_CREDENTIALS_INSECURE)
    mode = stat.S_IMODE(file_stat.st_mode)
    if mode & 0o077:
        raise CredentialsError(
            f"refusing to read {path}: mode {mode:04o} gives access to group or others; "
            f"run: chmod 600 {path}", EXIT_CREDENTIALS_INSECURE)

    directory = os.path.dirname(os.path.abspath(path))
    dir_mode = stat.S_IMODE(os.stat(directory).st_mode)
    if dir_mode & 0o022:
        raise CredentialsError(
            f"refusing to read {path}: directory {directory} has mode {dir_mode:04o} and is writable "
            f"by group or others; run: chmod 700 {directory}", EXIT_CREDENTIALS_INSECURE)


def read_password(path, key, match_host=False):
    """Return the password of section `key` in the credentials file at `path`."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    except FileNotFoundError:
        raise CredentialsError(
            f"credentials file not found: {path} (see README, section 'Inverter password')",
            EXIT_CREDENTIALS_MISSING) from None
    except PermissionError:
        raise CredentialsError(
            f"cannot read credentials file {path}: permission denied", EXIT_CREDENTIALS_INVALID) from None
    except OSError as e:
        raise CredentialsError(
            f"cannot open credentials file {path}: {e.strerror}", EXIT_CREDENTIALS_INVALID) from None

    # Check the opened file itself, so it cannot be swapped after the check
    try:
        check_permissions(path, os.fstat(fd))
    except BaseException:
        os.close(fd)
        raise

    with os.fdopen(fd, "rb") as f:
        try:
            content = f.read().decode("utf-8")
        except UnicodeDecodeError:
            raise CredentialsError(
                f"cannot read credentials file {path}: not valid UTF-8", EXIT_CREDENTIALS_INVALID) from None
        except OSError as e:
            raise CredentialsError(
                f"cannot read credentials file {path}: {e.strerror}", EXIT_CREDENTIALS_INVALID) from None

    parser = configparser.RawConfigParser()
    try:
        parser.read_string(content, source=path)
    except configparser.Error as e:
        # configparser messages quote the offending line, which may hold a password
        raise CredentialsError(
            f"cannot parse credentials file {path}: {type(e).__name__}{_line_info(e)}",
            EXIT_CREDENTIALS_INVALID) from None

    if match_host:
        sections = [s for s in parser.sections() if s.rstrip(".").lower() == key.lower()]
    else:
        sections = [key] if parser.has_section(key) else []
    if not sections:
        raise CredentialsError(
            f"no entry for inverter '{key}' in {path} (expected a [{key}] section with a "
            f"'password' key)", EXIT_CREDENTIALS_INVALID)

    password = parser.get(sections[0], "password", fallback="")
    if not password:
        raise CredentialsError(
            f"no password for inverter '{key}' in {path} (the [{sections[0]}] section needs a "
            f"non-empty 'password' key)", EXIT_CREDENTIALS_INVALID)
    return password


def _line_info(error):
    """Return ' at line N[, M...]' for a configparser error, without any line content."""
    if getattr(error, "lineno", None):
        return f" at line {error.lineno}"
    lines = [str(lineno) for lineno, _ in getattr(error, "errors", [])]
    return f" at line {', '.join(lines)}" if lines else ""


def resolve_password(cli_password, fronius_url, inverter=None, credentials_file=None, stderr=None):
    """Return the inverter password from -p (deprecated) or from the credentials file."""
    if cli_password is not None:
        print(DEPRECATION_WARNING, file=stderr or sys.stderr)
        return cli_password
    path = credentials_file or default_credentials_path()
    return read_password(path, inverter_key(fronius_url, inverter), match_host=not inverter)
