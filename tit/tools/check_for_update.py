"""Check for new TI-Toolbox releases on GitHub.

Queries the GitHub Releases API and compares the latest published tag
against the running version.  Designed for non-blocking startup checks.

Usage
-----
>>> from tit.tools.check_for_update import check_for_new_version
>>> newer = check_for_new_version("2.2.0")
>>> if newer:
...     print(f"Update available: {newer}")
"""

import logging

logger = logging.getLogger(__name__)


def parse_version(version_str: str) -> tuple:
    """Parse a version string into a tuple of integers.

    Leading ``v`` prefixes and non-numeric suffixes are stripped so that
    both ``"2.2.1"`` and ``"v2.2.1"`` produce ``(2, 2, 1)``.

    Parameters
    ----------
    version_str : str
        Dotted version string, e.g. ``"v2.2.1"``.

    Returns
    -------
    tuple of int
        Numeric version components.
    """
    parts = version_str.strip().lstrip("v").split(".")
    result = []
    for part in parts:
        try:
            result.append(int(part))
        except ValueError:
            pass
    return tuple(result)


def check_for_new_version(
    current_version: str,
    repo: str = "idossha/TI-Toolbox",
    timeout: float = 2.0,
) -> str | None:
    """Check GitHub for the latest release.

    Parameters
    ----------
    current_version : str
        The running version string (e.g. ``"2.2.0"``).
    repo : str, optional
        GitHub ``owner/repo`` slug.
    timeout : float, optional
        HTTP request timeout in seconds.

    Returns
    -------
    str or None
        The latest version string if a newer release exists, otherwise
        ``None``.

    Raises
    ------
    requests.HTTPError
        If the GitHub API request fails.
    """
    import requests

    url = f"https://api.github.com/repos/{repo}/releases/latest"
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    latest = data.get("tag_name", "").lstrip("v")
    if latest and parse_version(latest) > parse_version(current_version):
        return latest
    return None
